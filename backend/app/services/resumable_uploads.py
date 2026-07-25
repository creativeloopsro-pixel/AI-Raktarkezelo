from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from hashlib import sha256
from math import ceil
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models import AuditLog, ResumableUploadSession, User, utc_now
from app.services.documents import DocumentService
from app.services.vrp_imports import VrpImportService
from app.storage import ObjectStorage, get_object_storage


class ResumableUploadError(Exception):
    code = "resumable_upload_error"


class ResumableUploadNotFoundError(ResumableUploadError):
    code = "resumable_upload_not_found"


class ResumableUploadConflictError(ResumableUploadError):
    code = "resumable_upload_conflict"


class ResumableUploadStateError(ResumableUploadError):
    code = "resumable_upload_state"


class ResumableUploadChunkError(ResumableUploadError):
    code = "resumable_upload_chunk_invalid"


class ResumableUploadIncompleteError(ResumableUploadError):
    code = "resumable_upload_incomplete"


class ResumableUploadIntegrityError(ResumableUploadError):
    code = "resumable_upload_integrity"


class ResumableUploadMetadataError(ResumableUploadError):
    code = "resumable_upload_metadata"


@dataclass(frozen=True)
class ResumableUploadCompletion:
    upload: ResumableUploadSession
    entity_type: str
    entity_id: str


