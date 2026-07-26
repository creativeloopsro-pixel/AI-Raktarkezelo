from __future__ import annotations

import logging
from datetime import timedelta
from uuid import uuid4

import dramatiq
from dramatiq.brokers.redis import RedisBroker
from sqlalchemy import or_, select

from app.config import get_settings
from app.database import SessionLocal
from app.email_imap import poll_imap_once
from app.models import (
    Document,
    DocumentProcessingJob,
    InventoryReportRun,
    InventoryReportSchedule,
    OutboxEvent,
    Plugin,
    User,
    VrpImportBatch,
    VrpImportSchedule,
    utc_now,
)
from app.services.ai_processing import DocumentAiPipeline
from app.services.inventory_reports import InventoryReportService
from app.services.plugin_runtime import PluginRuntime
from app.services.vrp_imports import (
    VrpImportNotFoundError,
    VrpImportService,
    VrpNegativeStockError,
    VrpNotProcessableError,
)
from app.vrp.scheduling import calculate_next_run

settings = get_settings()
logger = logging.getLogger(__name__)
broker = RedisBroker(
    url=settings.redis_url,
    socket_connect_timeout=2,
    socket_timeout=2,
)
dramatiq.set_broker(broker)


@dramatiq.actor(max_retries=0, time_limit=(settings.ai_timeout_seconds + 60) * 1000)
def process_document_job(job_id: str) -> None:
    with SessionLocal() as session:
        DocumentAiPipeline(session).process(job_id)


@dramatiq.actor(max_retries=3, min_backoff=5000)
def recover_pending_document_jobs() -> None:
    now = utc_now()
    stale_before = now - timedelta(minutes=10)
    with SessionLocal.begin() as session:
        stale_jobs = session.scalars(
            select(DocumentProcessingJob).where(
                DocumentProcessingJob.status == "PROCESSING",
                DocumentProcessingJob.started_at < stale_before,
            )
        )
        for job in stale_jobs:
            job.status = "RETRY"
            job.error_code = "stale_worker_recovered"
            job.next_attempt_at = now
            document = session.scalar(
                select(Document).where(
                    Document.id == job.document_id,
                    Document.organization_id == job.organization_id,
                )
            )
            if document is not None:
                document.status = "QUEUED"

        due_ids = list(
            session.scalars(
                select(DocumentProcessingJob.id).where(
                    DocumentProcessingJob.status.in_(("PENDING", "RETRY")),
                    or_(
                        DocumentProcessingJob.next_attempt_at.is_(None),
                        DocumentProcessingJob.next_attempt_at <= now,
                    ),
                )
            )
        )

    for job_id in due_ids:
        process_document_job.send(job_id)
    recover_pending_document_jobs.send_with_options(
        delay=max(settings.ai_worker_poll_seconds, 1) * 1000
    )


@dramatiq.actor(max_retries=0, time_limit=300_000)
def process_vrp_import_batch(batch_id: str) -> None:
    with SessionLocal() as session:
        batch = session.scalar(
            select(VrpImportBatch).where(VrpImportBatch.id == batch_id)
        )
        if batch is None:
            return
        operator = session.scalar(
            select(User)
            .where(
                User.organization_id == batch.organization_id,
                User.is_active.is_(True),
                User.role.in_(("admin", "manager")),
            )
            .order_by(User.role, User.created_at)
        )
        service = VrpImportService(session)
        if operator is None:
            service.mark_failed(
                batch.organization_id,
                batch.id,
                "vrp_worker_operator_missing",
            )
            return
        try:
            service.process(
                user=operator,
                batch_id=batch.id,
                correlation_id=f"vrp-worker:{uuid4()}",
            )
        except (VrpNegativeStockError, VrpNotProcessableError):
            session.rollback()
        except VrpImportNotFoundError:
            session.rollback()
        except Exception:
            session.rollback()
            logger.exception("A VRP-import worker hibával leállt: %s", batch_id)
            service.mark_failed(
                batch.organization_id,
                batch.id,
                "vrp_worker_failed",
            )


@dramatiq.actor(max_retries=3, min_backoff=5000)
def process_inventory_report_run(run_id: str) -> None:
    with SessionLocal() as session:
        InventoryReportService(session).process_run(run_id)


