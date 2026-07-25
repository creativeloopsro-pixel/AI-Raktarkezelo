from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import Settings, get_settings
from app.models import (
    AuditLog,
    InventoryCount,
    InventorySession,
    InventoryStockCorrection,
    Organization,
    OutboxEvent,
    Product,
    ProductBarcode,
    ReviewTask,
    StockBalance,
    StockMovement,
    User,
    utc_now,
)
from app.services.stock import StockService

INVENTORY_REASON_CODES = frozenset(
    {
        "PHYSICAL_COUNT",
        "DAMAGE",
        "SHRINKAGE",
        "DATA_ERROR",
        "OTHER",
    }
)


class InventoryError(Exception):
    code = "inventory_error"


class InventorySessionNotFoundError(InventoryError):
    code = "inventory_session_not_found"


class ActiveInventorySessionError(InventoryError):
    code = "active_inventory_session_exists"

    def __init__(self, session_id: str):
        self.session_id = session_id


class InventorySessionStateError(InventoryError):
    code = "inventory_session_state_invalid"


class InventoryCountRequiredError(InventoryError):
    code = "inventory_count_required"


class InventoryReasonRequiredError(InventoryError):
    code = "inventory_reason_required"


class InventoryReasonInvalidError(InventoryError):
    code = "inventory_reason_invalid"


class InventoryProductNotFoundError(InventoryError):
    code = "inventory_product_not_found"


class InventoryBarcodeMismatchError(InventoryError):
    code = "inventory_barcode_mismatch"


class InventoryOperationConflictError(InventoryError):
    code = "inventory_operation_conflict"


class InventoryClientTimestampError(InventoryError):
    code = "inventory_client_timestamp_invalid"


class InventoryApprovalRequiredError(InventoryError):
    code = "inventory_approval_required"


