from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from app.dependencies import CurrentUser, DbSession, require_roles
from app.models import InventorySession
from app.schemas import (
    InventoryCancelRequest,
    InventoryCompleteRequest,
    InventoryCorrectionRead,
    InventoryCountCreate,
    InventoryCountRead,
    InventoryRecentMovementRead,
    InventorySessionCreate,
    InventorySessionRead,
)
from app.services.inventory import (
    ActiveInventorySessionError,
    InventoryApprovalRequiredError,
    InventoryBarcodeMismatchError,
    InventoryClientTimestampError,
    InventoryCountRequiredError,
    InventoryOperationConflictError,
    InventoryProductNotFoundError,
    InventoryReasonInvalidError,
    InventoryReasonRequiredError,
    InventoryService,
    InventorySessionNotFoundError,
    InventorySessionStateError,
)

router = APIRouter(prefix="/inventory", tags=["inventory"])
InventoryOperator = Annotated[
    object, Depends(require_roles("admin", "manager", "warehouse"))
]
InventoryApprover = Annotated[
    object, Depends(require_roles("admin", "manager"))
]


def _correlation_id(value: str | None) -> str:
    return value or str(uuid4())


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, InventorySessionNotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": exc.code,
                "message": "A leltármenet nem található.",
            },
        )
    if isinstance(exc, InventoryProductNotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": exc.code,
                "message": "A termék nem található.",
            },
        )
    if isinstance(exc, ActiveInventorySessionError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": exc.code,
                "message": "Már van aktív leltármenet.",
                "existing_session_id": exc.session_id,
            },
        )
    if isinstance(
        exc, (InventorySessionStateError, InventoryOperationConflictError)
    ):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": exc.code,
                "message": "A leltárművelet az aktuális állapotban nem végezhető el.",
            },
        )
    if isinstance(exc, InventoryApprovalRequiredError):
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": exc.code,
                "message": "A művelethez vezetői jóváhagyás szükséges.",
            },
        )
    if isinstance(
        exc,
        (
            InventoryBarcodeMismatchError,
            InventoryClientTimestampError,
            InventoryCountRequiredError,
            InventoryReasonInvalidError,
            InventoryReasonRequiredError,
        ),
    ):
        messages = {
            "inventory_barcode_mismatch": "A kód nem a kiválasztott termékhez tartozik.",
            "inventory_client_timestamp_invalid": "Az offline művelet időpontja érvénytelen.",
            "inventory_count_required": "A lezáráshoz legalább egy számlálás szükséges.",
            "inventory_reason_invalid": "A korrekció okkódja érvénytelen.",
            "inventory_reason_required": "Eltérés esetén kötelező korrekciós okot megadni.",
        }
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": exc.code,
                "message": messages[exc.code],
            },
        )
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={
            "code": getattr(exc, "code", "inventory_operation_failed"),
            "message": "A leltárművelet sikertelen.",
        },
    )


def _session_read(
    service: InventoryService, inventory_session: InventorySession
) -> InventorySessionRead:
    latest_counts = service.latest_counts(inventory_session)
    activity = service.recent_activity_for_products(
        inventory_session.organization_id,
        [count.product_id for count in latest_counts],
    )
    return InventorySessionRead(
        id=inventory_session.id,
        organization_id=inventory_session.organization_id,
        client_session_id=inventory_session.client_session_id,
        name=inventory_session.name,
        status=inventory_session.status,
        approval_required=inventory_session.approval_required,
        started_by=inventory_session.started_by,
        completed_by=inventory_session.completed_by,
        approved_by=inventory_session.approved_by,
        review_task_id=inventory_session.review_task_id,
        completion_note=inventory_session.completion_note,
        started_at=inventory_session.started_at,
        completed_at=inventory_session.completed_at,
        cancelled_at=inventory_session.cancelled_at,
        updated_at=inventory_session.updated_at,
        counts=[
            InventoryCountRead(
                id=count.id,
                organization_id=count.organization_id,
                session_id=count.session_id,
                product_id=count.product_id,
                product_name=count.product.name,
                internal_sku=count.product.internal_sku,
                base_unit=count.product.base_unit,
                client_operation_id=count.client_operation_id,
                expected_quantity=count.expected_quantity,
                client_expected_quantity=count.client_expected_quantity,
                counted_quantity=count.counted_quantity,
                quantity_difference=count.quantity_difference,
                scanned_code=count.scanned_code,
                reason_code=count.reason_code,
                reason_note=count.reason_note,
                recorded_by=count.recorded_by,
                client_recorded_at=count.client_recorded_at,
                created_at=count.created_at,
                recent_movements=[
                    InventoryRecentMovementRead.model_validate(movement)
                    for movement in activity.get(count.product_id, [])
                ],
            )
            for count in latest_counts
        ],
        corrections=[
            InventoryCorrectionRead(
                id=correction.id,
                organization_id=correction.organization_id,
                session_id=correction.session_id,
                count_id=correction.count_id,
                product_id=correction.product_id,
                product_name=correction.product.name,
                movement_id=correction.movement_id,
                expected_quantity=correction.expected_quantity,
                counted_quantity=correction.counted_quantity,
                quantity_delta=correction.quantity_delta,
                reason_code=correction.reason_code,
                reason_note=correction.reason_note,
                created_by=correction.created_by,
                approved_by=correction.approved_by,
                created_at=correction.created_at,
            )
            for correction in sorted(
                inventory_session.corrections,
                key=lambda item: item.created_at,
            )
        ],
    )


