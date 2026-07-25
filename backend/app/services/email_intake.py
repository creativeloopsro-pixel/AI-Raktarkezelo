from __future__ import annotations

import hmac
import re
import time
from dataclasses import dataclass
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import getaddresses, parseaddr
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from secrets import token_hex

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.config import Settings, get_settings
from app.models import (
    AuditLog,
    EmailInboundSettings,
    InboundEmail,
    InboundEmailAttachment,
    OutboxEvent,
    ReviewTask,
    User,
    utc_now,
)
from app.services.documents import (
    DocumentError,
    DocumentService,
    DuplicateDocumentError,
)

FINAL_EMAIL_STATUSES = {"PROCESSED", "PARTIAL", "REJECTED"}
ROUTING_ADDRESS = re.compile(
    r"^documents\+(?P<token>[a-f0-9]{24})@(?P<domain>[^@\s]+)$",
    re.IGNORECASE,
)
PROVIDER_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
DOMAIN_NAME = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$",
    re.IGNORECASE,
)


class EmailIntakeError(Exception):
    code = "email_intake_error"


class EmailWebhookDisabledError(EmailIntakeError):
    code = "email_webhook_disabled"


class EmailSignatureError(EmailIntakeError):
    code = "invalid_email_signature"


class EmailReplayWindowError(EmailIntakeError):
    code = "email_replay_window_exceeded"


class EmailMessageTooLargeError(EmailIntakeError):
    code = "email_message_too_large"


class InvalidEmailMessageError(EmailIntakeError):
    code = "invalid_email_message"


class UnknownInboundRecipientError(EmailIntakeError):
    code = "unknown_inbound_recipient"


class AmbiguousInboundRecipientError(EmailIntakeError):
    code = "ambiguous_inbound_recipient"


class InvalidSenderDomainError(EmailIntakeError):
    code = "invalid_sender_domain"


@dataclass(frozen=True)
class EmailIngestionResult:
    message: InboundEmail
    duplicate: bool
    job_ids: tuple[str, ...]


def normalize_domain(value: str) -> str:
    domain = value.strip().lower().rstrip(".")
    if not DOMAIN_NAME.fullmatch(domain):
        raise InvalidSenderDomainError
    return domain


def verify_webhook_signature(
    raw_message: bytes,
    *,
    timestamp: str | None,
    signature: str | None,
    settings: Settings | None = None,
    now_epoch: int | None = None,
) -> None:
    active_settings = settings or get_settings()
    secret = active_settings.email_webhook_secret.get_secret_value()
    if not secret:
        raise EmailWebhookDisabledError
    try:
        signed_at = int(timestamp or "")
    except ValueError as exc:
        raise EmailSignatureError from exc
    current = int(time.time()) if now_epoch is None else now_epoch
    if abs(current - signed_at) > active_settings.email_webhook_max_age_seconds:
        raise EmailReplayWindowError
    supplied = (signature or "").removeprefix("sha256=").strip().lower()
    expected = hmac.new(
        secret.encode("utf-8"),
        f"{signed_at}.".encode("ascii") + raw_message,
        sha256,
    ).hexdigest()
    if len(supplied) != len(expected) or not hmac.compare_digest(supplied, expected):
        raise EmailSignatureError