class ResumableUploadService:
    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
        storage: ObjectStorage | None = None,
    ):
        self.session = session
        self.settings = settings or get_settings()
        self.storage = storage or get_object_storage()

    def create(
        self,
        *,
        user: User,
        client_upload_id: str,
        target_type: str,
        filename: str,
        declared_content_type: str | None,
        total_size: int,
        file_sha256: str | None,
        metadata: dict,
        correlation_id: str,
    ) -> ResumableUploadSession:
        target = target_type.upper()
        if target not in {"DOCUMENT", "VRP"}:
            raise ResumableUploadMetadataError
        max_bytes = (
            self.settings.max_upload_mb
            if target == "DOCUMENT"
            else self.settings.vrp_max_upload_mb
        ) * 1024 * 1024
        if total_size <= 0 or total_size > max_bytes:
            raise ResumableUploadMetadataError
        safe_filename = Path(filename or "upload").name[:255]
        normalized_metadata = self._validate_metadata(target, metadata)
        existing = self.session.scalar(
            select(ResumableUploadSession).where(
                ResumableUploadSession.organization_id == user.organization_id,
                ResumableUploadSession.client_upload_id == client_upload_id,
            )
        )
        if existing is not None:
            if (
                existing.target_type != target
                or existing.filename != safe_filename
                or existing.total_size != total_size
                or existing.file_sha256 != file_sha256
            ):
                raise ResumableUploadConflictError
            return existing

        chunk_size = max(256 * 1024, self.settings.resumable_upload_chunk_mb * 1024 * 1024)
        upload = ResumableUploadSession(
            organization_id=user.organization_id,
            created_by=user.id,
            client_upload_id=client_upload_id,
            target_type=target,
            filename=safe_filename,
            declared_content_type=declared_content_type,
            total_size=total_size,
            chunk_size=chunk_size,
            total_chunks=ceil(total_size / chunk_size),
            received_chunks=[],
            chunk_hashes={},
            file_sha256=file_sha256,
            upload_metadata=normalized_metadata,
            status="PENDING",
            expires_at=utc_now()
            + timedelta(hours=self.settings.resumable_upload_expiry_hours),
        )
        self.session.add(upload)
        self.session.flush()
        self._audit(
            user,
            "uploads.session_created",
            upload,
            correlation_id,
            {
                "target_type": target,
                "filename": safe_filename,
                "total_size": total_size,
                "total_chunks": upload.total_chunks,
            },
        )
        self.session.commit()
        self.session.refresh(upload)
        return upload

    def list_sessions(
        self,
        organization_id: str,
        *,
        created_by: str,
        target_type: str,
        limit: int = 100,
    ) -> list[ResumableUploadSession]:
        return list(
            self.session.scalars(
                select(ResumableUploadSession)
                .where(
                    ResumableUploadSession.organization_id == organization_id,
                    ResumableUploadSession.created_by == created_by,
                    ResumableUploadSession.target_type == target_type.upper(),
                )
                .order_by(ResumableUploadSession.updated_at.desc())
                .limit(limit)
            )
        )

    def get(
        self,
        organization_id: str,
        upload_id: str,
        *,
        created_by: str | None = None,
        lock: bool = False,
    ) -> ResumableUploadSession:
        statement = select(ResumableUploadSession).where(
            ResumableUploadSession.id == upload_id,
            ResumableUploadSession.organization_id == organization_id,
        )
        if created_by is not None:
            statement = statement.where(
                ResumableUploadSession.created_by == created_by,
            )
        if lock:
            statement = statement.with_for_update()
        upload = self.session.scalar(statement)
        if upload is None:
            raise ResumableUploadNotFoundError
        return upload

    def put_chunk(
        self,
        *,
        user: User,
        upload_id: str,
        chunk_index: int,
        payload: bytes,
        declared_sha256: str | None,
    ) -> ResumableUploadSession:
        upload = self.get(
            user.organization_id,
            upload_id,
            created_by=user.id,
            lock=True,
        )
        if upload.status not in {"PENDING", "UPLOADING", "FAILED"}:
            raise ResumableUploadStateError
        now = utc_now()
        comparison_now = (
            now if upload.expires_at.tzinfo is not None else now.replace(tzinfo=None)
        )
        if upload.expires_at < comparison_now:
            upload.status = "EXPIRED"
            self.session.commit()
            raise ResumableUploadStateError
        if chunk_index < 0 or chunk_index >= upload.total_chunks:
            raise ResumableUploadChunkError
        expected_size = self._expected_chunk_size(upload, chunk_index)
        if len(payload) != expected_size:
            raise ResumableUploadChunkError
        digest = sha256(payload).hexdigest()
        if declared_sha256 and declared_sha256 != digest:
            raise ResumableUploadIntegrityError
        stored_hash = upload.chunk_hashes.get(str(chunk_index))
        if chunk_index in upload.received_chunks:
            if stored_hash != digest:
                raise ResumableUploadConflictError
            return upload

        with TemporaryDirectory(prefix="ai-raktar-upload-chunk-") as temp_directory:
            path = Path(temp_directory) / f"{chunk_index}.part"
            path.write_bytes(payload)
            self.storage.put_file(
                path,
                self._chunk_key(upload, chunk_index),
                "application/octet-stream",
            )

        upload.received_chunks = sorted([*upload.received_chunks, chunk_index])
        upload.chunk_hashes = {**upload.chunk_hashes, str(chunk_index): digest}
        upload.status = "UPLOADING"
        upload.last_error_code = None
        upload.expires_at = utc_now() + timedelta(
            hours=self.settings.resumable_upload_expiry_hours
        )
        self.session.commit()
        self.session.refresh(upload)
        return upload

    def complete(
        self,
        *,
        user: User,
        upload_id: str,
        declared_file_sha256: str | None,
        correlation_id: str,
    ) -> ResumableUploadCompletion:
        upload = self.get(
            user.organization_id,
            upload_id,
            created_by=user.id,
            lock=True,
        )
        if upload.status == "COMPLETED":
            return ResumableUploadCompletion(
                upload=upload,
                entity_type=upload.result_entity_type or "",
                entity_id=upload.result_entity_id or "",
            )
        if upload.status in {"CANCELLED", "EXPIRED"}:
            raise ResumableUploadStateError
        expected = list(range(upload.total_chunks))
        if upload.received_chunks != expected:
            raise ResumableUploadIncompleteError

        upload.status = "ASSEMBLING"
        upload.last_error_code = None
        self.session.commit()
        try:
            with TemporaryDirectory(prefix="ai-raktar-resumable-") as temp_directory:
                assembled_path = Path(temp_directory) / upload.filename
                digest = sha256()
                written = 0
                with assembled_path.open("wb") as assembled:
                    for index in expected:
                        stream = self.storage.open_stream(self._chunk_key(upload, index))
                        if stream is None:
                            raise ResumableUploadIncompleteError
                        try:
                            while data := stream.read(1024 * 1024):
                                digest.update(data)
                                written += len(data)
                                assembled.write(data)
                        finally:
                            close = getattr(stream, "close", None)
                            if close is not None:
                                close()
                actual_digest = digest.hexdigest()
                expected_digest = declared_file_sha256 or upload.file_sha256
                if written != upload.total_size:
                    raise ResumableUploadIntegrityError
                if expected_digest and actual_digest != expected_digest:
                    raise ResumableUploadIntegrityError

                with assembled_path.open("rb") as source:
                    if upload.target_type == "DOCUMENT":
                        document = DocumentService(
                            self.session,
                            settings=self.settings,
                            storage=self.storage,
                        ).ingest(
                            user=user,
                            stream=source,
                            filename=upload.filename,
                            declared_content_type=upload.declared_content_type,
                            document_type=str(
                                upload.upload_metadata.get(
                                    "document_type",
                                    "goods_receipt",
                                )
                            ),
                            source_type="RESUMABLE_WEB_UPLOAD",
                            correlation_id=correlation_id,
                            source_metadata={
                                "client_upload_id": upload.client_upload_id,
                                "resumable": True,
                            },
                        )
                        entity_type = "document"
                        entity_id = document.id
                    else:
                        period_start = date.fromisoformat(
                            str(upload.upload_metadata["period_start"])
                        )
                        period_end = date.fromisoformat(
                            str(upload.upload_metadata["period_end"])
                        )
                        batch = VrpImportService(
                            self.session,
                            settings=self.settings,
                            storage=self.storage,
                        ).ingest(
                            user=user,
                            stream=source,
                            filename=upload.filename,
                            declared_content_type=upload.declared_content_type,
                            period_start=period_start,
                            period_end=period_end,
                            external_report_id=(
                                str(upload.upload_metadata["external_report_id"])
                                if upload.upload_metadata.get("external_report_id")
                                else None
                            ),
                            correlation_id=correlation_id,
                        ).batch
                        entity_type = "vrp_import_batch"
                        entity_id = batch.id
        except Exception as exc:
            self.session.rollback()
            failed = self.get(
                user.organization_id,
                upload_id,
                created_by=user.id,
                lock=True,
            )
            failed.status = "FAILED"
            failed.last_error_code = getattr(exc, "code", exc.__class__.__name__)
            self.session.commit()
            raise

        completed = self.get(
            user.organization_id,
            upload_id,
            created_by=user.id,
            lock=True,
        )
        completed.status = "COMPLETED"
        completed.file_sha256 = actual_digest
        completed.result_entity_type = entity_type
        completed.result_entity_id = entity_id
        completed.completed_at = utc_now()
        completed.last_error_code = None
        self._audit(
            user,
            "uploads.session_completed",
            completed,
            correlation_id,
            {
                "target_type": completed.target_type,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "sha256": actual_digest,
            },
        )
        self.session.commit()
        self.session.refresh(completed)
        self._delete_chunks(completed)
        return ResumableUploadCompletion(
            upload=completed,
            entity_type=entity_type,
            entity_id=entity_id,
        )

    def cancel(
        self,
        *,
        user: User,
        upload_id: str,
        correlation_id: str,
    ) -> ResumableUploadSession:
        upload = self.get(
            user.organization_id,
            upload_id,
            created_by=user.id,
            lock=True,
        )
        if upload.status == "COMPLETED":
            raise ResumableUploadStateError
        if upload.status != "CANCELLED":
            upload.status = "CANCELLED"
            upload.cancelled_at = utc_now()
            self._audit(
                user,
                "uploads.session_cancelled",
                upload,
                correlation_id,
                {"received_chunks": len(upload.received_chunks)},
            )
            self.session.commit()
            self.session.refresh(upload)
            self._delete_chunks(upload)
        return upload

    @staticmethod
    def _validate_metadata(target_type: str, metadata: dict) -> dict:
        if target_type == "DOCUMENT":
            document_type = str(metadata.get("document_type") or "goods_receipt")
            if not document_type or len(document_type) > 60:
                raise ResumableUploadMetadataError
            return {"document_type": document_type}
        try:
            period_start = date.fromisoformat(str(metadata["period_start"]))
            period_end = date.fromisoformat(str(metadata["period_end"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise ResumableUploadMetadataError from exc
        if period_start > period_end or (period_end - period_start).days > 366:
            raise ResumableUploadMetadataError
        external_report_id = metadata.get("external_report_id")
        if external_report_id is not None and len(str(external_report_id)) > 160:
            raise ResumableUploadMetadataError
        return {
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "external_report_id": (
                str(external_report_id) if external_report_id else None
            ),
        }

    @staticmethod
    def _chunk_key(upload: ResumableUploadSession, chunk_index: int) -> str:
        return (
            f"{upload.organization_id}/resumable/{upload.id}/"
            f"{chunk_index:08d}.part"
        )

    @staticmethod
    def _expected_chunk_size(
        upload: ResumableUploadSession,
        chunk_index: int,
    ) -> int:
        if chunk_index < upload.total_chunks - 1:
            return upload.chunk_size
        return upload.total_size - (upload.chunk_size * (upload.total_chunks - 1))

    def _delete_chunks(self, upload: ResumableUploadSession) -> None:
        for index in range(upload.total_chunks):
            try:
                self.storage.delete(self._chunk_key(upload, index))
            except Exception:
                continue

    def _audit(
        self,
        user: User,
        action: str,
        upload: ResumableUploadSession,
        correlation_id: str,
        details: dict,
    ) -> None:
        self.session.add(
            AuditLog(
                organization_id=user.organization_id,
                actor_id=user.id,
                action=action,
                entity_type="resumable_upload",
                entity_id=upload.id,
                correlation_id=correlation_id,
                details=details,
            )
        )
