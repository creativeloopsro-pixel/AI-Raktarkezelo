from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.config import Settings, get_settings
from app.models import (
    AuditLog,
    OutboxEvent,
    Plugin,
    PluginJob,
    ReviewTask,
    utc_now,
)
from app.plugins.registry import (
    PluginHandlerNotFoundError,
    PluginRegistry,
    plugin_registry,
)
from app.plugins.sdk import PluginContext, PluginEvent, PluginSdkError
from app.services.plugins import PluginManifestError, PluginService


class PluginRuntime:
    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
        registry: PluginRegistry | None = None,
    ):
        self.session = session
        self.settings = settings or get_settings()
        self.registry = registry or plugin_registry

    def create_jobs_from_outbox(self) -> list[str]:
        plugin_service = PluginService(
            self.session, settings=self.settings, registry=self.registry
        )
        plugin_service.ensure_all_builtin_plugins()
        now = utc_now()
        events = list(
            self.session.scalars(
                select(OutboxEvent)
                .where(OutboxEvent.published_at.is_(None))
                .order_by(OutboxEvent.created_at)
                .limit(self.settings.plugin_dispatch_batch_size)
                .with_for_update(skip_locked=True)
            )
        )
        created_job_ids: list[str] = []
        for event in events:
            plugins = list(
                self.session.scalars(
                    select(Plugin)
                    .where(
                        Plugin.organization_id == event.organization_id,
                        Plugin.status == "ENABLED",
                    )
                    .options(
                        selectinload(Plugin.versions),
                        selectinload(Plugin.permissions),
                        selectinload(Plugin.settings),
                        selectinload(Plugin.service_user),
                    )
                ).unique()
            )
            target_plugin = str(event.payload.get("target_plugin_id", "")).strip()
            deferred = False
            subscribed = 0
            for plugin in plugins:
                if target_plugin and target_plugin != plugin.plugin_key:
                    continue
                try:
                    manifest = plugin_service.manifest_for(plugin)
                except PluginManifestError:
                    self._record_manifest_failure(plugin, event)
                    continue
                if event.event_type not in manifest.subscribes:
                    continue
                subscribed += 1
                existing = self.session.scalar(
                    select(PluginJob.id).where(
                        PluginJob.plugin_id == plugin.id,
                        PluginJob.outbox_event_id == event.id,
                    )
                )
                if existing is not None:
                    continue
                if self._rate_limited(plugin.id, now):
                    deferred = True
                    continue
                job = PluginJob(
                    organization_id=event.organization_id,
                    plugin_id=plugin.id,
                    outbox_event_id=event.id,
                    plugin_version=plugin.active_version,
                    event_type=event.event_type,
                    aggregate_type=event.aggregate_type,
                    aggregate_id=event.aggregate_id,
                    idempotency_key=f"event:{event.id}:plugin:{plugin.plugin_key}",
                    status="PENDING",
                    max_attempts=self.settings.plugin_max_retries,
                    payload=event.payload,
                    correlation_id=str(
                        event.payload.get("correlation_id") or event.id
                    )[:80],
                )
                self.session.add(job)
                self.session.flush()
                created_job_ids.append(job.id)
            if not deferred or subscribed == 0:
                event.published_at = now
        self.session.commit()
        return created_job_ids

    def due_job_ids(self) -> list[str]:
        now = utc_now()
        stale_before = now - timedelta(
            seconds=max(self.settings.plugin_job_timeout_seconds * 2, 120)
        )
        stale_jobs = self.session.scalars(
            select(PluginJob)
            .where(
                PluginJob.status == "PROCESSING",
                PluginJob.started_at < stale_before,
            )
            .with_for_update(skip_locked=True)
        )
        for job in stale_jobs:
            job.status = "RETRY"
            job.error_code = "stale_plugin_job_recovered"
            job.error_message = "A worker futása megszakadt; a job újra sorba állt."
            job.next_attempt_at = now
        job_ids = list(
            self.session.scalars(
                select(PluginJob.id)
                .where(
                    PluginJob.status.in_(("PENDING", "RETRY")),
                    or_(
                        PluginJob.next_attempt_at.is_(None),
                        PluginJob.next_attempt_at <= now,
                    ),
                )
                .order_by(PluginJob.created_at)
                .limit(self.settings.plugin_dispatch_batch_size)
            )
        )
        self.session.commit()
        return job_ids

    def run_job(self, job_id: str) -> PluginJob | None:
        job = self.session.scalar(
            select(PluginJob)
            .where(PluginJob.id == job_id)
            .options(
                selectinload(PluginJob.plugin).selectinload(Plugin.versions),
                selectinload(PluginJob.plugin).selectinload(Plugin.permissions),
                selectinload(PluginJob.plugin).selectinload(Plugin.settings),
                selectinload(PluginJob.plugin).selectinload(Plugin.service_user),
            )
            .with_for_update()
        )
        if job is None:
            return None
        if job.status in {"COMPLETED", "FAILED", "CANCELLED"}:
            return job
        if job.plugin.status != "ENABLED":
            job.status = "CANCELLED"
            job.error_code = "plugin_disabled"
            job.error_message = "A plugin a futtatás előtt le lett tiltva."
            job.completed_at = utc_now()
            self.session.commit()
            return job

        job.status = "PROCESSING"
        job.attempts += 1
        job.started_at = utc_now()
        job.next_attempt_at = None
        self.session.commit()

        try:
            plugin_service = PluginService(
                self.session, settings=self.settings, registry=self.registry
            )
            manifest = plugin_service.manifest_for(job.plugin)
            handler = self.registry.get(job.plugin.plugin_key, job.event_type)
            event = PluginEvent(
                id=job.outbox_event_id,
                type=job.event_type,
                aggregate_type=job.aggregate_type,
                aggregate_id=job.aggregate_id,
                payload=job.payload,
                correlation_id=job.correlation_id,
            )
            context = PluginContext(
                self.session,
                plugin=job.plugin,
                job=job,
                manifest=manifest,
            )
            result = handler(context, event) or {}
            job.status = "COMPLETED"
            job.result = self._json_result(result)
            job.error_code = None
            job.error_message = None
            job.completed_at = utc_now()
            self.session.add(
                AuditLog(
                    organization_id=job.organization_id,
                    actor_id=job.plugin.service_user_id,
                    action="plugin.job_completed",
                    entity_type="plugin_job",
                    entity_id=job.id,
                    correlation_id=job.correlation_id,
                    details={
                        "plugin_id": job.plugin.plugin_key,
                        "event_type": job.event_type,
                        "attempts": job.attempts,
                    },
                )
            )
            self.session.commit()
            return job
        except Exception as exc:
            self.session.rollback()
            failed_job = self.session.scalar(
                select(PluginJob)
                .where(PluginJob.id == job_id)
                .options(selectinload(PluginJob.plugin))
                .with_for_update()
            )
            if failed_job is None:
                return None
            error_code = self._error_code(exc)
            failed_job.error_code = error_code
            failed_job.error_message = str(exc)[:1000] or error_code
            if failed_job.attempts < failed_job.max_attempts:
                failed_job.status = "RETRY"
                failed_job.next_attempt_at = utc_now() + timedelta(
                    seconds=min(2**failed_job.attempts * 5, 300)
                )
            else:
                failed_job.status = "FAILED"
                failed_job.completed_at = utc_now()
                self._record_final_failure(failed_job)
            self.session.commit()
            return failed_job

    def _rate_limited(self, plugin_id: str, now) -> bool:
        recent = self.session.scalar(
            select(func.count())
            .select_from(PluginJob)
            .where(
                PluginJob.plugin_id == plugin_id,
                PluginJob.created_at >= now - timedelta(minutes=1),
            )
        )
        return int(recent or 0) >= self.settings.plugin_rate_limit_per_minute

    def _record_manifest_failure(
        self, plugin: Plugin, event: OutboxEvent
    ) -> None:
        self.session.add(
            ReviewTask(
                organization_id=plugin.organization_id,
                task_type="PLUGIN_FAILURE",
                entity_type="plugin",
                entity_id=plugin.id,
                reason_code="INVALID_PLUGIN_MANIFEST",
                context={
                    "plugin_id": plugin.plugin_key,
                    "outbox_event_id": event.id,
                },
            )
        )
        plugin.status = "DISABLED"
        plugin.disabled_at = utc_now()

    def _record_final_failure(self, job: PluginJob) -> None:
        self.session.add(
            ReviewTask(
                organization_id=job.organization_id,
                task_type="PLUGIN_FAILURE",
                entity_type="plugin_job",
                entity_id=job.id,
                reason_code=job.error_code or "PLUGIN_JOB_FAILED",
                context={
                    "plugin_id": job.plugin.plugin_key,
                    "event_type": job.event_type,
                    "error": job.error_message,
                },
            )
        )
        self.session.add(
            AuditLog(
                organization_id=job.organization_id,
                actor_id=job.plugin.service_user_id,
                action="plugin.job_failed",
                entity_type="plugin_job",
                entity_id=job.id,
                correlation_id=job.correlation_id,
                details={
                    "plugin_id": job.plugin.plugin_key,
                    "event_type": job.event_type,
                    "attempts": job.attempts,
                    "error_code": job.error_code,
                },
            )
        )
        self.session.add(
            OutboxEvent(
                organization_id=job.organization_id,
                event_type="plugin.failed",
                aggregate_type="plugin",
                aggregate_id=job.plugin_id,
                payload={
                    "plugin_id": job.plugin.plugin_key,
                    "plugin_job_id": job.id,
                    "error_code": job.error_code,
                    "correlation_id": job.correlation_id,
                },
            )
        )

    @staticmethod
    def _error_code(exc: Exception) -> str:
        if isinstance(exc, PluginSdkError):
            return exc.code
        if isinstance(exc, PluginHandlerNotFoundError):
            return "plugin_handler_not_found"
        if isinstance(exc, PluginManifestError):
            return exc.code
        return "plugin_handler_failed"

    @staticmethod
    def _json_result(result: dict[str, Any]) -> dict[str, Any]:
        safe: dict[str, Any] = {}
        for key, value in result.items():
            if (
                isinstance(value, (str, int, float, bool, list, dict))
                or value is None
            ):
                safe[str(key)[:100]] = value
            else:
                safe[str(key)[:100]] = str(value)
        return safe
