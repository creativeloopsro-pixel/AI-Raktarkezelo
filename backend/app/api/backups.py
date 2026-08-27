from __future__ import annotations

from typing import Annotated
from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, StreamingResponse

from app.dependencies import CurrentUser, DbSession, InteractiveUser, require_permissions
from app.models import BackupSchedule
from app.schemas import BackupRestoreRead, BackupScheduleRead, BackupScheduleUpdate
from app.services.backup_restore import (
    BackupOrganizationMismatchError,
    BackupRestoreError,
    BackupRestoreService,
    BackupRestoreTooLargeError,
    InvalidBackupArchiveError,
)
from app.services.backups import (
    BACKUP_CONTENT_TYPE,
    BackupBusyError,
    BackupNotAvailableError,
    BackupService,
)

router = APIRouter(prefix="/backups", tags=["backups"])
BackupReader = Annotated[
    object,
    Depends(require_permissions("settings.read")),
]
BackupWriter = Annotated[
    object,
    Depends(require_permissions("settings.write")),
]
BackupRestorer = Annotated[
    object,
    Depends(require_permissions("backups.restore")),
]


def _correlation_id(value: str | None) -> str:
    return value or str(uuid4())


def _read(schedule: BackupSchedule) -> BackupScheduleRead:
    return BackupScheduleRead(
        organization_id=schedule.organization_id,
        enabled=schedule.enabled,
        frequency=schedule.frequency,
        backup_time=schedule.backup_time,
        timezone=schedule.timezone,
        weekly_day=schedule.weekly_day,
        monthly_rule=schedule.monthly_rule,
        next_run_at=schedule.next_run_at,
        last_run_at=schedule.last_run_at,
        last_status=schedule.last_status,
        last_error_message=schedule.last_error_message,
        last_filename=schedule.last_filename,
        last_size_bytes=schedule.last_size_bytes,
        last_sha256=schedule.last_sha256,
        backup_available=bool(schedule.last_object_key),
        updated_by=schedule.updated_by,
        created_at=schedule.created_at,
        updated_at=schedule.updated_at,
    )


@router.get("/schedule", response_model=BackupScheduleRead)
def get_backup_schedule(
    session: DbSession,
    user: CurrentUser,
    _: BackupReader,
) -> BackupScheduleRead:
    return _read(BackupService(session).get_schedule(user.organization_id))


@router.put("/schedule", response_model=BackupScheduleRead)
def update_backup_schedule(
    payload: BackupScheduleUpdate,
    session: DbSession,
    user: CurrentUser,
    _: BackupWriter,
    correlation_header: Annotated[
        str | None, Header(alias="X-Correlation-ID")
    ] = None,
) -> BackupScheduleRead:
    try:
        schedule = BackupService(session).update_schedule(
            user=user,
            correlation_id=_correlation_id(correlation_header),
            **payload.model_dump(),
        )
        return _read(schedule)
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "invalid_backup_schedule", "message": str(exc)},
        ) from exc


@router.post(
    "/generate",
    response_model=BackupScheduleRead,
    status_code=status.HTTP_201_CREATED,
)
def generate_backup(
    session: DbSession,
    user: CurrentUser,
    _: BackupWriter,
    correlation_header: Annotated[
        str | None, Header(alias="X-Correlation-ID")
    ] = None,
) -> BackupScheduleRead:
    try:
        return _read(
            BackupService(session).generate_now(
                user=user,
                correlation_id=_correlation_id(correlation_header),
            )
        )
    except BackupBusyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "backup_busy", "message": str(exc)},
        ) from exc


@router.get("/download")
def download_backup(
    session: DbSession,
    user: CurrentUser,
    _: BackupReader,
):
    service = BackupService(session)
    try:
        schedule, stream = service.open_download(user.organization_id)
    except BackupNotAvailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "backup_not_available", "message": str(exc)},
        ) from exc
    filename = schedule.last_filename or "ai-raktar-biztonsagi-mentes.zip"
    local_path = service.storage.local_path(schedule.last_object_key)
    if local_path is not None:
        stream.close()
        return FileResponse(
            local_path,
            media_type=BACKUP_CONTENT_TYPE,
            filename=filename,
        )
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    if schedule.last_size_bytes is not None:
        headers["Content-Length"] = str(schedule.last_size_bytes)

    def stream_backup():
        try:
            while chunk := stream.read(1024 * 1024):
                yield chunk
        finally:
            stream.close()

    return StreamingResponse(
        stream_backup(),
        media_type=BACKUP_CONTENT_TYPE,
        headers=headers,
    )


@router.post(
    "/restore",
    response_model=BackupRestoreRead,
    status_code=status.HTTP_200_OK,
)
def restore_backup(
    session: DbSession,
    user: InteractiveUser,
    _: BackupRestorer,
    file: Annotated[UploadFile, File(description="AI Raktár ZIP biztonsági mentés")],
    confirmation: Annotated[str, Form(max_length=20)],
    correlation_header: Annotated[
        str | None, Header(alias="X-Correlation-ID")
    ] = None,
) -> BackupRestoreRead:
    if confirmation != "RESTORE":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "backup_restore_confirmation_required",
                "message": "A visszaállítás külön megerősítést igényel.",
            },
        )
    service = BackupRestoreService(session)
    source_path = None
    try:
        source_path, source_sha256 = service.save_upload(file.file)
        result = service.restore(
            user=user,
            source_path=source_path,
            source_filename=file.filename or "ai-raktar-biztonsagi-mentes.zip",
            source_sha256=source_sha256,
            correlation_id=_correlation_id(correlation_header),
        )
        return BackupRestoreRead(**result.__dict__)
    except BackupRestoreTooLargeError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    except BackupOrganizationMismatchError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    except InvalidBackupArchiveError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    except BackupBusyError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "backup_busy", "message": str(exc)},
        ) from exc
    except BackupRestoreError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    finally:
        if source_path is not None:
            source_path.unlink(missing_ok=True)
