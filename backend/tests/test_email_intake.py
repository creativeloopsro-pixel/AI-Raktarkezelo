from __future__ import annotations

import hmac
import time
from email.message import EmailMessage
from hashlib import sha256
from io import BytesIO

import pytest
from pypdf import PdfWriter
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.email_imap import poll_imap_once
from app.models import (
    AuditLog,
    Document,
    DocumentProcessingJob,
    EmailInboundSettings,
    InboundEmail,
    OutboxEvent,
    ReviewTask,
)
from app.services.documents import DocumentService
from app.services.email_intake import (
    EmailIntakeService,
    EmailReplayWindowError,
    EmailSignatureError,
    verify_webhook_signature,
)
from app.storage import LocalObjectStorage
from app.virus_scan import DisabledVirusScanner

ROUTING_TOKEN = "0123456789abcdef01234567"


def pdf_bytes() -> bytes:
    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    writer.write(output)
    return output.getvalue()


def raw_email(
    *,
    sender: str = "supplier@trusted.example",
    recipient: str = f"documents+{ROUTING_TOKEN}@mail.example.test",
    attachment: bytes | None = None,
) -> bytes:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = "Szállítólevél DL-1048"
    message["Message-ID"] = "<mail-1048@trusted.example>"
    message.set_content("A szállítólevél csatolva.")
    if attachment is not None:
        message.add_attachment(
            attachment,
            maintype="application",
            subtype="pdf",
            filename="szallito-level.pdf",
        )
    return message.as_bytes()


def email_settings(tmp_path, **overrides) -> Settings:
    return Settings(
        _env_file=None,
        object_store_backend="local",
        object_store_local_path=str(tmp_path / "objects"),
        email_inbound_domain="mail.example.test",
        email_webhook_secret="test-email-webhook-secret",
        ai_provider="disabled",
        **overrides,
    )


def intake_service(
    session: Session,
    tmp_path,
    settings: Settings,
) -> EmailIntakeService:
    document_service = DocumentService(
        session,
        storage=LocalObjectStorage(tmp_path / "objects"),
        scanner=DisabledVirusScanner(),
        settings=settings,
    )
    return EmailIntakeService(
        session,
        settings=settings,
        document_service=document_service,
    )


def create_mailbox(
    session: Session,
    organization_id: str,
    *,
    allowed_sender_domains: list[str] | None = None,
) -> EmailInboundSettings:
    mailbox = EmailInboundSettings(
        organization_id=organization_id,
        routing_token=ROUTING_TOKEN,
        enabled=True,
        auto_process=True,
        allowed_sender_domains=allowed_sender_domains or [],
    )
    session.add(mailbox)
    session.commit()
    return mailbox


def test_webhook_signature_has_constant_time_validation_and_replay_window(tmp_path) -> None:
    settings = email_settings(tmp_path)
    payload = raw_email(attachment=pdf_bytes())
    timestamp = str(int(time.time()))
    signature = hmac.new(
        b"test-email-webhook-secret",
        f"{timestamp}.".encode() + payload,
        sha256,
    ).hexdigest()

    verify_webhook_signature(
        payload,
        timestamp=timestamp,
        signature=f"sha256={signature}",
        settings=settings,
    )
    with pytest.raises(EmailSignatureError):
        verify_webhook_signature(
            payload,
            timestamp=timestamp,
            signature="sha256=" + ("0" * 64),
            settings=settings,
        )
    with pytest.raises(EmailReplayWindowError):
        verify_webhook_signature(
            payload,
            timestamp=timestamp,
            signature=signature,
            settings=settings,
            now_epoch=int(timestamp) + settings.email_webhook_max_age_seconds + 1,
        )


def test_email_attachment_is_ingested_queued_audited_and_idempotent(
    session: Session, seeded, tmp_path
) -> None:
    organization, _, _ = seeded
    settings = email_settings(tmp_path)
    create_mailbox(session, organization.id, allowed_sender_domains=["trusted.example"])
    service = intake_service(session, tmp_path, settings)
    payload = raw_email(attachment=pdf_bytes())

    result = service.ingest_raw(
        payload,
        provider="test",
        provider_message_id="provider-1048",
        correlation_id="email-test-1",
    )

    assert result.duplicate is False
    assert result.message.status == "PROCESSED"
    assert result.message.accepted_count == 1
    assert len(result.job_ids) == 1
    attachment = result.message.attachments[0]
    assert attachment.status == "ACCEPTED"
    document = session.get(Document, attachment.document_id)
    assert document is not None
    assert document.source_type == "EMAIL_ATTACHMENT"
    assert document.uploaded_by is None
    assert document.validation_summary["email_id"] == result.message.id
    assert session.scalar(select(func.count()).select_from(DocumentProcessingJob)) == 1
    assert session.scalar(
        select(func.count())
        .select_from(AuditLog)
        .where(AuditLog.action == "email.received")
    ) == 1
    assert session.scalar(
        select(func.count())
        .select_from(OutboxEvent)
        .where(OutboxEvent.event_type == "email.received")
    ) == 1

    replay = service.ingest_raw(
        payload,
        provider="test",
        provider_message_id="provider-1048",
        correlation_id="email-test-2",
    )
    assert replay.duplicate is True
    assert replay.message.id == result.message.id
    assert replay.job_ids == ()
    assert session.scalar(select(func.count()).select_from(InboundEmail)) == 1
    assert session.scalar(select(func.count()).select_from(Document)) == 1

    duplicate_document = service.ingest_raw(
        payload,
        provider="test",
        provider_message_id="provider-1049",
        correlation_id="email-test-3",
    )
    assert duplicate_document.message.status == "PROCESSED"
    assert duplicate_document.message.duplicate_count == 1
    assert duplicate_document.message.attachments[0].document_id == document.id
    assert session.scalar(select(func.count()).select_from(Document)) == 1