@router.get("/sessions", response_model=list[InventorySessionRead])
def list_inventory_sessions(
    session: DbSession,
    user: CurrentUser,
    _: InventoryOperator,
    session_status: str | None = Query(
        default=None, alias="status", max_length=32
    ),
    limit: int = Query(default=30, ge=1, le=100),
) -> list[InventorySessionRead]:
    service = InventoryService(session)
    return [
        _session_read(service, item)
        for item in service.list_sessions(
            user.organization_id,
            status=session_status,
            limit=limit,
        )
    ]


@router.get(
    "/sessions/current",
    response_model=InventorySessionRead | None,
)
def current_inventory_session(
    session: DbSession,
    user: CurrentUser,
    _: InventoryOperator,
) -> InventorySessionRead | None:
    service = InventoryService(session)
    inventory_session = service.get_active(user.organization_id)
    if inventory_session is None:
        return None
    return _session_read(service, inventory_session)


@router.post(
    "/sessions",
    response_model=InventorySessionRead,
    status_code=status.HTTP_201_CREATED,
)
def start_inventory_session(
    payload: InventorySessionCreate,
    session: DbSession,
    user: CurrentUser,
    _: InventoryOperator,
    correlation_header: Annotated[
        str | None, Header(alias="X-Correlation-ID")
    ] = None,
) -> InventorySessionRead:
    service = InventoryService(session)
    try:
        inventory_session = service.start(
            user=user,
            client_session_id=payload.client_session_id,
            name=payload.name,
            correlation_id=_correlation_id(correlation_header),
        )
        session.commit()
        return _session_read(
            service,
            service.get_session(user.organization_id, inventory_session.id),
        )
    except Exception as exc:
        session.rollback()
        raise _map_error(exc) from exc


@router.get(
    "/sessions/{session_id}",
    response_model=InventorySessionRead,
)
def get_inventory_session(
    session_id: str,
    session: DbSession,
    user: CurrentUser,
    _: InventoryOperator,
) -> InventorySessionRead:
    service = InventoryService(session)
    try:
        return _session_read(
            service, service.get_session(user.organization_id, session_id)
        )
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post(
    "/sessions/{session_id}/counts",
    response_model=InventorySessionRead,
    status_code=status.HTTP_201_CREATED,
)
def record_inventory_count(
    session_id: str,
    payload: InventoryCountCreate,
    session: DbSession,
    user: CurrentUser,
    _: InventoryOperator,
    correlation_header: Annotated[
        str | None, Header(alias="X-Correlation-ID")
    ] = None,
) -> InventorySessionRead:
    service = InventoryService(session)
    try:
        service.record_count(
            user=user,
            session_id=session_id,
            product_id=payload.product_id,
            counted_quantity=payload.counted_quantity,
            client_operation_id=payload.client_operation_id,
            client_recorded_at=payload.client_recorded_at,
            client_expected_quantity=payload.client_expected_quantity,
            scanned_code=payload.scanned_code,
            reason_code=payload.reason_code,
            reason_note=payload.reason_note,
            correlation_id=_correlation_id(correlation_header),
        )
        session.commit()
        return _session_read(
            service, service.get_session(user.organization_id, session_id)
        )
    except Exception as exc:
        session.rollback()
        raise _map_error(exc) from exc


@router.post(
    "/sessions/{session_id}/complete",
    response_model=InventorySessionRead,
)
def complete_inventory_session(
    session_id: str,
    payload: InventoryCompleteRequest,
    session: DbSession,
    user: CurrentUser,
    _: InventoryOperator,
    correlation_header: Annotated[
        str | None, Header(alias="X-Correlation-ID")
    ] = None,
) -> InventorySessionRead:
    service = InventoryService(session)
    try:
        service.complete(
            user=user,
            session_id=session_id,
            note=payload.note,
            correlation_id=_correlation_id(correlation_header),
        )
        session.commit()
        return _session_read(
            service, service.get_session(user.organization_id, session_id)
        )
    except Exception as exc:
        session.rollback()
        raise _map_error(exc) from exc


@router.post(
    "/sessions/{session_id}/approve",
    response_model=InventorySessionRead,
)
def approve_inventory_session(
    session_id: str,
    payload: InventoryCompleteRequest,
    session: DbSession,
    user: CurrentUser,
    _: InventoryApprover,
    correlation_header: Annotated[
        str | None, Header(alias="X-Correlation-ID")
    ] = None,
) -> InventorySessionRead:
    service = InventoryService(session)
    try:
        service.approve(
            user=user,
            session_id=session_id,
            note=payload.note,
            correlation_id=_correlation_id(correlation_header),
        )
        session.commit()
        return _session_read(
            service, service.get_session(user.organization_id, session_id)
        )
    except Exception as exc:
        session.rollback()
        raise _map_error(exc) from exc


@router.post(
    "/sessions/{session_id}/cancel",
    response_model=InventorySessionRead,
)
def cancel_inventory_session(
    session_id: str,
    payload: InventoryCancelRequest,
    session: DbSession,
    user: CurrentUser,
    _: InventoryOperator,
    correlation_header: Annotated[
        str | None, Header(alias="X-Correlation-ID")
    ] = None,
) -> InventorySessionRead:
    service = InventoryService(session)
    try:
        service.cancel(
            user=user,
            session_id=session_id,
            note=payload.note,
            correlation_id=_correlation_id(correlation_header),
        )
        session.commit()
        return _session_read(
            service, service.get_session(user.organization_id, session_id)
        )
    except Exception as exc:
        session.rollback()
        raise _map_error(exc) from exc
