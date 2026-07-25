from __future__ import annotations

import argparse
import time

from sqlalchemy import or_, select

from app.config import get_settings
from app.database import SessionLocal
from app.models import DocumentProcessingJob, utc_now
from app.services.ai_processing import DocumentAiPipeline


def process_next() -> bool:
    with SessionLocal() as session:
        job_id = session.scalar(
            select(DocumentProcessingJob.id)
            .where(
                DocumentProcessingJob.status.in_(("PENDING", "RETRY")),
                or_(
                    DocumentProcessingJob.next_attempt_at.is_(None),
                    DocumentProcessingJob.next_attempt_at <= utc_now(),
                ),
            )
            .order_by(DocumentProcessingJob.created_at)
            .limit(1)
        )
        if job_id is None:
            return False
        DocumentAiPipeline(session).process(job_id)
        return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Durable AI document worker")
    parser.add_argument("--once", action="store_true", help="Process at most one due job")
    arguments = parser.parse_args()
    settings = get_settings()
    while True:
        processed = process_next()
        if arguments.once:
            return
        if not processed:
            time.sleep(max(settings.ai_worker_poll_seconds, 1))


if __name__ == "__main__":
    main()
