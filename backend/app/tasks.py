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
    User,
    VrpImportBatch,
    VrpImportSchedule,
    utc_now,
)
from app.services.ai_processing import DocumentAiPipeline
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

        due_batch_ids = list(
            session.scalars(
                select(VrpImportBatch.id).where(
                    VrpImportBatch.status == "SCHEDULED",
                    VrpImportBatch.scheduled_for <= now,
                )
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

    for batch_id in due_batch_ids:
        process_vrp_import_batch.send(batch_id)
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
