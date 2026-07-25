from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from app.dependencies import CurrentUser, DbSession, require_permissions
from app.models import Plugin
from app.plugins.manifest import PluginManifest
from app.schemas import (
    PluginJobRead,
    PluginOverview,
    PluginPermissionRead,
    PluginPermissionUpdate,
    PluginRead,
    PluginSettingRead,
    PluginSettingsUpdate,
)
from app.services.plugins import (
    BuiltinPluginProtectedError,
    PluginApiVersionError,
    PluginEnableError,
    PluginHandlerMissingError,
    PluginManifestError,
    PluginNotFoundError,
    PluginPermissionError,
    PluginService,
    PluginServiceError,
    PluginSettingError,
)

router = APIRouter(prefix="/plugins", tags=["plugins"])
PluginViewer = Annotated[object, Depends(require_permissions("plugins.read"))]
PluginAdmin = Annotated[object, Depends(require_permissions("plugins.manage"))]


def _correlation_id(value: str | None) -> str:
    return value or str(uuid4())


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, PluginNotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": "A plugin nem található."},
        )
    if isinstance(exc, (PluginManifestError, PluginPermissionError, PluginSettingError)):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": exc.code,
                "message": "A plugin manifestje, jogosultsága vagy beállítása érvénytelen.",
            },
        )
    if isinstance(exc, PluginApiVersionError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": exc.code,
                "message": "A plugin API-verziója nem támogatott.",
            },
        )
    if isinstance(exc, PluginHandlerMissingError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": exc.code,
                "message": "A deklarált eseményhez nincs telepített szerveroldali handler.",
            },
        )
    if isinstance(exc, PluginEnableError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": exc.code,
                "message": (
                    "A plugin csak minden deklarált jogosultság megadása "
                    "után engedélyezhető."
                ),
            },
        )
    if isinstance(exc, BuiltinPluginProtectedError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": exc.code,
                "message": "A beépített plugin manifestje nem írható felül.",
            },
        )
    code = getattr(exc, "code", "plugin_operation_failed")
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"code": code, "message": "A plugin művelet sikertelen."},
    )


def _plugin_read(service: PluginService, plugin: Plugin) -> PluginRead:
    manifest = service.manifest_for(plugin)
    return PluginRead(
        id=plugin.id,
        organization_id=plugin.organization_id,
        plugin_key=plugin.plugin_key,
        name=plugin.name,
        description=plugin.description,
        status=plugin.status,
        active_version=plugin.active_version,
        api_version=manifest.api_version,
        is_builtin=plugin.is_builtin,
        manifest=manifest.model_dump(mode="json"),
        permissions=[
            PluginPermissionRead.model_validate(permission)
            for permission in sorted(
                plugin.permissions, key=lambda item: item.permission
            )
        ],
        settings=[
            PluginSettingRead(
                key=setting.setting_key,
                value="********" if setting.is_secret else setting.value,
                is_secret=setting.is_secret,
                updated_at=setting.updated_at,
            )
            for setting in sorted(
                plugin.settings, key=lambda item: item.setting_key
            )
        ],
        installed_at=plugin.installed_at,
        updated_at=plugin.updated_at,
        enabled_at=plugin.enabled_at,
        disabled_at=plugin.disabled_at,
    )


@router.get("", response_model=PluginOverview)
def list_plugins(
    session: DbSession,
    user: CurrentUser,
    _: PluginViewer,
) -> PluginOverview:
    service = PluginService(session)
    plugins = service.list_plugins(user.organization_id)
    return PluginOverview(
        plugins=[_plugin_read(service, plugin) for plugin in plugins],
        job_counts=service.job_counts(user.organization_id),
    )


@router.post(
    "/install",
    response_model=PluginRead,
    status_code=status.HTTP_201_CREATED,
)
def install_plugin(
    manifest: PluginManifest,
    session: DbSession,
    user: CurrentUser,
    _: PluginAdmin,
    correlation_header: Annotated[
        str | None, Header(alias="X-Correlation-ID")
    ] = None,
) -> PluginRead:
    service = PluginService(session)
    try:
        plugin = service.install_manifest(
            user=user,
            manifest_payload=manifest.model_dump(mode="json"),
            correlation_id=_correlation_id(correlation_header),
        )
        return _plugin_read(service, plugin)
    except PluginServiceError as exc:
        session.rollback()
        raise _map_error(exc) from exc


@router.put("/{plugin_id}/permissions", response_model=PluginRead)
def update_plugin_permissions(
    plugin_id: str,
    payload: PluginPermissionUpdate,
    session: DbSession,
    user: CurrentUser,
    _: PluginAdmin,
    correlation_header: Annotated[
        str | None, Header(alias="X-Correlation-ID")
    ] = None,
) -> PluginRead:
    service = PluginService(session)
    try:
        plugin = service.set_permissions(
            user=user,
            plugin_id=plugin_id,
            granted_permissions=payload.granted_permissions,
            correlation_id=_correlation_id(correlation_header),
        )
        return _plugin_read(service, plugin)
    except PluginServiceError as exc:
        session.rollback()
        raise _map_error(exc) from exc


@router.put("/{plugin_id}/settings", response_model=PluginRead)
def update_plugin_settings(
    plugin_id: str,
    payload: PluginSettingsUpdate,
    session: DbSession,
    user: CurrentUser,
    _: PluginAdmin,
    correlation_header: Annotated[
        str | None, Header(alias="X-Correlation-ID")
    ] = None,
) -> PluginRead:
    service = PluginService(session)
    try:
        plugin = service.update_settings(
            user=user,
            plugin_id=plugin_id,
            values=payload.values,
            correlation_id=_correlation_id(correlation_header),
        )
        return _plugin_read(service, plugin)
    except PluginServiceError as exc:
        session.rollback()
        raise _map_error(exc) from exc


@router.post("/{plugin_id}/enable", response_model=PluginRead)
def enable_plugin(
    plugin_id: str,
    session: DbSession,
    user: CurrentUser,
    _: PluginAdmin,
    correlation_header: Annotated[
        str | None, Header(alias="X-Correlation-ID")
    ] = None,
) -> PluginRead:
    service = PluginService(session)
    try:
        plugin = service.enable(
            user=user,
            plugin_id=plugin_id,
            correlation_id=_correlation_id(correlation_header),
        )
        return _plugin_read(service, plugin)
    except PluginServiceError as exc:
        session.rollback()
        raise _map_error(exc) from exc


@router.post("/{plugin_id}/disable", response_model=PluginRead)
def disable_plugin(
    plugin_id: str,
    session: DbSession,
    user: CurrentUser,
    _: PluginAdmin,
    correlation_header: Annotated[
        str | None, Header(alias="X-Correlation-ID")
    ] = None,
) -> PluginRead:
    service = PluginService(session)
    try:
        plugin = service.disable(
            user=user,
            plugin_id=plugin_id,
            correlation_id=_correlation_id(correlation_header),
        )
        return _plugin_read(service, plugin)
    except PluginServiceError as exc:
        session.rollback()
        raise _map_error(exc) from exc


@router.get("/jobs", response_model=list[PluginJobRead])
def list_plugin_jobs(
    session: DbSession,
    user: CurrentUser,
    _: PluginViewer,
    plugin_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
):
    return PluginService(session).list_jobs(
        user.organization_id, plugin_id=plugin_id, limit=limit
    )
