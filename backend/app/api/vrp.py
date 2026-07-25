from datetime import date
from typing import Annotated
from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy import select

from app.dependencies import CurrentUser, DbSession, require_permissions
from app.models import Plugin, VrpImportBatch, VrpImportSchedule
from app.schemas import (
    VrpImportBatchRead,
    VrpImportItemUpdate,
    VrpImportReverse,
    VrpScheduleRead,
    VrpScheduleUpdate,
)
from app.services.vrp_imports import (
    VrpDuplicateError,
    VrpFileTooLargeError,
    VrpImportErrorBase,
    VrpImportNotFoundError,
    VrpImportService,
    VrpInvalidMappingError,
    VrpInvalidPeriodError,
    VrpInvalidReportError,
    VrpItemNotFoundError,
    VrpNegativeStockError,
    VrpNotProcessableError,
    VrpNotReversibleError,
    VrpScannerUnavailableError,
    VrpUnsafeFileError,
    VrpUnsupportedFileError,
)

router = APIRouter(prefix="/vrp", tags=["vrp imports"])
VrpReader = Annotated[object, Depends(require_permissions("vrp.read"))]
VrpUploader = Annotated[object, Depends(require_permissions("vrp.upload"))]
VrpProcessor = Annotated[object, Depends(require_permissions("vrp.process"))]
VrpSettingsAdmin = Annotated[object, Depends(require_permissions("vrp.settings"))]
VrpReverser = Annotated[
    object,
    Depends(require_permissions("vrp.process", "stock.reverse")),
]


def require_vrp_plugin_enabled(
    session: DbSession,
    user: CurrentUser,
    _: VrpReader,
) -> object:
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
    return object()


VrpPluginEnabled = Annotated[object, Depends(require_vrp_plugin_enabled)]


def _correlation_id(value: str | None) -> str:
    return value or str(uuid4())


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, (VrpImportNotFoundError, VrpItemNotFoundError)):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": "A VRP-import nem található."},
        )
    if isinstance(exc, VrpDuplicateError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": exc.code,
                "message": "Ezt a VRP-riportot korábban már feltöltötték.",
                "existing_batch_id": exc.existing_batch_id,
            },
        )
    if isinstance(exc, VrpFileTooLargeError):
        return HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail={"code": exc.code, "message": "A VRP-riport túl nagy."},
        )
    if isinstance(exc, VrpUnsupportedFileError):
        return HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail={
                "code": exc.code,
                "message": "CSV, XLSX vagy géppel olvasható PDF riport tölthető fel.",
            },
        )
    if isinstance(exc, VrpInvalidReportError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": exc.code, "message": exc.message},
        )
    if isinstance(exc, VrpInvalidPeriodError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": exc.code,
                "message": "A riportidőszak kezdete, vége vagy hossza érvénytelen.",
            },
        )
    if isinstance(exc, VrpUnsafeFileError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": exc.code, "message": "A riport biztonsági ellenőrzése hibát jelzett."},
        )
    if isinstance(exc, VrpScannerUnavailableError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": exc.code,
                "message": "A vírusellenőrző nem elérhető; a riport nem került tárolásra.",
            },
        )
    if isinstance(exc, VrpInvalidMappingError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": exc.code,
                "message": "A kiválasztott termék vagy konverziós faktor érvénytelen.",
            },
        )
    if isinstance(exc, VrpNegativeStockError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": exc.code,
                "message": "A beállított szabály szerint negatív készlet nem könyvelhető.",
            },
        )
    if isinstance(exc, (VrpNotProcessableError, VrpNotReversibleError)):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": exc.code,
                "message": "A VRP-import ebben az állapotban nem hajtható végre.",
            },
        )
    code = getattr(exc, "code", "vrp_operation_failed")
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"code": code, "message": "A VRP-művelet sikertelen."},
    )


