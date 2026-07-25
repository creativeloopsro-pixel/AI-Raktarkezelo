from __future__ import annotations

from datetime import timedelta

import dramatiq
from dramatiq.brokers.redis import RedisBroker
from sqlalchemy import or_, select

from app.config import get_settings
from app.database import SessionLocal
from app.models import Document, DocumentProcessingJob, utc_now
from app.services.ai_processing import DocumentAiPipeline

settings = get_settings()
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
