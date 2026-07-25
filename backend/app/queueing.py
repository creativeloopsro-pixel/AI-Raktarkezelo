import logging

logger = logging.getLogger(__name__)


def dispatch_document_job(job_id: str) -> bool:
    try:
        from app.tasks import process_document_job

        process_document_job.send(job_id)
    except Exception:
        logger.exception("Document job %s remains in the durable queue", job_id)
        return False
    return True
