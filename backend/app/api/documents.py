from typing import Annotated
from urllib.parse import quote
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
from fastapi.responses import FileResponse, Response, StreamingResponse
from sqlalchemy import or_, select

from app.dependencies import CurrentUser, DbSession, require_roles
from app.models import Document
from app.queueing import dispatch_document_job
from app.schemas import DocumentProcessingJobRead, DocumentRead
from app.services.documents import (
    DocumentNeedsReviewError,
    DocumentNotFoundError,
    DocumentNotProcessableError,
    DocumentService,
    DocumentTooLargeError,
    DuplicateDocumentError,
    ScannerUnavailableError,
    UnsafeDocumentError,
    UnsupportedDocumentError,
)
from app.storage import get_object_storage

router = APIRouter(prefix="/documents", tags=["documents"])
DocumentEditor = Annotated[object, Depends(require_roles("admin", "manager", "warehouse"))]


def _correlation_id(value: str | None) -> str:
    return value or str(uuid4())


def _document_error(exc: Exception) -> HTTPException:
    if isinstance(exc, UnsupportedDocumentError):
        return HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail={
                "code": exc.code,
                "message": "Csak PDF, JPG, PNG vagy TIFF dokumentum tölthető fel.",
            },
        )
    if isinstance(exc, DocumentTooLargeError):
        return HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail={"code": exc.code, "message": "A dokumentum meghaladja a méretkorlátot."},
        )
    if isinstance(exc, DuplicateDocumentError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": exc.code,
                "message": "Ezt a dokumentumot korábban már feltöltötték.",
                "existing_document_id": exc.existing_document_id,
            },
        )
    if isinstance(exc, UnsafeDocumentError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": exc.code,
                "message": "A dokumentum biztonsági ellenőrzése kártevőt jelzett.",
            },
        )
    if isinstance(exc, ScannerUnavailableError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": exc.code,
                "message": "A vírusellenőrző nem érhető el; a fájl nem került tárolásra.",
            },
        )
    if isinstance(exc, DocumentNotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": "A dokumentum nem található."},
        )
    if isinstance(exc, DocumentNeedsReviewError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": exc.code,
                "message": "A dokumentumot feldolgozás előtt ellenőrizni kell.",
            },
        )
    if isinstance(exc, DocumentNotProcessableError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": exc.code,
                "message": "A dokumentum ebben az állapotban nem indítható újra.",
            },
        )
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"code": "document_operation_failed", "message": "A dokumentumművelet sikertelen."},
    )


@router.get("", response_model=list[DocumentRead])
def list_documents(
    session: DbSession,
    user: CurrentUser,
    _: DocumentEditor,
    document_status: str | None = Query(default=None, alias="status", max_length=40),
    search: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[Document]:
    statement = select(Document).where(Document.organization_id == user.organization_id)
    if document_status:
        statement = statement.where(Document.status == document_status.upper())
    if search:
        pattern = f"%{search.strip()}%"
        statement = statement.where(
            or_(
                Document.original_filename.ilike(pattern),
                Document.sha256_hash.ilike(pattern),
            )
        )
    return list(session.scalars(statement.order_by(Document.created_at.desc()).limit(limit)))


@router.post("", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
def upload_document(
    session: DbSession,
    user: CurrentUser,
    _: DocumentEditor,
    file: Annotated[UploadFile, File(description="PDF, JPG, PNG vagy TIFF dokumentum")],
    document_type: Annotated[str, Form(max_length=60)] = "goods_receipt",
    correlation_header: Annotated[str | None, Header(alias="X-Correlation-ID")] = None,
) -> Document:
    try:
        return DocumentService(session).ingest(
            user=user,
            stream=file.file,
            filename=file.filename or "document",
            declared_content_type=file.content_type,
            document_type=document_type,
            correlation_id=_correlation_id(correlation_header),
        )
    except Exception as exc:
        raise _document_error(exc) from exc


@router.post(
    "/{document_id}/process",
    response_model=DocumentProcessingJobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def queue_document_processing(
    document_id: str,
    session: DbSession,
    user: CurrentUser,
    _: DocumentEditor,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8)],
    correlation_header: Annotated[str | None, Header(alias="X-Correlation-ID")] = None,
):
    try:
        result = DocumentService(session).queue_processing(
            user=user,
            document_id=document_id,
            idempotency_key=idempotency_key,
            correlation_id=_correlation_id(correlation_header),
        )
        if result.created:
            dispatch_document_job(result.job.id)
        return result.job
    except Exception as exc:
        session.rollback()
        raise _document_error(exc) from exc


@router.get("/{document_id}/download")
def download_document(
    document_id: str,
    session: DbSession,
    user: CurrentUser,
) -> Response:
    document = session.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.organization_id == user.organization_id,
        )
    )
    if document is None:
        raise _document_error(DocumentNotFoundError())

    storage = get_object_storage()
    local_path = storage.local_path(document.object_key)
    if local_path is not None:
        return FileResponse(
            local_path,
            media_type=document.content_type,
            filename=document.original_filename,
        )
    stream = storage.open_stream(document.object_key)
    if stream is not None:
        encoded_filename = quote(document.original_filename)
        return StreamingResponse(
            stream,
            media_type=document.content_type,
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
                "Content-Length": str(document.size_bytes),
            },
        )
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={"code": "storage_unavailable", "message": "A dokumentumtár nem elérhető."},
    )


@router.get("/{document_id}", response_model=DocumentRead)
def get_document(document_id: str, session: DbSession, user: CurrentUser) -> Document:
    document = session.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.organization_id == user.organization_id,
        )
    )
    if document is None:
        raise _document_error(DocumentNotFoundError())
    return document
