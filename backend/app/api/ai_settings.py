from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Header

from app.dependencies import AppSettings, CurrentUser, DbSession, require_permissions
from app.schemas import AiSettingsRead, AiSettingsUpdate
from app.services.ai_settings import AiSettingsService, AiSettingsSnapshot

router = APIRouter(prefix="/ai/settings", tags=["AI settings"])
AiSettingsReader = Annotated[
    object, Depends(require_permissions("settings.read"))
]
AiSettingsWriter = Annotated[
    object, Depends(require_permissions("settings.write"))
]


def _correlation_id(value: str | None) -> str:
    return value or str(uuid4())


def _read(snapshot: AiSettingsSnapshot) -> AiSettingsRead:
    return AiSettingsRead(
        organization_id=snapshot.organization_id,
        provider=snapshot.provider,
        base_url=snapshot.base_url,
        model=snapshot.model,
        api_key_configured=snapshot.api_key_configured,
        api_key_source=snapshot.api_key_source,
        api_key_hint=snapshot.api_key_hint,
        provider_enabled=snapshot.provider_enabled,
        updated_by=snapshot.updated_by,
        updated_at=snapshot.updated_at,
    )


@router.get("", response_model=AiSettingsRead)
def get_ai_settings(
    session: DbSession,
    user: CurrentUser,
    _: AiSettingsReader,
    app_settings: AppSettings,
) -> AiSettingsRead:
    service = AiSettingsService(session, settings=app_settings)
    return _read(service.snapshot(user.organization_id))


@router.put("", response_model=AiSettingsRead)
def update_ai_settings(
    payload: AiSettingsUpdate,
    session: DbSession,
    user: CurrentUser,
    _: AiSettingsWriter,
    app_settings: AppSettings,
    correlation_header: Annotated[
        str | None, Header(alias="X-Correlation-ID")
    ] = None,
) -> AiSettingsRead:
    service = AiSettingsService(session, settings=app_settings)
    return _read(
        service.update_api_key(
            user=user,
            api_key=payload.api_key,
            correlation_id=_correlation_id(correlation_header),
        )
    )


@router.delete("", response_model=AiSettingsRead)
def clear_ai_settings(
    session: DbSession,
    user: CurrentUser,
    _: AiSettingsWriter,
    app_settings: AppSettings,
    correlation_header: Annotated[
        str | None, Header(alias="X-Correlation-ID")
    ] = None,
) -> AiSettingsRead:
    service = AiSettingsService(session, settings=app_settings)
    return _read(
        service.clear_api_key(
            user=user,
            correlation_id=_correlation_id(correlation_header),
        )
    )