def test_disallowed_sender_is_rejected_without_storing_attachment(
    session: Session, seeded, tmp_path
) -> None:
    organization, _, _ = seeded
    settings = email_settings(tmp_path)
    create_mailbox(session, organization.id, allowed_sender_domains=["trusted.example"])
    service = intake_service(session, tmp_path, settings)

    result = service.ingest_raw(
        raw_email(sender="attacker@untrusted.example", attachment=pdf_bytes()),
        provider="test",
        provider_message_id="blocked-sender",
        correlation_id="email-test-4",
    )

    assert result.message.status == "REJECTED"
    assert result.message.rejected_count == 1
    assert result.message.error_summary["codes"] == ["SENDER_DOMAIN_NOT_ALLOWED"]
    assert session.scalar(select(func.count()).select_from(Document)) == 0
    review = session.scalar(
        select(ReviewTask).where(ReviewTask.entity_id == result.message.id)
    )
    assert review is not None
    assert review.reason_code == "SENDER_DOMAIN_NOT_ALLOWED"


def test_signed_inbound_api_and_tenant_scoped_message_list(
    client, session: Session, seeded, tmp_path, monkeypatch
) -> None:
    organization, _, _ = seeded
    settings = email_settings(tmp_path)
    create_mailbox(session, organization.id)
    storage = LocalObjectStorage(tmp_path / "api-objects")
    monkeypatch.setattr("app.services.documents.get_object_storage", lambda: storage)
    monkeypatch.setattr(
        "app.services.documents.get_virus_scanner", lambda: DisabledVirusScanner()
    )
    monkeypatch.setattr(
        "app.api.email_intake.dispatch_document_job", lambda _job_id: True
    )
    client.app.dependency_overrides[get_settings] = lambda: settings
    login = client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": "tesztbolt",
            "email": "admin@teszt.hu",
            "password": "Secret-1234!",
        },
    )
    token = login.json()["access_token"]
    payload = raw_email(attachment=pdf_bytes())
    timestamp = str(int(time.time()))
    signature = hmac.new(
        b"test-email-webhook-secret",
        f"{timestamp}.".encode() + payload,
        sha256,
    ).hexdigest()

    inbound = client.post(
        "/api/v1/email/inbound",
        content=payload,
        headers={
            "Content-Type": "message/rfc822",
            "X-Inbound-Timestamp": timestamp,
            "X-Inbound-Signature": f"sha256={signature}",
            "X-Inbound-Provider": "test-webhook",
            "X-Provider-Message-ID": "api-message-1",
        },
    )
    assert inbound.status_code == 202
    assert inbound.json()["message"]["accepted_count"] == 1
    assert inbound.json()["queued_job_count"] == 1

    unauthorized = client.post(
        "/api/v1/email/inbound",
        content=payload,
        headers={
            "Content-Type": "message/rfc822",
            "X-Inbound-Timestamp": timestamp,
            "X-Inbound-Signature": "sha256=" + ("0" * 64),
        },
    )
    assert unauthorized.status_code == 401

    authenticated_headers = {"Authorization": f"Bearer {token}"}
    settings_response = client.get(
        "/api/v1/email/settings", headers=authenticated_headers
    )
    assert settings_response.status_code == 200
    assert settings_response.json()["inbound_address"] == (
        f"documents+{ROUTING_TOKEN}@mail.example.test"
    )
    messages = client.get("/api/v1/email/messages", headers=authenticated_headers)
    assert messages.status_code == 200
    assert len(messages.json()) == 1
    client.app.dependency_overrides.pop(get_settings, None)


class FakeImap:
    def __init__(self, raw_message: bytes):
        self.raw_message = raw_message
        self.seen: list[bytes] = []

    def login(self, _username: str, _password: str):
        return "OK", []

    def select(self, _mailbox: str):
        return "OK", [b"1"]

    def uid(self, command: str, uid, *args):
        if command == "search":
            return "OK", [b"42"]
        if command == "fetch":
            return "OK", [(b"42 (RFC822)", self.raw_message)]
        if command == "store":
            self.seen.append(uid)
            return "OK", []
        raise AssertionError(command)

    def logout(self):
        return "BYE", []


def test_imap_worker_persists_before_marking_seen(
    session_factory, session: Session, seeded, tmp_path, monkeypatch
) -> None:
    organization, _, _ = seeded
    create_mailbox(session, organization.id)
    settings = email_settings(
        tmp_path,
        email_imap_enabled=True,
        email_imap_host="imap.example.test",
        email_imap_username="documents@example.test",
        email_imap_password="imap-secret",
    )
    storage = LocalObjectStorage(tmp_path / "imap-objects")
    monkeypatch.setattr("app.services.documents.get_object_storage", lambda: storage)
    monkeypatch.setattr(
        "app.services.documents.get_virus_scanner", lambda: DisabledVirusScanner()
    )
    monkeypatch.setattr("app.email_imap.dispatch_document_job", lambda _job_id: True)
    fake = FakeImap(raw_email(attachment=pdf_bytes()))

    processed = poll_imap_once(
        settings=settings,
        session_factory=session_factory,
        imap_factory=lambda *_args: fake,
    )

    assert processed == 1
    assert fake.seen == [b"42"]
    assert session.scalar(select(func.count()).select_from(InboundEmail)) == 1
