from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    OutboxEvent,
    Product,
    StockBalance,
    StockMovement,
    User,
)


class StockError(Exception):
    code = "stock_error"


class ProductNotFoundError(StockError):
    code = "product_not_found"


class MovementNotFoundError(StockError):
    code = "movement_not_found"


class MovementAlreadyReversedError(StockError):
    code = "movement_already_reversed"


class ReversalOfReversalError(StockError):
    code = "reversal_of_reversal"


@dataclass(frozen=True)
class StockResult:
    movement: StockMovement
    balance: StockBalance
    created: bool


class StockService:
    """The only domain service allowed to change stock quantities."""

    def __init__(self, session: Session):
        self.session = session

    def receive(
        self,
        *,
        user: User,
        product_id: str,
        quantity: Decimal,
        source_id: str,
        idempotency_key: str,
        correlation_id: str,
        reason: str | None = None,
    ) -> StockResult:
        return self._apply_delta(
            user=user,
            product_id=product_id,
            quantity_delta=quantity,
            movement_type="GOODS_RECEIPT",
            source_type="MANUAL_RECEIPT",
            source_id=source_id,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
            details={"reason": reason} if reason else {},
        )

    def receive_document_item(
        self,
        *,
        user: User,
        product_id: str,
        quantity: Decimal,
        receipt_id: str,
        receipt_item_id: str,
        idempotency_key: str,
        correlation_id: str,
    ) -> StockResult:
        return self._apply_delta(
            user=user,
            product_id=product_id,
            quantity_delta=quantity,
            movement_type="GOODS_RECEIPT",
            source_type="DOCUMENT_GOODS_RECEIPT",
            source_id=receipt_id,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
            details={
                "goods_receipt_id": receipt_id,
                "goods_receipt_item_id": receipt_item_id,
            },
        )

    def correct_to(
        self,
        *,
        user: User,
        product_id: str,
        counted_quantity: Decimal,
        idempotency_key: str,
        correlation_id: str,
        reason: str,
    ) -> StockResult:
        duplicate = self._find_by_idempotency(user.organization_id, idempotency_key)
        if duplicate is not None:
            return StockResult(
                movement=duplicate,
                balance=self._get_balance(user.organization_id, duplicate.product_id),
                created=False,
            )

        product = self._get_product(user.organization_id, product_id)
        balance = self._lock_balance(user.organization_id, product.id)
        quantity_delta = counted_quantity - balance.quantity
        return self._create_movement(
            user=user,
            product=product,
            balance=balance,
            quantity_delta=quantity_delta,
            movement_type="INVENTORY_CORRECTION",
            source_type="MANUAL_COUNT",
            source_id=f"inventory:{idempotency_key}",
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
            details={
                "reason": reason,
                "previous_quantity": str(balance.quantity),
                "counted_quantity": str(counted_quantity),
            },
        )

    def reverse(
        self,
        *,
        user: User,
        movement_id: str,
        idempotency_key: str,
        correlation_id: str,
        reason: str,
    ) -> StockResult:
        duplicate = self._find_by_idempotency(user.organization_id, idempotency_key)
        if duplicate is not None:
            return StockResult(
                movement=duplicate,
                balance=self._get_balance(user.organization_id, duplicate.product_id),
                created=False,
            )

        original = self.session.scalar(
            select(StockMovement)
            .where(
                StockMovement.id == movement_id,
                StockMovement.organization_id == user.organization_id,
            )
            .with_for_update()
        )
        if original is None:
            raise MovementNotFoundError
        if original.reverses_movement_id is not None:
            raise ReversalOfReversalError

        previous_reversal = self.session.scalar(
            select(StockMovement).where(
                StockMovement.organization_id == user.organization_id,
                StockMovement.reverses_movement_id == original.id,
            )
        )
        if previous_reversal is not None:
            raise MovementAlreadyReversedError

        product = self._get_product(user.organization_id, original.product_id)
        balance = self._lock_balance(user.organization_id, original.product_id)
        return self._create_movement(
            user=user,
            product=product,
            balance=balance,
            quantity_delta=-original.quantity_delta,
            movement_type="REVERSAL",
            source_type="STOCK_MOVEMENT",
            source_id=original.id,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
            details={"reason": reason, "original_movement_type": original.movement_type},
            reverses_movement_id=original.id,
        )

    def _apply_delta(
        self,
        *,
        user: User,
        product_id: str,
        quantity_delta: Decimal,
        movement_type: str,
        source_type: str,
        source_id: str,
        idempotency_key: str,
        correlation_id: str,
        details: dict,
    ) -> StockResult:
        duplicate = self._find_by_idempotency(user.organization_id, idempotency_key)
        if duplicate is not None:
            return StockResult(
                movement=duplicate,
                balance=self._get_balance(user.organization_id, duplicate.product_id),
                created=False,
            )

        product = self._get_product(user.organization_id, product_id)
        balance = self._lock_balance(user.organization_id, product.id)
        return self._create_movement(
            user=user,
            product=product,
            balance=balance,
            quantity_delta=quantity_delta,
            movement_type=movement_type,
            source_type=source_type,
            source_id=source_id,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
            details=details,
        )

    def _create_movement(
        self,
        *,
        user: User,
        product: Product,
        balance: StockBalance,
        quantity_delta: Decimal,
        movement_type: str,
        source_type: str,
        source_id: str,
        idempotency_key: str,
        correlation_id: str,
        details: dict,
        reverses_movement_id: str | None = None,
    ) -> StockResult:
        resulting_quantity = balance.quantity + quantity_delta
        movement_details = {
            **details,
            "resulting_quantity": str(resulting_quantity),
            "negative_stock": resulting_quantity < 0,
        }
        movement = StockMovement(
            organization_id=user.organization_id,
            product_id=product.id,
            movement_type=movement_type,
            quantity_delta=quantity_delta,
            source_type=source_type,
            source_id=source_id,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
            created_by=user.id,
            reverses_movement_id=reverses_movement_id,
            details=movement_details,
        )
        balance.quantity = resulting_quantity
        balance.version += 1
        self.session.add(movement)
        self.session.flush()
        self.session.add(
            AuditLog(
                organization_id=user.organization_id,
                actor_id=user.id,
                action=f"stock.{movement_type.lower()}",
                entity_type="stock_movement",
                entity_id=movement.id,
                correlation_id=correlation_id,
                details={
                    "product_id": product.id,
                    "quantity_delta": str(quantity_delta),
                    "resulting_quantity": str(resulting_quantity),
                },
            )
        )
        self.session.add(
            OutboxEvent(
                organization_id=user.organization_id,
                event_type="stock.changed",
                aggregate_type="product",
                aggregate_id=product.id,
                payload={
                    "movement_id": movement.id,
                    "quantity_delta": str(quantity_delta),
                    "resulting_quantity": str(resulting_quantity),
                    "correlation_id": correlation_id,
                },
            )
        )
        return StockResult(movement=movement, balance=balance, created=True)

    def _find_by_idempotency(
        self, organization_id: str, idempotency_key: str
    ) -> StockMovement | None:
        return self.session.scalar(
            select(StockMovement).where(
                StockMovement.organization_id == organization_id,
                StockMovement.idempotency_key == idempotency_key,
            )
        )

    def _get_product(self, organization_id: str, product_id: str) -> Product:
        product = self.session.scalar(
            select(Product).where(
                Product.id == product_id,
                Product.organization_id == organization_id,
                Product.status == "active",
            )
        )
        if product is None:
            raise ProductNotFoundError
        return product

    def _get_balance(self, organization_id: str, product_id: str) -> StockBalance:
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

    def _lock_balance(self, organization_id: str, product_id: str) -> StockBalance:
        balance = self.session.scalar(
            select(StockBalance)
            .where(
                StockBalance.organization_id == organization_id,
                StockBalance.product_id == product_id,
            )
            .with_for_update()
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
