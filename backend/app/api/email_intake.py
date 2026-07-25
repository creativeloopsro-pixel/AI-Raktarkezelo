from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status

from app.config import Settings
from app.dependencies import AppSettings, CurrentUser, DbSession, require_roles
from app.models import EmailInboundSettings, InboundEmail
from app.queueing import dispatch_document_job
from app.schemas import (
    EmailInboundSettingsRead,
    EmailInboundSettingsUpdate,
    InboundEmailRead,
    InboundEmailReceipt,
)
from app.services.email_intake import (
    AmbiguousInboundRecipientError,
    EmailIntakeError,
    EmailIntakeService,
    EmailMessageTooLargeError,
    EmailReplayWindowError,
    EmailSignatureError,
    EmailWebhookDisabledError,
    InvalidEmailMessageError,
    InvalidSenderDomainError,
    UnknownInboundRecipientError,
    verify_webhook_signature,
)

router = APIRouter(prefix="/email", tags=["email intake"])
EmailOperator = Annotated[
    object, Depends(require_roles("admin", "manager", "warehouse"))
]
EmailManager = Annotated[object, Depends(require_roles("admin", "manager"))]
EmailAdmin = Annotated[object, Depends(require_roles("admin"))]


def _correlation_id(value: str | None) -> str:
    return value or str(uuid4())


def _settings_read(
    inbound: EmailInboundSettings,
    *,
    app_settings: Settings,
    service: EmailIntakeService,
) -> EmailInboundSettingsRead:
    return EmailInboundSettingsRead(
        organization_id=inbound.organization_id,
        inbound_address=service.inbound_address(inbound),
        enabled=inbound.enabled,
        auto_process=inbound.auto_process,
        allowed_sender_domains=inbound.allowed_sender_domains,
        webhook_configured=bool(
            app_settings.email_webhook_secret.get_secret_value()
        ),
        imap_enabled=app_settings.email_imap_enabled,
        updated_by=inbound.updated_by,
        created_at=inbound.created_at,
        updated_at=inbound.updated_at,
    )


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, EmailWebhookDisabledError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": exc.code,
                "message": "Az e-mail webhook nincs konfigurálva.",
            },
        )
    if isinstance(exc, (EmailSignatureError, EmailReplayWindowError)):
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": exc.code,
                "message": "Az inbound e-mail aláírása érvénytelen vagy lejárt.",
            },
        )
    if isinstance(exc, EmailMessageTooLargeError):
        return HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail={"code": exc.code, "message": "A bejövő e-mail túl nagy."},
        )
    if isinstance(
        exc, (UnknownInboundRecipientError, AmbiguousInboundRecipientError)
    ):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": exc.code,
                "message": "A bejövő dokumentumcím nem található vagy nem egyértelmű.",
            },
        )
    if isinstance(exc, (InvalidEmailMessageError, InvalidSenderDomainError)):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": exc.code, "message": "Az e-mail adatai érvénytelenek."},
        )
    code = getattr(exc, "code", "email_operation_failed")
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"code": code, "message": "Az e-mail művelet sikertelen."},
    )


@router.get("/settings", response_model=EmailInboundSettingsRead)
def get_email_settings(
    session: DbSession,
    user: CurrentUser,
    _: EmailOperator,
    app_settings: AppSettings,
) -> EmailInboundSettingsRead:
    service = EmailIntakeService(session, settings=app_settings)
    inbound = service.get_settings(user.organization_id)
    return _settings_read(inbound, app_settings=app_settings, service=service)


@router.put("/settings", response_model=EmailInboundSettingsRead)
def update_email_settings(
    payload: EmailInboundSettingsUpdate,
    session: DbSession,
    user: CurrentUser,
    _: EmailManager,
    app_settings: AppSettings,
    correlation_header: Annotated[
        str | None, Header(alias="X-Correlation-ID")
    ] = None,
) -> EmailInboundSettingsRead:
    service = EmailIntakeService(session, settings=app_settings)
    try:
        inbound = service.update_settings(
            user=user,
            enabled=payload.enabled,
            auto_process=payload.auto_process,
            allowed_sender_domains=payload.allowed_sender_domains,
            correlation_id=_correlation_id(correlation_header),
        )
        return _settings_read(inbound, app_settings=app_settings, service=service)
    except EmailIntakeError as exc:
        session.rollback()
        raise _map_error(exc) from exc


@router.post("/settings/rotate-address", response_model=EmailInboundSettingsRead)
def rotate_email_address(
    session: DbSession,
    user: CurrentUser,
    _: EmailAdmin,
    app_settings: AppSettings,
    correlation_header: Annotated[
        str | None, Header(alias="X-Correlation-ID")
    ] = None,
) -> EmailInboundSettingsRead:
    service = EmailIntakeService(session, settings=app_settings)
    inbound = service.rotate_address(
        user=user,
        correlation_id=_correlation_id(correlation_header),
    )
    return _settings_read(inbound, app_settings=app_settings, service=service)


@router.get("/messages", response_model=list[InboundEmailRead])
def list_inbound_messages(
    session: DbSession,
    user: CurrentUser,
    _: EmailOperator,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[InboundEmail]:
    return EmailIntakeService(session).list_messages(
        user.organization_id, limit=limit
    )


@router.get("/messages/{message_id}", response_model=InboundEmailRead)
def get_inbound_message(
    message_id: str,
    session: DbSession,
    user: CurrentUser,
    _: EmailOperator,
) -> InboundEmail:
    message = EmailIntakeService(session).get_message(
        user.organization_id, message_id
    )
    if message is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "inbound_email_not_found",
                "message": "A bejövő e-mail nem található.",
            },
        )
    return message


@router.post(
    "/inbound",
    response_model=InboundEmailReceipt,
    status_code=status.HTTP_202_ACCEPTED,
)
async def receive_inbound_email(
    request: Request,
    session: DbSession,
    app_settings: AppSettings,
    timestamp: Annotated[str | None, Header(alias="X-Inbound-Timestamp")] = None,
    signature: Annotated[str | None, Header(alias="X-Inbound-Signature")] = None,
    provider: Annotated[
        str, Header(alias="X-Inbound-Provider", max_length=40)
    ] = "webhook",
    provider_message_id: Annotated[
        str | None, Header(alias="X-Provider-Message-ID", max_length=255)
    ] = None,
    correlation_header: Annotated[
        str | None, Header(alias="X-Correlation-ID")
    ] = None,
) -> InboundEmailReceipt:
    content_length = request.headers.get("content-length")
    max_bytes = app_settings.email_max_message_mb * 1024 * 1024
    if content_length and content_length.isdigit() and int(content_length) > max_bytes:
        raise _map_error(EmailMessageTooLargeError())
    raw_message = await request.body()
    try:
        verify_webhook_signature(
            raw_message,
            timestamp=timestamp,
            signature=signature,
            settings=app_settings,
        )
        result = EmailIntakeService(session, settings=app_settings).ingest_raw(
            raw_message,
            provider=provider,
            provider_message_id=provider_message_id,
            correlation_id=_correlation_id(correlation_header),
        )
        for job_id in result.job_ids:
            dispatch_document_job(job_id)
        return InboundEmailReceipt(
            message=InboundEmailRead.model_validate(result.message),
            duplicate=result.duplicate,
            queued_job_count=len(result.job_ids),
        )
    except EmailIntakeError as exc:
        session.rollback()
        raise _map_error(exc) from exc
