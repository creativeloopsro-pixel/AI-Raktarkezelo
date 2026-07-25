from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.dependencies import CurrentUser, DbSession, require_permissions
from app.models import GoodsReceiptDraft
from app.schemas import GoodsReceiptDraftRead, GoodsReceiptItemUpdate
from app.services.goods_receipts import (
    GoodsReceiptError,
    GoodsReceiptItemNotFoundError,
    GoodsReceiptNotFoundError,
    GoodsReceiptNotReadyError,
    GoodsReceiptService,
    InvalidProductMatchError,
)

router = APIRouter(prefix="/goods-receipts", tags=["goods receipts"])
ReceiptReader = Annotated[object, Depends(require_permissions("receipts.read"))]
ReceiptConfirmer = Annotated[object, Depends(require_permissions("receipts.confirm"))]


def _map_error(exc: GoodsReceiptError) -> HTTPException:
    if isinstance(exc, (GoodsReceiptNotFoundError, GoodsReceiptItemNotFoundError)):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": "A bevételezési tervezet nem található."},
        )
    if isinstance(exc, GoodsReceiptNotReadyError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": exc.code,
                "message": "A bevételezés csak minden tétel ellenőrzése után hagyható jóvá.",
            },
        )
    if isinstance(exc, InvalidProductMatchError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": exc.code,
                "message": "A kiválasztott termék vagy csomagolási egység érvénytelen.",
            },
        )
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"code": exc.code, "message": "A bevételezési művelet sikertelen."},
    )


@router.get("/by-document/{document_id}", response_model=GoodsReceiptDraftRead)
def get_receipt_by_document(
    document_id: str,
    session: DbSession,
    user: CurrentUser,
    _: ReceiptReader,
) -> GoodsReceiptDraft:
    try:
        return GoodsReceiptService(session).get_by_document(
            user.organization_id,
            document_id,
        )
    except GoodsReceiptError as exc:
        raise _map_error(exc) from exc


@router.patch(
    "/{draft_id}/items/{item_id}",
    response_model=GoodsReceiptDraftRead,
)
def update_receipt_item(
    draft_id: str,
    item_id: str,
    payload: GoodsReceiptItemUpdate,
    session: DbSession,
    user: CurrentUser,
    _: ReceiptConfirmer,
    correlation_header: Annotated[str | None, Header(alias="X-Correlation-ID")] = None,
) -> GoodsReceiptDraft:
    try:
        return GoodsReceiptService(session).update_item(
            user=user,
            draft_id=draft_id,
            item_id=item_id,
            product_id=payload.product_id,
            packaging_unit_id=payload.packaging_unit_id,
            quantity=payload.quantity,
            correlation_id=correlation_header or str(uuid4()),
        )
    except GoodsReceiptError as exc:
        session.rollback()
        raise _map_error(exc) from exc


@router.post(
    "/{draft_id}/confirm",
    response_model=GoodsReceiptDraftRead,
)
def confirm_receipt(
    draft_id: str,
    session: DbSession,
    user: CurrentUser,
    _: ReceiptConfirmer,
    correlation_header: Annotated[str | None, Header(alias="X-Correlation-ID")] = None,
) -> GoodsReceiptDraft:
    try:
        return GoodsReceiptService(session).confirm(
            user=user,
            draft_id=draft_id,
            correlation_id=correlation_header or str(uuid4()),
        )
    except GoodsReceiptError as exc:
        session.rollback()
        raise _map_error(exc) from exc
