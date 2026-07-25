from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import BinaryIO

import filetype
from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models import (
    AuditLog,
    Document,
    DocumentPage,
    DocumentProcessingJob,
    OutboxEvent,
    ReviewTask,
    User,
    new_id,
    utc_now,
)
from app.storage import ObjectStorage, get_object_storage
from app.virus_scan import (
    InfectedFileError,
    VirusScanner,
    VirusScannerUnavailableError,
    get_virus_scanner,
)

ALLOWED_CONTENT_TYPES = {
    "application/pdf": "pdf",
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/tiff": "tiff",
}


class DocumentError(Exception):
    code = "document_error"


class UnsupportedDocumentError(DocumentError):
    code = "unsupported_document"


class DocumentTooLargeError(DocumentError):
    code = "document_too_large"


class DuplicateDocumentError(DocumentError):
    code = "duplicate_document"

    def __init__(self, existing_document_id: str):
        self.existing_document_id = existing_document_id


class DocumentNotFoundError(DocumentError):
    code = "document_not_found"


class DocumentNeedsReviewError(DocumentError):
    code = "document_needs_review"


class ReviewTaskNotFoundError(DocumentError):
    code = "review_task_not_found"


class UnsafeDocumentError(DocumentError):
    code = "unsafe_document"


class ScannerUnavailableError(DocumentError):
    code = "scanner_unavailable"


@dataclass(frozen=True)
class DocumentValidation:
    content_type: str
    page_count: int
    issues: list[str]
    virus_scan: str


@dataclass(frozen=True)
class ProcessingJobResult:
    job: DocumentProcessingJob
    created: bool


