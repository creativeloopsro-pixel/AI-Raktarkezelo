from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import select

from app.dependencies import CurrentUser, DbSession, require_permissions
from app.models import Product, StockBalance, StockMovement
from app.schemas import (
    ReversalRequest,
    StockBalanceRead,
    StockCorrection,
    StockMovementRead,
    StockOperation,
    StockProductDetail,
)
from app.services.stock import (
    MovementAlreadyReversedError,
    MovementNotFoundError,
    ProductNotFoundError,
    ReversalOfReversalError,
    StockService,
)

router = APIRouter(prefix="/stock", tags=["stock"])
StockReader = Annotated[object, Depends(require_permissions("stock.read"))]
StockReceiver = Annotated[object, Depends(require_permissions("stock.receive"))]
StockCorrector = Annotated[object, Depends(require_permissions("stock.correct"))]
StockReverser = Annotated[object, Depends(require_permissions("stock.reverse"))]


def _correlation_id(value: str | None) -> str:
    return value or str(uuid4())


def _map_stock_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ProductNotFoundError):
        return HTTPException(
            status_code=404,
            detail={"code": exc.code, "message": "A termék nem található."},
        )
    if isinstance(exc, MovementNotFoundError):
        return HTTPException(
            status_code=404,
            detail={"code": exc.code, "message": "A készletmozgás nem található."},
        )
    if isinstance(exc, MovementAlreadyReversedError):
        return HTTPException(
            status_code=409,
            detail={"code": exc.code, "message": "A mozgást már visszavonták."},
        )
    if isinstance(exc, ReversalOfReversalError):
        return HTTPException(
            status_code=409,
            detail={"code": exc.code, "message": "Visszavonó mozgás nem vonható vissza."},
        )
    return HTTPException(
        status_code=400,
        detail={"code": "stock_operation_failed", "message": "A készletművelet sikertelen."},
    )


@router.get("", response_model=list[StockBalanceRead])
def list_stock(
    session: DbSession,
    user: CurrentUser,
    _: StockReader,
    low_stock_only: bool = Query(default=False),
) -> list[StockBalanceRead]:
    statement = (
        select(Product, StockBalance)
        .outerjoin(
            StockBalance,
            (StockBalance.product_id == Product.id)
            & (StockBalance.organization_id == Product.organization_id),
        )
        .where(
            Product.organization_id == user.organization_id,
            Product.status == "active",
        )
        .order_by(Product.name)
    )
    result: list[StockBalanceRead] = []
    for product, balance in session.execute(statement):
        quantity = balance.quantity if balance else 0
        if low_stock_only and quantity > product.min_stock:
            continue
        result.append(
            StockBalanceRead(
                product_id=product.id,
                product_name=product.name,
                internal_sku=product.internal_sku,
                quantity=quantity,
                min_stock=product.min_stock,
                updated_at=balance.updated_at if balance else None,
            )
        )
    return result


@router.post("/receive", response_model=StockMovementRead, status_code=status.HTTP_201_CREATED)
def receive_stock(
    payload: StockOperation,
    session: DbSession,
    user: CurrentUser,
    _: StockReceiver,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8)],
    correlation_header: Annotated[str | None, Header(alias="X-Correlation-ID")] = None,
) -> StockMovement:
    try:
        result = StockService(session).receive(
            user=user,
            product_id=payload.product_id,
            quantity=payload.quantity,
            source_id=payload.source_id,
            idempotency_key=idempotency_key,
            correlation_id=_correlation_id(correlation_header),
            reason=payload.reason,
        )
        session.commit()
        return result.movement
    except Exception as exc:
        session.rollback()
        raise _map_stock_error(exc) from exc


@router.post("/correct", response_model=StockMovementRead, status_code=status.HTTP_201_CREATED)
def correct_stock(
    payload: StockCorrection,
    session: DbSession,
    user: CurrentUser,
    _: StockCorrector,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8)],
    correlation_header: Annotated[str | None, Header(alias="X-Correlation-ID")] = None,
) -> StockMovement:
    try:
        result = StockService(session).correct_to(
            user=user,
            product_id=payload.product_id,
            counted_quantity=payload.counted_quantity,
            idempotency_key=idempotency_key,
            correlation_id=_correlation_id(correlation_header),
            reason=payload.reason,
        )
        session.commit()
        return result.movement
    except Exception as exc:
        session.rollback()
        raise _map_stock_error(exc) from exc


@router.post(
    "/movements/{movement_id}/reverse",
    response_model=StockMovementRead,
    status_code=status.HTTP_201_CREATED,
)
def reverse_movement(
    movement_id: str,
    payload: ReversalRequest,
    session: DbSession,
    user: CurrentUser,
    _: StockReverser,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8)],
    correlation_header: Annotated[str | None, Header(alias="X-Correlation-ID")] = None,
) -> StockMovement:
    try:
        result = StockService(session).reverse(
            user=user,
            movement_id=movement_id,
            idempotency_key=idempotency_key,
            correlation_id=_correlation_id(correlation_header),
            reason=payload.reason,
        )
        session.commit()
        return result.movement
    except Exception as exc:
        session.rollback()
        raise _map_stock_error(exc) from exc


@router.get("/{product_id}", response_model=StockProductDetail)
def stock_detail(
    product_id: str,
    session: DbSession,
    user: CurrentUser,
    _: StockReader,
    movement_limit: int = Query(default=50, ge=1, le=200),
) -> StockProductDetail:
    row = session.execute(
        select(Product, StockBalance)
        .outerjoin(
            StockBalance,
            (StockBalance.product_id == Product.id)
            & (StockBalance.organization_id == Product.organization_id),
        )
        .where(
            Product.id == product_id,
            Product.organization_id == user.organization_id,
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "product_not_found", "message": "A termék nem található."},
        )
    product, balance = row
    movements = list(
        session.scalars(
            select(StockMovement)
            .where(
                StockMovement.organization_id == user.organization_id,
                StockMovement.product_id == product.id,
            )
            .order_by(StockMovement.created_at.desc())
            .limit(movement_limit)
        )
    )
    return StockProductDetail(
        balance=StockBalanceRead(
            product_id=product.id,
            product_name=product.name,
            internal_sku=product.internal_sku,
            quantity=balance.quantity if balance else 0,
            min_stock=product.min_stock,
            updated_at=balance.updated_at if balance else None,
        ),
        movements=movements,
    )
