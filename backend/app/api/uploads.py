from typing import Annotated, Literal

from fastapi import APIRouter, Body, Header, HTTPException, Query, Request, status
from sqlalchemy import select

from app.config import get_settings
from app.dependencies import CurrentUser, DbSession, authorize_permissions
from app.models import Plugin
from app.schemas import (
    ResumableUploadComplete,
    ResumableUploadCreate,
    ResumableUploadRead,
    ResumableUploadResult,
)
from app.services.resumable_uploads import (
    ResumableUploadChunkError,
    ResumableUploadConflictError,
    ResumableUploadError,
    ResumableUploadIncompleteError,
    ResumableUploadIntegrityError,
    ResumableUploadMetadataError,
    ResumableUploadNotFoundError,
    ResumableUploadService,
    ResumableUploadStateError,
)

router = APIRouter(prefix="/uploads", tags=["resumable uploads"])


def _authorize_target(
    request: Request,
    session: DbSession,
    user: CurrentUser,
    target_type: str,
) -> None:
    permission = (
        "documents.upload"
        if target_type.upper() == "DOCUMENT"
        else "vrp.upload"
    )
    authorize_permissions(
        request,
        session,
        get_settings(),
        user,
        permission,
    )
    if target_type.upper() == "VRP":
        plugin = session.scalar(
            select(Plugin).where(
                Plugin.organization_id == user.organization_id,
                Plugin.plugin_key == "vrp-import",
            )
        )
        if plugin is not None and plugin.status != "ENABLED":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "vrp_plugin_disabled",
                    "message": "A VRP plugin jelenleg le van tiltva.",
                },
            )


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, ResumableUploadNotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": exc.code,
                "message": "A feltöltési munkamenet nem található.",
            },
        )
    if isinstance(exc, ResumableUploadConflictError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": exc.code,
                "message": "A feltöltési azonosító vagy fájldarab ütközik.",
            },
        )
    if isinstance(exc, ResumableUploadStateError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": exc.code,
                "message": "A feltöltés jelenlegi állapotában nem módosítható.",
            },
        )
    if isinstance(exc, ResumableUploadIncompleteError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": exc.code,
                "message": "Még nem érkezett meg minden fájldarab.",
            },
        )
    if isinstance(
        exc,
        (
            ResumableUploadChunkError,
            ResumableUploadIntegrityError,
            ResumableUploadMetadataError,
        ),
    ):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": exc.code,
                "message": "A feltöltési metaadat, méret vagy ellenőrzőösszeg hibás.",
            },
        )
    if isinstance(exc, ResumableUploadError):
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": exc.code,
                "message": "A feltöltési művelet sikertelen.",
            },
        )
    code = getattr(exc, "code", "upload_completion_failed")
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail={
            "code": code,
            "message": "A fájl összeállt, de a tartalmi feldolgozása sikertelen.",
        },
    )


@router.post(
    "",
    response_model=ResumableUploadRead,
    status_code=status.HTTP_201_CREATED,
)
def create_upload(
    payload: ResumableUploadCreate,
    request: Request,
    session: DbSession,
    user: CurrentUser,
) -> ResumableUploadRead:
    _authorize_target(request, session, user, payload.target_type)
    try:
        upload = ResumableUploadService(session).create(
            user=user,
            client_upload_id=payload.client_upload_id,
            target_type=payload.target_type,
            filename=payload.filename,
            declared_content_type=payload.declared_content_type,
            total_size=payload.total_size,
            file_sha256=payload.file_sha256,
            metadata=payload.metadata,
            correlation_id=request.state.correlation_id,
        )
        return ResumableUploadRead.model_validate(upload)
    except Exception as exc:
        session.rollback()
        raise _error(exc) from exc


@router.get("", response_model=list[ResumableUploadRead])
def list_uploads(
    request: Request,
    session: DbSession,
    user: CurrentUser,
    target_type: Literal["DOCUMENT", "VRP"] = Query(),
    limit: int = Query(default=100, ge=1, le=500),
) -> list:
    _authorize_target(request, session, user, target_type)
    return ResumableUploadService(session).list_sessions(
        user.organization_id,
        created_by=user.id,
        target_type=target_type,
        limit=limit,
    )


@router.get("/{upload_id}", response_model=ResumableUploadRead)
def get_upload(
    upload_id: str,
    request: Request,
    session: DbSession,
    user: CurrentUser,
) -> ResumableUploadRead:
    try:
        upload = ResumableUploadService(session).get(
            user.organization_id,
            upload_id,
            created_by=user.id,
        )
        _authorize_target(request, session, user, upload.target_type)
        return ResumableUploadRead.model_validate(upload)
    except Exception as exc:
        raise _error(exc) from exc


@router.put(
    "/{upload_id}/chunks/{chunk_index}",
    response_model=ResumableUploadRead,
)
def put_chunk(
    upload_id: str,
    chunk_index: int,
    request: Request,
    session: DbSession,
    user: CurrentUser,
    payload: Annotated[
        bytes,
        Body(media_type="application/octet-stream", max_length=16 * 1024 * 1024),
    ],
    chunk_sha256: Annotated[
        str | None,
        Header(alias="X-Chunk-SHA256", pattern=r"^[a-f0-9]{64}$"),
    ] = None,
) -> ResumableUploadRead:
    try:
        service = ResumableUploadService(session)
        pending = service.get(
            user.organization_id,
            upload_id,
            created_by=user.id,
        )
        _authorize_target(request, session, user, pending.target_type)
        upload = service.put_chunk(
            user=user,
            upload_id=upload_id,
            chunk_index=chunk_index,
            payload=payload,
            declared_sha256=chunk_sha256,
        )
        return ResumableUploadRead.model_validate(upload)
    except Exception as exc:
        session.rollback()
        raise _error(exc) from exc


@router.post(
    "/{upload_id}/complete",
    response_model=ResumableUploadResult,
)
def complete_upload(
    upload_id: str,
    payload: ResumableUploadComplete,
    request: Request,
    session: DbSession,
    user: CurrentUser,
) -> ResumableUploadResult:
    try:
        service = ResumableUploadService(session)
        pending = service.get(
            user.organization_id,
            upload_id,
            created_by=user.id,
        )
        _authorize_target(request, session, user, pending.target_type)
        result = service.complete(
            user=user,
            upload_id=upload_id,
            declared_file_sha256=payload.file_sha256,
            correlation_id=request.state.correlation_id,
        )
        return ResumableUploadResult(
            upload=ResumableUploadRead.model_validate(result.upload),
            entity_type=result.entity_type,
            entity_id=result.entity_id,
        )
    except Exception as exc:
        session.rollback()
        raise _error(exc) from exc


@router.delete("/{upload_id}", response_model=ResumableUploadRead)
def cancel_upload(
    upload_id: str,
    request: Request,
    session: DbSession,
    user: CurrentUser,
) -> ResumableUploadRead:
    try:
        service = ResumableUploadService(session)
        pending = service.get(
            user.organization_id,
            upload_id,
            created_by=user.id,
        )
        _authorize_target(request, session, user, pending.target_type)
        cancelled = service.cancel(
            user=user,
            upload_id=upload_id,
            correlation_id=request.state.correlation_id,
        )
        return ResumableUploadRead.model_validate(cancelled)
    except Exception as exc:
        session.rollback()
        raise _error(exc) from exc