class EmailIntakeService:
    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
        document_service: DocumentService | None = None,
    ):
        self.session = session
        self.settings = settings or get_settings()
        self.document_service = document_service or DocumentService(
            session, settings=self.settings
        )

    def inbound_address(self, inbound: EmailInboundSettings) -> str:
        domain = self.settings.email_inbound_domain.strip().lower().lstrip("@")
        return f"documents+{inbound.routing_token}@{domain}"

    def get_settings(self, organization_id: str) -> EmailInboundSettings:
        inbound = self.session.get(EmailInboundSettings, organization_id)
        if inbound is None:
            inbound = EmailInboundSettings(organization_id=organization_id)
            self.session.add(inbound)
            self.session.commit()
            self.session.refresh(inbound)
        return inbound

    def update_settings(
        self,
        *,
        user: User,
        enabled: bool,
        auto_process: bool,
        allowed_sender_domains: list[str],
        correlation_id: str,
    ) -> EmailInboundSettings:
        inbound = self.get_settings(user.organization_id)
        normalized_domains = sorted(
            {normalize_domain(domain) for domain in allowed_sender_domains if domain.strip()}
        )
        inbound.enabled = enabled
        inbound.auto_process = auto_process
        inbound.allowed_sender_domains = normalized_domains
        inbound.updated_by = user.id
        self.session.add(
            AuditLog(
                organization_id=user.organization_id,
                actor_id=user.id,
                action="email.settings_updated",
                entity_type="email_inbound_settings",
                entity_id=user.organization_id,
                correlation_id=correlation_id,
                details={
                    "enabled": enabled,
                    "auto_process": auto_process,
                    "allowed_sender_domains": normalized_domains,
                },
            )
        )
        self.session.add(
            OutboxEvent(
                organization_id=user.organization_id,
                event_type="email.settings.updated",
                aggregate_type="email_inbound_settings",
                aggregate_id=user.organization_id,
                payload={"correlation_id": correlation_id},
            )
        )
        self.session.commit()
        self.session.refresh(inbound)
        return inbound

    def rotate_address(
        self,
        *,
        user: User,
        correlation_id: str,
    ) -> EmailInboundSettings:
        inbound = self.get_settings(user.organization_id)
        previous_suffix = inbound.routing_token[-4:]
        inbound.routing_token = token_hex(12)
        inbound.updated_by = user.id
        self.session.add(
            AuditLog(
                organization_id=user.organization_id,
                actor_id=user.id,
                action="email.address_rotated",
                entity_type="email_inbound_settings",
                entity_id=user.organization_id,
                correlation_id=correlation_id,
                details={"previous_token_suffix": previous_suffix},
            )
        )
        self.session.add(
            OutboxEvent(
                organization_id=user.organization_id,
                event_type="email.address.rotated",
                aggregate_type="email_inbound_settings",
                aggregate_id=user.organization_id,
                payload={"correlation_id": correlation_id},
            )
        )
        self.session.commit()
        self.session.refresh(inbound)
        return inbound

    def list_messages(
        self,
        organization_id: str,
        *,
        limit: int = 100,
    ) -> list[InboundEmail]:
        return list(
            self.session.scalars(
                select(InboundEmail)
                .where(InboundEmail.organization_id == organization_id)
                .options(selectinload(InboundEmail.attachments))
                .order_by(InboundEmail.received_at.desc())
                .limit(limit)
            ).unique()
        )

    def get_message(
        self, organization_id: str, message_id: str
    ) -> InboundEmail | None:
        return self.session.scalar(
            select(InboundEmail)
            .where(
                InboundEmail.id == message_id,
                InboundEmail.organization_id == organization_id,
            )
            .options(selectinload(InboundEmail.attachments))
        )

    def ingest_raw(
        self,
        raw_message: bytes,
        *,
        provider: str,
        provider_message_id: str | None,
        correlation_id: str,
    ) -> EmailIngestionResult:
        max_bytes = self.settings.email_max_message_mb * 1024 * 1024
        if not raw_message or len(raw_message) > max_bytes:
            raise EmailMessageTooLargeError

        normalized_provider = provider.strip().lower()
        if not PROVIDER_NAME.fullmatch(normalized_provider):
            raise InvalidEmailMessageError
        try:
            parsed = BytesParser(policy=policy.default).parsebytes(raw_message)
        except Exception as exc:
            raise InvalidEmailMessageError from exc
        if not isinstance(parsed, EmailMessage):
            raise InvalidEmailMessageError

        recipients = self._recipients(parsed)
        inbound = self._resolve_settings(recipients)
        sender = parseaddr(str(parsed.get("From", "")))[1].strip().lower()[:254]
        message_key = (
            (provider_message_id or "").strip()
            or str(parsed.get("Message-ID", "")).strip()
            or f"sha256:{sha256(raw_message).hexdigest()}"
        )[:255]

        existing = self.session.scalar(
            select(InboundEmail)
            .where(
                InboundEmail.organization_id == inbound.organization_id,
                InboundEmail.provider == normalized_provider,
                InboundEmail.provider_message_id == message_key,
            )
            .options(selectinload(InboundEmail.attachments))
        )
        duplicate = existing is not None
        if existing is not None and existing.status in FINAL_EMAIL_STATUSES:
            return EmailIngestionResult(
                message=existing,
                duplicate=True,
                job_ids=(),
            )

        if existing is None:
            message = InboundEmail(
                organization_id=inbound.organization_id,
                provider=normalized_provider,
                provider_message_id=message_key,
                sender=sender,
                recipients=recipients[:50],
                subject=str(parsed.get("Subject", ""))[:500],
                status="PROCESSING",
            )
            self.session.add(message)
            self.session.commit()
            self.session.refresh(message)
        else:
            message = existing

        parts = self._attachment_parts(parsed)
        message.attachment_count = len(parts)
        if not self._sender_allowed(sender, inbound.allowed_sender_domains):
            self._reject_sender(message, sender, correlation_id)
            return EmailIngestionResult(message=message, duplicate=duplicate, job_ids=())

        job_ids: list[str] = []
        processing_parts = parts[: self.settings.email_max_attachments]
        for position, part in enumerate(processing_parts, start=1):
            already_recorded = self.session.scalar(
                select(InboundEmailAttachment).where(
                    InboundEmailAttachment.email_id == message.id,
                    InboundEmailAttachment.position == position,
                )
            )
            if already_recorded is not None:
                continue
            payload = part.get_payload(decode=True) or b""
            filename = self._safe_filename(part.get_filename(), position)
            declared_content_type = part.get_content_type()
            content_hash = sha256(payload).hexdigest()
            attachment_status = "REJECTED"
            rejection_code: str | None = None
            document_id: str | None = None
            try:
                document = self.document_service.ingest(
                    organization_id=inbound.organization_id,
                    actor_id=None,
                    stream=BytesIO(payload),
                    filename=filename,
                    declared_content_type=declared_content_type,
                    document_type="goods_receipt",
                    source_type="EMAIL_ATTACHMENT",
                    correlation_id=correlation_id,
                    source_metadata={
                        "email_id": message.id,
                        "sender": sender,
                        "subject": message.subject,
                        "provider": normalized_provider,
                    },
                )
                attachment_status = "ACCEPTED"
                document_id = document.id
                if inbound.auto_process and document.status == "UPLOADED":
                    queued = self.document_service.queue_processing(
                        organization_id=inbound.organization_id,
                        actor_id=None,
                        document_id=document.id,
                        idempotency_key=f"email:{message.id}:{position}",
                        correlation_id=correlation_id,
                    )
                    if queued.created:
                        job_ids.append(queued.job.id)
            except DuplicateDocumentError as exc:
                self.session.rollback()
                attachment_status = "DUPLICATE"
                document_id = exc.existing_document_id
                rejection_code = exc.code
            except DocumentError as exc:
                self.session.rollback()
                rejection_code = exc.code
            except Exception:
                self.session.rollback()
                rejection_code = "attachment_processing_failed"

            self.session.add(
                InboundEmailAttachment(
                    organization_id=inbound.organization_id,
                    email_id=message.id,
                    position=position,
                    filename=filename,
                    declared_content_type=declared_content_type,
                    size_bytes=len(payload),
                    content_sha256=content_hash,
                    status=attachment_status,
                    document_id=document_id,
                    rejection_code=rejection_code,
                )
            )
            self.session.commit()

        overflow = max(0, len(parts) - self.settings.email_max_attachments)
        self._finalize_message(message, overflow=overflow, correlation_id=correlation_id)
        return EmailIngestionResult(
            message=self.get_message(inbound.organization_id, message.id) or message,
            duplicate=duplicate,
            job_ids=tuple(job_ids),
        )

    def _resolve_settings(self, recipients: list[str]) -> EmailInboundSettings:
        expected_domain = self.settings.email_inbound_domain.strip().lower().lstrip("@")
        tokens = {
            match.group("token").lower()
            for recipient in recipients
            if (match := ROUTING_ADDRESS.fullmatch(recipient))
            and match.group("domain").lower() == expected_domain
        }
        if not tokens:
            raise UnknownInboundRecipientError
        mailboxes = list(
            self.session.scalars(
                select(EmailInboundSettings).where(
                    EmailInboundSettings.routing_token.in_(tokens),
                    EmailInboundSettings.enabled.is_(True),
                )
            )
        )
        if not mailboxes:
            raise UnknownInboundRecipientError
        if len(mailboxes) != 1:
            raise AmbiguousInboundRecipientError
        return mailboxes[0]

    @staticmethod
    def _recipients(message: EmailMessage) -> list[str]:
        values: list[str] = []
        for header in ("To", "Cc", "Delivered-To", "X-Original-To", "Envelope-To"):
            values.extend(str(value) for value in message.get_all(header, []))
        return sorted(
            {
                address.strip().lower()
                for _, address in getaddresses(values)
                if address.strip()
            }
        )

    @staticmethod
    def _attachment_parts(message: EmailMessage) -> list[EmailMessage]:
        parts: list[EmailMessage] = []
        for part in message.walk():
            if part.is_multipart():
                continue
            disposition = part.get_content_disposition()
            if disposition == "attachment" or part.get_filename():
                parts.append(part)
        return parts

    @staticmethod
    def _safe_filename(filename: str | None, position: int) -> str:
        normalized = (filename or f"attachment-{position}").replace("\\", "/")
        return Path(normalized).name[:255] or f"attachment-{position}"

    @staticmethod
    def _sender_allowed(sender: str, allowed_domains: list[str]) -> bool:
        if not sender or "@" not in sender:
            return False
        if not allowed_domains:
            return True
        sender_domain = sender.rsplit("@", 1)[1].lower().rstrip(".")
        return any(
            sender_domain == domain or sender_domain.endswith(f".{domain}")
            for domain in allowed_domains
        )

    def _reject_sender(
        self,
        message: InboundEmail,
        sender: str,
        correlation_id: str,
    ) -> None:
        message.status = "REJECTED"
        message.rejected_count = message.attachment_count
        message.error_summary = {"codes": ["SENDER_DOMAIN_NOT_ALLOWED"]}
        message.processed_at = utc_now()
        self.session.add(
            ReviewTask(
                organization_id=message.organization_id,
                task_type="EMAIL_INTAKE_FAILURE",
                entity_type="inbound_email",
                entity_id=message.id,
                reason_code="SENDER_DOMAIN_NOT_ALLOWED",
                context={"sender": sender, "subject": message.subject},
            )
        )
        self._add_completion_events(message, correlation_id)
        self.session.commit()
        self.session.refresh(message)

    def _finalize_message(
        self,
        message: InboundEmail,
        *,
        overflow: int,
        correlation_id: str,
    ) -> None:
        counts = dict(
            self.session.execute(
                select(
                    InboundEmailAttachment.status,
                    func.count(InboundEmailAttachment.id),
                )
                .where(InboundEmailAttachment.email_id == message.id)
                .group_by(InboundEmailAttachment.status)
            ).all()
        )
        message.accepted_count = int(counts.get("ACCEPTED", 0))
        message.duplicate_count = int(counts.get("DUPLICATE", 0))
        message.rejected_count = int(counts.get("REJECTED", 0)) + overflow
        codes = list(
            self.session.scalars(
                select(InboundEmailAttachment.rejection_code)
                .where(
                    InboundEmailAttachment.email_id == message.id,
                    InboundEmailAttachment.rejection_code.is_not(None),
                )
                .distinct()
            )
        )
        if overflow:
            codes.append("ATTACHMENT_LIMIT_EXCEEDED")
        if not message.attachment_count:
            codes.append("NO_ATTACHMENTS")
        message.error_summary = {"codes": sorted(set(codes))}
        if message.rejected_count:
            message.status = (
                "PARTIAL"
                if message.accepted_count or message.duplicate_count
                else "REJECTED"
            )
        elif message.accepted_count or message.duplicate_count:
            message.status = "PROCESSED"
        else:
            message.status = "REJECTED"
        message.processed_at = utc_now()

        if message.status in {"PARTIAL", "REJECTED"}:
            reason_code = message.error_summary["codes"][0]
            self.session.add(
                ReviewTask(
                    organization_id=message.organization_id,
                    task_type="EMAIL_INTAKE_FAILURE",
                    entity_type="inbound_email",
                    entity_id=message.id,
                    reason_code=reason_code,
                    context={
                        "sender": message.sender,
                        "subject": message.subject,
                        "errors": message.error_summary["codes"],
                    },
                )
            )
        self._add_completion_events(message, correlation_id)
        self.session.commit()
        self.session.refresh(message)

    def _add_completion_events(
        self, message: InboundEmail, correlation_id: str
    ) -> None:
        existing_audit = self.session.scalar(
            select(AuditLog.id).where(
                AuditLog.organization_id == message.organization_id,
                AuditLog.action == "email.received",
                AuditLog.entity_type == "inbound_email",
                AuditLog.entity_id == message.id,
            )
        )
        if existing_audit is not None:
            return
        details = {
            "provider": message.provider,
            "sender": message.sender,
            "status": message.status,
            "attachment_count": message.attachment_count,
            "accepted_count": message.accepted_count,
            "duplicate_count": message.duplicate_count,
            "rejected_count": message.rejected_count,
        }
        self.session.add(
            AuditLog(
                organization_id=message.organization_id,
                actor_id=None,
                action="email.received",
                entity_type="inbound_email",
                entity_id=message.id,
                correlation_id=correlation_id,
                details=details,
            )
        )
        self.session.add(
            OutboxEvent(
                organization_id=message.organization_id,
                event_type="email.received",
                aggregate_type="inbound_email",
                aggregate_id=message.id,
                payload={**details, "correlation_id": correlation_id},
            )
        )
