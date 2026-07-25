from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    Organization,
    OutboxEvent,
    Product,
    StockBalance,
    StockMovement,
)
from app.services.stock import (
    MovementAlreadyReversedError,
    ProductNotFoundError,
    StockService,
)


def test_receive_is_idempotent_and_updates_all_transaction_records(
    session: Session, seeded
) -> None:
    _, user, product = seeded
    service = StockService(session)

    first = service.receive(
        user=user,
        product_id=product.id,
        quantity=Decimal("12"),
        source_id="receipt-1",
        idempotency_key="receive-operation-1",
        correlation_id="correlation-1",
    )
    session.commit()
    second = service.receive(
        user=user,
        product_id=product.id,
        quantity=Decimal("12"),
        source_id="receipt-1",
        idempotency_key="receive-operation-1",
        correlation_id="correlation-2",
    )
    session.commit()

    balance = session.get(StockBalance, (user.organization_id, product.id))
    assert first.created is True
    assert second.created is False
    assert first.movement.id == second.movement.id
    assert balance is not None
    assert balance.quantity == Decimal("12.000")
    assert session.scalar(select(func.count()).select_from(StockMovement)) == 1
    assert session.scalar(select(func.count()).select_from(AuditLog)) == 1
    assert session.scalar(select(func.count()).select_from(OutboxEvent)) == 1


def test_correction_sets_absolute_count_and_reversal_restores_previous_balance(
    session: Session, seeded
) -> None:
    _, user, product = seeded
    service = StockService(session)
    receipt = service.receive(
        user=user,
        product_id=product.id,
        quantity=Decimal("20"),
        source_id="receipt-2",
        idempotency_key="receive-operation-2",
        correlation_id="correlation-2",
    )
    session.commit()

    correction = service.correct_to(
        user=user,
        product_id=product.id,
        counted_quantity=Decimal("17"),
        idempotency_key="correction-operation-1",
        correlation_id="correlation-3",
        reason="Leltár",
    )
    session.commit()
    assert correction.movement.quantity_delta == Decimal("-3")
    assert correction.balance.quantity == Decimal("17")

    reversal = service.reverse(
        user=user,
        movement_id=receipt.movement.id,
        idempotency_key="reversal-operation-1",
        correlation_id="correlation-4",
        reason="Téves bevételezés",
    )
    session.commit()
    assert reversal.movement.quantity_delta == Decimal("-20")
    assert reversal.balance.quantity == Decimal("-3")
    movement_sum = session.scalar(
        select(func.sum(StockMovement.quantity_delta)).where(
            StockMovement.organization_id == user.organization_id,
            StockMovement.product_id == product.id,
        )
    )
    assert movement_sum == reversal.balance.quantity

    with pytest.raises(MovementAlreadyReversedError):
        service.reverse(
            user=user,
            movement_id=receipt.movement.id,
            idempotency_key="reversal-operation-2",
            correlation_id="correlation-5",
            reason="Ismételt próbálkozás",
        )


def test_product_from_another_organization_cannot_be_modified(session: Session, seeded) -> None:
    _, user, _ = seeded
    other_organization = Organization(name="Másik bolt", slug="masik-bolt")
    session.add(other_organization)
    session.flush()
    other_product = Product(
        organization_id=other_organization.id,
        name="Másik termék",
        internal_sku="OTHER-001",
    )
    session.add(other_product)
    session.commit()

    with pytest.raises(ProductNotFoundError):
        StockService(session).receive(
            user=user,
            product_id=other_product.id,
            quantity=Decimal("1"),
            source_id="cross-tenant-attempt",
            idempotency_key="cross-tenant-operation-1",
            correlation_id="correlation-tenant",
        )

    assert (
        session.scalar(
            select(func.count())
            .select_from(StockMovement)
            .where(StockMovement.product_id == other_product.id)
        )
        == 0
    )