@router.get("/imports", response_model=list[VrpImportBatchRead])
def list_vrp_imports(
    session: DbSession,
    user: CurrentUser,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[VrpImportBatch]:
    return VrpImportService(session).list_batches(user.organization_id, limit=limit)


@router.post(
    "/imports",
    response_model=VrpImportBatchRead,
    status_code=status.HTTP_201_CREATED,
)
def upload_vrp_import(
    session: DbSession,
    user: CurrentUser,
    _: VrpUploader,
    _plugin: VrpPluginEnabled,
    file: Annotated[UploadFile, File(description="VRP2 Report predaja")],
    period_start: Annotated[date, Form()],
    period_end: Annotated[date, Form()],
    external_report_id: Annotated[str | None, Form(max_length=160)] = None,
    correlation_header: Annotated[str | None, Header(alias="X-Correlation-ID")] = None,
) -> VrpImportBatch:
    try:
        return VrpImportService(session).ingest(
            user=user,
            stream=file.file,
            filename=file.filename or "vrp-report",
            declared_content_type=file.content_type,
            period_start=period_start,
            period_end=period_end,
            external_report_id=external_report_id,
            correlation_id=_correlation_id(correlation_header),
        ).batch
    except Exception as exc:
        session.rollback()
        raise _map_error(exc) from exc


@router.get("/imports/{batch_id}", response_model=VrpImportBatchRead)
def get_vrp_import(
    batch_id: str,
    session: DbSession,
    user: CurrentUser,
    _: VrpReader,
) -> VrpImportBatch:
    try:
        return VrpImportService(session).get_batch(user.organization_id, batch_id)
    except VrpImportErrorBase as exc:
        raise _map_error(exc) from exc


@router.patch(
    "/imports/{batch_id}/items/{item_id}",
    response_model=VrpImportBatchRead,
)
def update_vrp_item(
    batch_id: str,
    item_id: str,
    payload: VrpImportItemUpdate,
    session: DbSession,
    user: CurrentUser,
    _: VrpProcessor,
    _plugin: VrpPluginEnabled,
    correlation_header: Annotated[str | None, Header(alias="X-Correlation-ID")] = None,
) -> VrpImportBatch:
    try:
        return VrpImportService(session).update_item(
            user=user,
            batch_id=batch_id,
            item_id=item_id,
            product_id=payload.product_id,
            conversion_factor=payload.conversion_factor,
            correlation_id=_correlation_id(correlation_header),
        )
    except VrpImportErrorBase as exc:
        session.rollback()
        raise _map_error(exc) from exc


@router.post(
    "/imports/{batch_id}/process",
    response_model=VrpImportBatchRead,
)
def process_vrp_import(
    batch_id: str,
    session: DbSession,
    user: CurrentUser,
    _: VrpProcessor,
    _plugin: VrpPluginEnabled,
    correlation_header: Annotated[str | None, Header(alias="X-Correlation-ID")] = None,
) -> VrpImportBatch:
    try:
        return VrpImportService(session).process(
            user=user,
            batch_id=batch_id,
            correlation_id=_correlation_id(correlation_header),
            force=True,
        )
    except VrpImportErrorBase as exc:
        session.rollback()
        raise _map_error(exc) from exc


@router.post(
    "/imports/{batch_id}/reverse",
    response_model=VrpImportBatchRead,
)
def reverse_vrp_import(
    batch_id: str,
    payload: VrpImportReverse,
    session: DbSession,
    user: CurrentUser,
    _: VrpReverser,
    correlation_header: Annotated[str | None, Header(alias="X-Correlation-ID")] = None,
) -> VrpImportBatch:
    try:
        return VrpImportService(session).reverse(
            user=user,
            batch_id=batch_id,
            reason=payload.reason,
            correlation_id=_correlation_id(correlation_header),
        )
    except VrpImportErrorBase as exc:
        session.rollback()
        raise _map_error(exc) from exc


@router.get("/schedule", response_model=VrpScheduleRead)
def get_vrp_schedule(
    session: DbSession,
    user: CurrentUser,
    _: VrpReader,
) -> VrpImportSchedule:
    return VrpImportService(session).get_schedule(user.organization_id)


@router.put("/schedule", response_model=VrpScheduleRead)
def update_vrp_schedule(
    payload: VrpScheduleUpdate,
    session: DbSession,
    user: CurrentUser,
    _: VrpSettingsAdmin,
    _plugin: VrpPluginEnabled,
    correlation_header: Annotated[str | None, Header(alias="X-Correlation-ID")] = None,
) -> VrpImportSchedule:
    try:
        return VrpImportService(session).update_schedule(
            user=user,
            correlation_id=_correlation_id(correlation_header),
            **payload.model_dump(),
        )
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "invalid_schedule", "message": str(exc)},
        ) from exc