class DocumentService:
    def __init__(
        self,
        session: Session,
        *,
        storage: ObjectStorage | None = None,
        scanner: VirusScanner | None = None,
        settings: Settings | None = None,
    ):
        self.session = session
        self.storage = storage or get_object_storage()
        self.scanner = scanner or get_virus_scanner()
        self.settings = settings or get_settings()

    def ingest(
        self,
        *,
        user: User,
        stream: BinaryIO,
        filename: str,
        declared_content_type: str | None,
        document_type: str = "goods_receipt",
        source_type: str = "WEB_UPLOAD",
        correlation_id: str,
    ) -> Document:
        safe_filename = Path(filename or "document").name[:255]
        max_bytes = self.settings.max_upload_mb * 1024 * 1024
        stored = False
        object_key = ""

        with TemporaryDirectory(prefix="ai-raktar-document-") as temp_directory:
            temporary_path = Path(temp_directory) / "upload.bin"
            file_hash = sha256()
            total_bytes = 0
            with temporary_path.open("wb") as temporary_file:
                while chunk := stream.read(1024 * 1024):
                    total_bytes += len(chunk)
                    if total_bytes > max_bytes:
                        raise DocumentTooLargeError
                    file_hash.update(chunk)
                    temporary_file.write(chunk)

            if total_bytes == 0:
                raise UnsupportedDocumentError

            digest = file_hash.hexdigest()
            duplicate = self.session.scalar(
                select(Document).where(
                    Document.organization_id == user.organization_id,
                    Document.sha256_hash == digest,
                )
            )
            if duplicate is not None:
                raise DuplicateDocumentError(duplicate.id)

            validation = self._validate(temporary_path, declared_content_type)
            document_id = new_id()
            extension = ALLOWED_CONTENT_TYPES[validation.content_type]
            object_key = f"{user.organization_id}/{document_id}/{digest[:20]}.{extension}"

            try:
                self.storage.put_file(temporary_path, object_key, validation.content_type)
                stored = True
                status = "NEEDS_REVIEW" if validation.issues else "UPLOADED"
                document = Document(
                    id=document_id,
                    organization_id=user.organization_id,
                    original_filename=safe_filename,
                    content_type=validation.content_type,
                    size_bytes=total_bytes,
                    sha256_hash=digest,
                    object_key=object_key,
                    status=status,
                    source_type=source_type,
                    document_type=document_type,
                    page_count=validation.page_count,
                    validation_summary={
                        "issues": validation.issues,
                        "virus_scan": validation.virus_scan,
                        "declared_content_type": declared_content_type,
                    },
                    uploaded_by=user.id,
                )
                self.session.add(document)
                for page_number in range(
                    1, min(validation.page_count, self.settings.max_document_pages) + 1
                ):
                    self.session.add(
                        DocumentPage(
                            organization_id=user.organization_id,
                            document_id=document_id,
                            page_number=page_number,
                        )
                    )

                if validation.issues:
                    self.session.add(
                        ReviewTask(
                            organization_id=user.organization_id,
                            task_type="DOCUMENT_VALIDATION",
                            entity_type="document",
                            entity_id=document_id,
                            reason_code=validation.issues[0],
                            context={
                                "filename": safe_filename,
                                "issues": validation.issues,
                            },
                        )
                    )

                self.session.add(
                    AuditLog(
                        organization_id=user.organization_id,
                        actor_id=user.id,
                        action="documents.uploaded",
                        entity_type="document",
                        entity_id=document_id,
                        correlation_id=correlation_id,
                        details={
                            "filename": safe_filename,
                            "sha256": digest,
                            "size_bytes": total_bytes,
                            "status": status,
                        },
                    )
                )
                self.session.add(
                    OutboxEvent(
                        organization_id=user.organization_id,
                        event_type="document.uploaded",
                        aggregate_type="document",
                        aggregate_id=document_id,
                        payload={
                            "document_id": document_id,
                            "document_type": document_type,
                            "status": status,
                            "correlation_id": correlation_id,
                        },
                    )
                )
                self.session.commit()
                self.session.refresh(document)
                return document
            except Exception:
                self.session.rollback()
                if stored:
                    self.storage.delete(object_key)
                raise

    def queue_processing(
        self,
        *,
        user: User,
        document_id: str,
        idempotency_key: str,
        correlation_id: str,
    ) -> ProcessingJobResult:
        duplicate = self.session.scalar(
            select(DocumentProcessingJob).where(
                DocumentProcessingJob.organization_id == user.organization_id,
                DocumentProcessingJob.idempotency_key == idempotency_key,
            )
        )
        if duplicate is not None:
            return ProcessingJobResult(job=duplicate, created=False)

        document = self.session.scalar(
            select(Document)
            .where(
                Document.id == document_id,
                Document.organization_id == user.organization_id,
            )
            .with_for_update()
        )
        if document is None:
            raise DocumentNotFoundError
        if document.status == "NEEDS_REVIEW":
            raise DocumentNeedsReviewError

        job = DocumentProcessingJob(
            organization_id=user.organization_id,
            document_id=document.id,
            idempotency_key=idempotency_key,
            job_type="AI_EXTRACTION",
            status="PENDING",
        )
        document.status = "QUEUED"
        self.session.add(job)
        self.session.flush()
        self.session.add(
            AuditLog(
                organization_id=user.organization_id,
                actor_id=user.id,
                action="documents.processing_queued",
                entity_type="document",
                entity_id=document.id,
                correlation_id=correlation_id,
                details={"job_id": job.id},
            )
        )
        self.session.add(
            OutboxEvent(
                organization_id=user.organization_id,
                event_type="document.processing.requested",
                aggregate_type="document",
                aggregate_id=document.id,
                payload={
                    "document_id": document.id,
                    "job_id": job.id,
                    "correlation_id": correlation_id,
                },
            )
        )
        self.session.commit()
        return ProcessingJobResult(job=job, created=True)

    def resolve_review_task(
        self,
        *,
        user: User,
        task_id: str,
        resolution_note: str,
        correlation_id: str,
    ) -> ReviewTask:
        task = self.session.scalar(
            select(ReviewTask)
            .where(
                ReviewTask.id == task_id,
                ReviewTask.organization_id == user.organization_id,
            )
            .with_for_update()
        )
        if task is None:
            raise ReviewTaskNotFoundError
        if task.status == "RESOLVED":
            return task

        task.status = "RESOLVED"
        task.resolved_by = user.id
        task.resolution_note = resolution_note
        task.resolved_at = utc_now()
        if task.entity_type == "document":
            document = self.session.scalar(
                select(Document).where(
                    Document.id == task.entity_id,
                    Document.organization_id == user.organization_id,
                )
            )
            if document is not None and document.status == "NEEDS_REVIEW":
                document.status = "UPLOADED"

        self.session.add(
            AuditLog(
                organization_id=user.organization_id,
                actor_id=user.id,
                action="review_task.resolved",
                entity_type="review_task",
                entity_id=task.id,
                correlation_id=correlation_id,
                details={"resolution_note": resolution_note},
            )
        )
        self.session.commit()
        return task

    def _validate(self, path: Path, declared_content_type: str | None) -> DocumentValidation:
        kind = filetype.guess(path)
        detected_content_type = kind.mime if kind else ""
        if detected_content_type not in ALLOWED_CONTENT_TYPES:
            raise UnsupportedDocumentError

        issues: list[str] = []
        if declared_content_type and declared_content_type not in {
            "application/octet-stream",
            detected_content_type,
        }:
            issues.append("MIME_TYPE_MISMATCH")

        try:
            virus_scan = self.scanner.scan(path)
        except InfectedFileError as exc:
            raise UnsafeDocumentError from exc
        except VirusScannerUnavailableError as exc:
            raise ScannerUnavailableError from exc

        page_count = 0
        if detected_content_type == "application/pdf":
            try:
                with path.open("rb") as pdf_file:
                    reader = PdfReader(pdf_file, strict=False)
                    if reader.is_encrypted and reader.decrypt("") == 0:
                        issues.append("PASSWORD_PROTECTED_PDF")
                    else:
                        page_count = len(reader.pages)
            except (PdfReadError, OSError, ValueError):
                issues.append("CORRUPT_DOCUMENT")
        else:
            try:
                with Image.open(path) as image:
                    page_count = int(getattr(image, "n_frames", 1))
                    image.verify()
            except (UnidentifiedImageError, OSError, ValueError):
                issues.append("CORRUPT_DOCUMENT")

        if page_count > self.settings.max_document_pages:
            issues.append("PAGE_LIMIT_EXCEEDED")
        return DocumentValidation(
            content_type=detected_content_type,
            page_count=page_count,
            issues=issues,
            virus_scan=virus_scan,
        )