@dramatiq.actor(max_retries=3, min_backoff=5000)
def run_vrp_scheduler() -> None:
    now = utc_now()
    stale_before = now - timedelta(minutes=10)
    with SessionLocal.begin() as session:
        stale_batches = session.scalars(
            select(VrpImportBatch)
            .where(
                VrpImportBatch.status == "PROCESSING",
                VrpImportBatch.processing_started_at < stale_before,
            )
            .with_for_update()
        )
        for batch in stale_batches:
            batch.status = "SCHEDULED"
            batch.scheduled_for = now
            batch.processing_started_at = None
            batch.error_summary = {
                **batch.error_summary,
                "stale_worker_recovered": True,
            }

        due_batches = list(
            session.scalars(
                select(VrpImportBatch)
                .where(
                    VrpImportBatch.status == "SCHEDULED",
                    VrpImportBatch.scheduled_for <= now,
                )
                .with_for_update(skip_locked=True)
            )
        )
        enabled_vrp_organizations = set(
            session.scalars(
                select(Plugin.organization_id).where(
                    Plugin.plugin_key == "vrp-import",
                    Plugin.status == "ENABLED",
                )
            )
        )
        for batch in due_batches:
            if batch.organization_id not in enabled_vrp_organizations:
                continue
            batch.scheduled_for = None
            session.add(
                OutboxEvent(
                    organization_id=batch.organization_id,
                    event_type="schedule.triggered",
                    aggregate_type="vrp_import_batch",
                    aggregate_id=batch.id,
                    payload={
                        "target_plugin_id": "vrp-import",
                        "batch_id": batch.id,
                        "correlation_id": f"vrp-schedule:{uuid4()}",
                    },
                )
            )
        due_schedules = session.scalars(
            select(VrpImportSchedule)
            .where(
                VrpImportSchedule.auto_process.is_(True),
                VrpImportSchedule.frequency != "MANUAL",
                VrpImportSchedule.next_run_at <= now,
            )
            .with_for_update()
        )
        for schedule in due_schedules:
            schedule.last_run_at = now
            schedule.next_run_at = calculate_next_run(
                frequency=schedule.frequency,
                processing_time=schedule.processing_time,
                timezone_name=schedule.timezone,
                weekly_day=schedule.weekly_day,
                monthly_rule=schedule.monthly_rule,
                after=now,
            )

        stale_report_runs = session.scalars(
            select(InventoryReportRun)
            .where(
                InventoryReportRun.status == "PROCESSING",
                InventoryReportRun.started_at < stale_before,
            )
            .with_for_update(skip_locked=True)
        )
        for report_run in stale_report_runs:
            if report_run.attempts < 3:
                report_run.status = "PENDING"
                report_run.next_attempt_at = now
            else:
                report_run.status = "FAILED"
                report_run.completed_at = now
                report_run.error_message = (
                    report_run.error_message or "A riport worker nem fejezte be a futást."
                )

        due_report_schedules = session.scalars(
            select(InventoryReportSchedule)
            .where(
                InventoryReportSchedule.enabled.is_(True),
                InventoryReportSchedule.next_run_at <= now,
            )
            .with_for_update(skip_locked=True)
        )
        for report_schedule in due_report_schedules:
            scheduled_for = report_schedule.next_run_at
            if scheduled_for is None:
                continue
            session.add(
                InventoryReportRun(
                    organization_id=report_schedule.organization_id,
                    scheduled_for=scheduled_for,
                    next_attempt_at=now,
                )
            )
            report_schedule.next_run_at = calculate_next_run(
                frequency=report_schedule.frequency,
                processing_time=report_schedule.generation_time,
                timezone_name=report_schedule.timezone,
                weekly_day=report_schedule.weekly_day,
                monthly_rule=report_schedule.monthly_rule,
                after=now,
            )
        session.flush()
        pending_report_run_ids = list(
            session.scalars(
                select(InventoryReportRun.id).where(
                    InventoryReportRun.status == "PENDING",
                    or_(
                        InventoryReportRun.next_attempt_at.is_(None),
                        InventoryReportRun.next_attempt_at <= now,
                    ),
                )
            )
        )

    for report_run_id in pending_report_run_ids:
        process_inventory_report_run.send(report_run_id)
    run_vrp_scheduler.send_with_options(
        delay=max(settings.vrp_scheduler_poll_seconds, 1) * 1000
    )


@dramatiq.actor(max_retries=0)
def poll_inbound_email() -> None:
    if not settings.email_imap_enabled:
        return
    try:
        poll_imap_once(settings=settings)
    except Exception:
        logger.exception("Az IMAP e-mail worker futása sikertelen.")
    finally:
        poll_inbound_email.send_with_options(
            delay=max(settings.email_imap_poll_seconds, 5) * 1000
        )


@dramatiq.actor(
    max_retries=0,
    time_limit=settings.plugin_job_timeout_seconds * 1000,
)
def process_plugin_job(job_id: str) -> None:
    with SessionLocal() as session:
        PluginRuntime(session, settings=settings).run_job(job_id)


@dramatiq.actor(max_retries=0)
def run_plugin_dispatcher() -> None:
    job_ids: set[str] = set()
    try:
        with SessionLocal() as session:
            runtime = PluginRuntime(session, settings=settings)
            job_ids.update(runtime.create_jobs_from_outbox())
            job_ids.update(runtime.due_job_ids())
    except Exception:
        logger.exception("A plugin outbox dispatcher futása sikertelen.")
    for job_id in job_ids:
        process_plugin_job.send(job_id)
    run_plugin_dispatcher.send_with_options(
        delay=max(settings.plugin_dispatcher_poll_seconds, 1) * 1000
    )
