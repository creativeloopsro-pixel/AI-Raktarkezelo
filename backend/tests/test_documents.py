from io import BytesIO

import pytest
from pypdf import PdfWriter
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import AuditLog, Document, OutboxEvent, ReviewTask, User
from app.security import hash_password
from app.services.documents import (
    DocumentNeedsReviewError,
    DocumentService,
    DuplicateDocumentError,
)
from app.storage import LocalObjectStorage
from app.virus_scan import DisabledVirusScanner


def pdf_bytes() -> bytes:
    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    writer.write(output)
    return output.getvalue()


def document_service(session: Session, tmp_path) -> tuple[DocumentService, LocalObjectStorage]:
    storage = LocalObjectStorage(tmp_path / "objects")
    settings = Settings(
        _env_file=None,
        max_upload_mb=1,
        max_document_pages=5,
        object_store_backend="local",
        object_store_local_path=str(tmp_path / "objects"),
    )
    return (
        DocumentService(
            session,
            storage=storage,
            scanner=DisabledVirusScanner(),
            settings=settings,
        ),
        storage,
    )


def test_document_ingest_stores_hash_pages_audit_and_outbox(
    session: Session, seeded, tmp_path
) -> None:
    _, user, _ = seeded
    service, storage = document_service(session, tmp_path)

    document = service.ingest(
        user=user,
        stream=BytesIO(pdf_bytes()),
        filename="szallito-level.pdf",
        declared_content_type="application/pdf",
        correlation_id="document-correlation-1",
    )

    assert document.status == "UPLOADED"
    assert document.page_count == 1
    assert len(document.sha256_hash) == 64
    stored_path = storage.local_path(document.object_key)
    assert stored_path is not None and stored_path.exists()
    assert session.scalar(select(func.count()).select_from(AuditLog)) == 1
    assert session.scalar(select(func.count()).select_from(OutboxEvent)) == 1

    with pytest.raises(DuplicateDocumentError) as duplicate:
        service.ingest(
            user=user,
            stream=BytesIO(pdf_bytes()),
            filename="masolat.pdf",
            declared_content_type="application/pdf",
            correlation_id="document-correlation-2",
        )
    assert duplicate.value.existing_document_id == document.id
    assert session.scalar(select(func.count()).select_from(Document)) == 1


def test_corrupt_pdf_creates_review_task_and_blocks_processing(
    session: Session, seeded, tmp_path
) -> None:
    _, user, _ = seeded
    service, _ = document_service(session, tmp_path)
    document = service.ingest(
        user=user,
        stream=BytesIO(b"%PDF-1.7\ncorrupt-document"),
        filename="serult.pdf",
        declared_content_type="application/pdf",
        correlation_id="document-correlation-3",
    )

    assert document.status == "NEEDS_REVIEW"
    review_task = session.scalar(select(ReviewTask).where(ReviewTask.entity_id == document.id))
    assert review_task is not None
    assert review_task.reason_code == "CORRUPT_DOCUMENT"

    with pytest.raises(DocumentNeedsReviewError):
        service.queue_processing(
            user=user,
            document_id=document.id,
            idempotency_key="review-blocked-processing",
            correlation_id="document-correlation-blocked",
        )

    resolved = service.resolve_review_task(
        user=user,
        task_id=review_task.id,
        resolution_note="Kézzel ellenőrizve és elfogadva.",
        correlation_id="document-correlation-4",
    )
    session.refresh(document)
    assert resolved.status == "RESOLVED"
    assert document.status == "UPLOADED"


def test_processing_queue_is_idempotent(session: Session, seeded, tmp_path) -> None:
    _, user, _ = seeded
    service, _ = document_service(session, tmp_path)
    document = service.ingest(
        user=user,
        stream=BytesIO(pdf_bytes()),
        filename="feldolgozas.pdf",
        declared_content_type="application/pdf",
        correlation_id="document-correlation-5",
    )

    first = service.queue_processing(
        user=user,
        document_id=document.id,
        idempotency_key="document-processing-0001",
        correlation_id="document-correlation-6",
    )
    second = service.queue_processing(
        user=user,
        document_id=document.id,
        idempotency_key="document-processing-0001",
        correlation_id="document-correlation-7",
    )
    assert first.created is True
    assert second.created is False
    assert first.job.id == second.job.id


def test_document_upload_api_rejects_duplicate(
    client, monkeypatch, tmp_path, session: Session, seeded
) -> None:
    storage = LocalObjectStorage(tmp_path / "api-objects")
    monkeypatch.setattr("app.services.documents.get_object_storage", lambda: storage)
    monkeypatch.setattr("app.api.documents.get_object_storage", lambda: storage)
    monkeypatch.setattr("app.services.documents.get_virus_scanner", lambda: DisabledVirusScanner())
    login_response = client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": "tesztbolt",
            "email": "admin@teszt.hu",
            "password": "Secret-1234!",
        },
    )
    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    files = {"file": ("receipt.pdf", pdf_bytes(), "application/pdf")}

    upload_response = client.post(
        "/api/v1/documents",
        headers=headers,
        files=files,
        data={"document_type": "goods_receipt"},
    )
    assert upload_response.status_code == 201
    assert upload_response.json()["page_count"] == 1
    document_id = upload_response.json()["id"]

    download_response = client.get(f"/api/v1/documents/{document_id}/download", headers=headers)
    assert download_response.status_code == 200
    assert download_response.content == pdf_bytes()
    assert "receipt.pdf" in download_response.headers["content-disposition"]

    duplicate_response = client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": ("copy.pdf", pdf_bytes(), "application/pdf")},
        data={"document_type": "goods_receipt"},
    )
    assert duplicate_response.status_code == 409
    assert duplicate_response.json()["detail"]["code"] == "duplicate_document"

    list_response = client.get("/api/v1/documents", headers=headers)
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

    organization, _, _ = seeded
    viewer = User(
        organization_id=organization.id,
        email="viewer@teszt.hu",
        full_name="Teszt Olvasó",
        password_hash=hash_password("Secret-5678!"),
        role="viewer",
    )
    session.add(viewer)
    session.commit()
    viewer_login = client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": "tesztbolt",
            "email": "viewer@teszt.hu",
            "password": "Secret-5678!",
        },
    )
    viewer_token = viewer_login.json()["access_token"]
    forbidden_queue = client.post(
        f"/api/v1/documents/{document_id}/process",
        headers={
            "Authorization": f"Bearer {viewer_token}",
            "Idempotency-Key": "viewer-processing-attempt",
        },
    )
    assert forbidden_queue.status_code == 403