class InventoryService:
    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
    ):
        self.session = session
        self.settings = settings or get_settings()

    @staticmethod
    def _session_query():
        return (
            select(InventorySession)
            .options(
                selectinload(InventorySession.counts).selectinload(
                    InventoryCount.product
                ),
                selectinload(InventorySession.corrections).selectinload(
                    InventoryStockCorrection.product
                ),
                selectinload(InventorySession.corrections).selectinload(
                    InventoryStockCorrection.movement
                ),
            )
            .execution_options(populate_existing=True)
        )

    def list_sessions(
        self,
        organization_id: str,
        *,
        status: str | None = None,
        limit: int = 50,
    ) -> list[InventorySession]:
        statement = self._session_query().where(
            InventorySession.organization_id == organization_id
        )
        if status:
            statement = statement.where(InventorySession.status == status)
        return list(
            self.session.scalars(
                statement.order_by(InventorySession.started_at.desc()).limit(limit)
            ).unique()
        )

    def get_session(
        self, organization_id: str, session_id: str
    ) -> InventorySession:
        inventory_session = self.session.scalar(
            self._session_query().where(
                InventorySession.id == session_id,
                InventorySession.organization_id == organization_id,
            )
        )
        if inventory_session is None:
            raise InventorySessionNotFoundError
        return inventory_session

    def get_active(self, organization_id: str) -> InventorySession | None:
        return self.session.scalar(
            self._session_query()
            .where(
                InventorySession.organization_id == organization_id,
                InventorySession.status.in_(("OPEN", "PENDING_APPROVAL")),
            )
            .order_by(InventorySession.started_at.desc())
            .limit(1)
        )

    def start(
        self,
        *,
        user: User,
        client_session_id: str,
        name: str,
        correlation_id: str,
    ) -> InventorySession:
        self.session.scalar(
            select(Organization.id)
            .where(Organization.id == user.organization_id)
            .with_for_update()
        )
        existing = self.session.scalar(
            select(InventorySession).where(
                InventorySession.organization_id == user.organization_id,
                InventorySession.client_session_id == client_session_id,
            )
        )
        if existing is not None:
            return existing
        active = self.session.scalar(
            select(InventorySession)
            .where(
                InventorySession.organization_id == user.organization_id,
                InventorySession.status.in_(("OPEN", "PENDING_APPROVAL")),
            )
            .with_for_update()
        )
        if active is not None:
            raise ActiveInventorySessionError(active.id)

        inventory_session = InventorySession(
            organization_id=user.organization_id,
            client_session_id=client_session_id,
            name=name.strip(),
            status="OPEN",
            started_by=user.id,
        )
        self.session.add(inventory_session)
        self.session.flush()
        self._audit(
            user=user,
            action="inventory.session_started",
            inventory_session=inventory_session,
            correlation_id=correlation_id,
            details={"name": inventory_session.name},
        )
        return inventory_session

    def record_count(
        self,
        *,
        user: User,
        session_id: str,
        product_id: str,
        counted_quantity: Decimal,
        client_operation_id: str,
        client_recorded_at: datetime,
        client_expected_quantity: Decimal | None,
        scanned_code: str | None,
        reason_code: str | None,
        reason_note: str | None,
        correlation_id: str,
    ) -> InventoryCount:
        duplicate = self.session.scalar(
            select(InventoryCount).where(
                InventoryCount.organization_id == user.organization_id,
                InventoryCount.client_operation_id == client_operation_id,
            )
        )
        if duplicate is not None:
            if (
                duplicate.session_id != session_id
                or duplicate.product_id != product_id
                or duplicate.counted_quantity != counted_quantity
            ):
                raise InventoryOperationConflictError
            return duplicate

        inventory_session = self._locked_session(
            user.organization_id, session_id
        )
        if inventory_session.status != "OPEN":
            raise InventorySessionStateError
        product = self.session.scalar(
            select(Product).where(
                Product.id == product_id,
                Product.organization_id == user.organization_id,
                Product.status == "active",
            )
        )
        if product is None:
            raise InventoryProductNotFoundError
        normalized_code = scanned_code.strip() if scanned_code else None
        if normalized_code:
            barcode_product_id = self.session.scalar(
                select(ProductBarcode.product_id).where(
                    ProductBarcode.organization_id == user.organization_id,
                    ProductBarcode.code == normalized_code,
                )
            )
            if barcode_product_id != product.id:
                raise InventoryBarcodeMismatchError
        normalized_reason = reason_code.strip().upper() if reason_code else None
        if normalized_reason and normalized_reason not in INVENTORY_REASON_CODES:
            raise InventoryReasonInvalidError

        recorded_at = self._validate_client_timestamp(client_recorded_at)
        balance = self._balance(user.organization_id, product.id)
        difference = counted_quantity - balance.quantity
        if difference != 0 and normalized_reason is None:
            raise InventoryReasonRequiredError

        count = InventoryCount(
            organization_id=user.organization_id,
            session_id=inventory_session.id,
            product_id=product.id,
            client_operation_id=client_operation_id,
            expected_quantity=balance.quantity,
            client_expected_quantity=client_expected_quantity,
            counted_quantity=counted_quantity,
            quantity_difference=difference,
            scanned_code=normalized_code,
            reason_code=normalized_reason,
            reason_note=reason_note.strip() if reason_note else None,
            recorded_by=user.id,
            client_recorded_at=recorded_at,
        )
        self.session.add(count)
        self.session.flush()
        self._audit(
            user=user,
            action="inventory.count_recorded",
            inventory_session=inventory_session,
            correlation_id=correlation_id,
            details={
                "count_id": count.id,
                "product_id": product.id,
                "expected_quantity": str(balance.quantity),
                "counted_quantity": str(counted_quantity),
                "client_operation_id": client_operation_id,
            },
        )
        return count

    def complete(
        self,
        *,
        user: User,
        session_id: str,
        note: str | None,
        correlation_id: str,
    ) -> InventorySession:
        inventory_session = self._locked_session(
            user.organization_id, session_id
        )
        if inventory_session.status != "OPEN":
            raise InventorySessionStateError
        latest_counts = self.latest_counts(inventory_session)
        if not latest_counts:
            raise InventoryCountRequiredError

        high_difference = self._has_high_difference(
            user.organization_id, latest_counts
        )
        inventory_session.completion_note = note.strip() if note else None
        if high_difference and user.role not in ("admin", "manager"):
            inventory_session.status = "PENDING_APPROVAL"
            inventory_session.approval_required = True
            review = ReviewTask(
                organization_id=user.organization_id,
                task_type="INVENTORY_APPROVAL",
                entity_type="inventory_session",
                entity_id=inventory_session.id,
                reason_code="LARGE_INVENTORY_DIFFERENCE",
                context={
                    "inventory_session_id": inventory_session.id,
                    "name": inventory_session.name,
                    "threshold": str(self.settings.inventory_approval_threshold),
                    "counted_products": len(latest_counts),
                },
            )
            self.session.add(review)
            self.session.flush()
            inventory_session.review_task_id = review.id
            self._audit(
                user=user,
                action="inventory.approval_requested",
                inventory_session=inventory_session,
                correlation_id=correlation_id,
                details={
                    "review_task_id": review.id,
                    "threshold": str(
                        self.settings.inventory_approval_threshold
                    ),
                },
            )
            return inventory_session

        self._apply_corrections(
            inventory_session=inventory_session,
            latest_counts=latest_counts,
            user=user,
            correlation_id=correlation_id,
            approved=high_difference,
        )
        return inventory_session

    def approve(
        self,
        *,
        user: User,
        session_id: str,
        note: str | None,
        correlation_id: str,
    ) -> InventorySession:
        if user.role not in ("admin", "manager"):
            raise InventoryApprovalRequiredError
        inventory_session = self._locked_session(
            user.organization_id, session_id
        )
        if inventory_session.status != "PENDING_APPROVAL":
            raise InventorySessionStateError
        latest_counts = self.latest_counts(inventory_session)
        if not latest_counts:
            raise InventoryCountRequiredError
        if note:
            inventory_session.completion_note = note.strip()
        self._apply_corrections(
            inventory_session=inventory_session,
            latest_counts=latest_counts,
            user=user,
            correlation_id=correlation_id,
            approved=True,
        )
        return inventory_session

    def cancel(
        self,
        *,
        user: User,
        session_id: str,
        note: str,
        correlation_id: str,
    ) -> InventorySession:
        inventory_session = self._locked_session(
            user.organization_id, session_id
        )
        if inventory_session.status not in ("OPEN", "PENDING_APPROVAL"):
            raise InventorySessionStateError
        if (
            inventory_session.status == "PENDING_APPROVAL"
            and user.role not in ("admin", "manager")
        ):
            raise InventoryApprovalRequiredError
        inventory_session.status = "CANCELLED"
        inventory_session.cancelled_at = utc_now()
        inventory_session.completion_note = note.strip()
        self._resolve_review(inventory_session, user, note)
        self._audit(
            user=user,
            action="inventory.session_cancelled",
            inventory_session=inventory_session,
            correlation_id=correlation_id,
            details={"note": note.strip()},
        )
        return inventory_session

    @staticmethod
    def latest_counts(
        inventory_session: InventorySession,
    ) -> list[InventoryCount]:
        latest: dict[str, InventoryCount] = {}
        for count in inventory_session.counts:
            previous = latest.get(count.product_id)
            if previous is None or InventoryService._count_key(
                count
            ) > InventoryService._count_key(previous):
                latest[count.product_id] = count
        return sorted(
            latest.values(),
            key=lambda item: (item.product.name.casefold(), item.product_id),
        )

    def recent_activity(
        self, organization_id: str, product_id: str
    ) -> list[StockMovement]:
        return self.recent_activity_for_products(
            organization_id, [product_id]
        ).get(product_id, [])

    def recent_activity_for_products(
        self, organization_id: str, product_ids: list[str]
    ) -> dict[str, list[StockMovement]]:
        if not product_ids:
            return {}
        rows = list(
            self.session.scalars(
                select(StockMovement)
                .where(
                    StockMovement.organization_id == organization_id,
                    StockMovement.product_id.in_(product_ids),
                    StockMovement.movement_type.in_(
                        (
                            "GOODS_RECEIPT",
                            "VRP_SALE_IMPORT",
                            "INVENTORY_CORRECTION",
                        )
                    ),
                )
                .order_by(StockMovement.created_at.desc())
            )
        )
        latest: dict[tuple[str, str], StockMovement] = {}
        for movement in rows:
            latest.setdefault(
                (movement.product_id, movement.movement_type), movement
            )
        order = ("GOODS_RECEIPT", "VRP_SALE_IMPORT", "INVENTORY_CORRECTION")
        return {
            product_id: [
                latest[(product_id, kind)]
                for kind in order
                if (product_id, kind) in latest
            ]
            for product_id in product_ids
        }

    def _apply_corrections(
        self,
        *,
        inventory_session: InventorySession,
        latest_counts: list[InventoryCount],
        user: User,
        correlation_id: str,
        approved: bool,
    ) -> None:
        correction_ids: list[str] = []
        total_delta = Decimal("0")
        stock_service = StockService(self.session)
        for count in latest_counts:
            balance = self._balance(user.organization_id, count.product_id)
            expected = balance.quantity
            delta = count.counted_quantity - expected
            if delta == 0:
                continue
            reason_code = count.reason_code or "STOCK_CHANGED_DURING_COUNT"
            reason = count.reason_note or reason_code
            result = stock_service.correct_to(
                user=user,
                product_id=count.product_id,
                counted_quantity=count.counted_quantity,
                idempotency_key=(
                    f"inventory:{inventory_session.id}:{count.id}:correction"
                ),
                correlation_id=correlation_id,
                reason=reason,
            )
            correction = self.session.scalar(
                select(InventoryStockCorrection).where(
                    InventoryStockCorrection.count_id == count.id
                )
            )
            if correction is None:
                correction = InventoryStockCorrection(
                    organization_id=user.organization_id,
                    session_id=inventory_session.id,
                    count_id=count.id,
                    product_id=count.product_id,
                    movement_id=result.movement.id,
                    expected_quantity=expected,
                    counted_quantity=count.counted_quantity,
                    quantity_delta=delta,
                    reason_code=reason_code,
                    reason_note=count.reason_note,
                    created_by=user.id,
                    approved_by=user.id if approved else None,
                )
                self.session.add(correction)
                self.session.flush()
            correction_ids.append(correction.id)
            total_delta += delta

        now = utc_now()
        inventory_session.status = "COMPLETED"
        inventory_session.completed_by = user.id
        inventory_session.completed_at = now
        if approved:
            inventory_session.approval_required = True
            inventory_session.approved_by = user.id
        self._resolve_review(
            inventory_session,
            user,
            inventory_session.completion_note or "Leltár jóváhagyva.",
        )
        self.session.add(
            OutboxEvent(
                organization_id=user.organization_id,
                event_type="inventory.corrected",
                aggregate_type="inventory_session",
                aggregate_id=inventory_session.id,
                payload={
                    "inventory_session_id": inventory_session.id,
                    "correction_ids": correction_ids,
                    "correction_count": len(correction_ids),
                    "counted_product_count": len(latest_counts),
                    "total_quantity_delta": str(total_delta),
                    "correlation_id": correlation_id,
                },
            )
        )
        self._audit(
            user=user,
            action="inventory.session_completed",
            inventory_session=inventory_session,
            correlation_id=correlation_id,
            details={
                "correction_count": len(correction_ids),
                "counted_product_count": len(latest_counts),
                "total_quantity_delta": str(total_delta),
                "approved": approved,
            },
        )

    def _has_high_difference(
        self,
        organization_id: str,
        latest_counts: list[InventoryCount],
    ) -> bool:
        threshold = self.settings.inventory_approval_threshold
        return any(
            abs(
                count.counted_quantity
                - self._balance(organization_id, count.product_id).quantity
            )
            > threshold
            for count in latest_counts
        )

    def _locked_session(
        self, organization_id: str, session_id: str
    ) -> InventorySession:
        inventory_session = self.session.scalar(
            select(InventorySession)
            .options(
                selectinload(InventorySession.counts).selectinload(
                    InventoryCount.product
                )
            )
            .execution_options(populate_existing=True)
            .where(
                InventorySession.id == session_id,
                InventorySession.organization_id == organization_id,
            )
            .with_for_update()
        )
        if inventory_session is None:
            raise InventorySessionNotFoundError
        return inventory_session

    def _balance(self, organization_id: str, product_id: str) -> StockBalance:
        balance = self.session.scalar(
            select(StockBalance).where(
                StockBalance.organization_id == organization_id,
                StockBalance.product_id == product_id,
            )
        )
        if balance is None:
            balance = StockBalance(
                organization_id=organization_id,
                product_id=product_id,
                quantity=Decimal("0"),
            )
            self.session.add(balance)
            self.session.flush()
        return balance

    @staticmethod
    def _count_key(count: InventoryCount) -> tuple[datetime, datetime, str]:
        client_time = count.client_recorded_at
        if client_time.tzinfo is None:
            client_time = client_time.replace(tzinfo=UTC)
        created_time = count.created_at
        if created_time.tzinfo is None:
            created_time = created_time.replace(tzinfo=UTC)
        return client_time, created_time, count.id

    @staticmethod
    def _validate_client_timestamp(value: datetime) -> datetime:
        normalized = value if value.tzinfo else value.replace(tzinfo=UTC)
        normalized = normalized.astimezone(UTC)
        now = utc_now()
        if normalized > now + timedelta(minutes=5):
            raise InventoryClientTimestampError
        if normalized < now - timedelta(days=30):
            raise InventoryClientTimestampError
        return normalized

    def _resolve_review(
        self,
        inventory_session: InventorySession,
        user: User,
        note: str,
    ) -> None:
        if not inventory_session.review_task_id:
            return
        review = self.session.scalar(
            select(ReviewTask).where(
                ReviewTask.id == inventory_session.review_task_id,
                ReviewTask.organization_id == user.organization_id,
            )
        )
        if review is not None and review.status == "OPEN":
            review.status = "RESOLVED"
            review.resolved_by = user.id
            review.resolution_note = note[:1000]
            review.resolved_at = utc_now()

    def _audit(
        self,
        *,
        user: User,
        action: str,
        inventory_session: InventorySession,
        correlation_id: str,
        details: dict,
    ) -> None:
        self.session.add(
            AuditLog(
                organization_id=user.organization_id,
                actor_id=user.id,
                action=action,
                entity_type="inventory_session",
                entity_id=inventory_session.id,
                correlation_id=correlation_id,
                details=details,
            )
        )
