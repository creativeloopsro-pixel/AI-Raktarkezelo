from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import (
    InventoryCount,
    InventoryStockCorrection,
    Organization,
    ProductBarcode,
    ReviewTask,
    StockBalance,
    StockMovement,
    User,
)
from app.security import hash_password
from app.services.inventory import (
    InventoryService,
    InventorySessionNotFoundError,
)


def settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


def test_inventory_counts_are_idempotent_and_latest_count_is_applied(
    session: Session, seeded
) -> None:
    organization, admin, product = seeded
    balance = session.get(StockBalance, (organization.id, product.id))
    balance.quantity = Decimal("10")
    service = InventoryService(session, settings=settings())
    inventory_session = service.start(
        user=admin,
        client_session_id="inventory-session-1",
        name="Szombati leltár",
        correlation_id="inventory-start-1",
    )

    first = service.record_count(
        user=admin,
        session_id=inventory_session.id,
        product_id=product.id,
        counted_quantity=Decimal("8"),
        client_operation_id="count-operation-1",
        client_recorded_at=datetime.now(UTC),
        client_expected_quantity=Decimal("10"),
        scanned_code=None,
        reason_code="PHYSICAL_COUNT",
        reason_note=None,
        correlation_id="inventory-count-1",
    )
    duplicate = service.record_count(
        user=admin,
        session_id=inventory_session.id,
        product_id=product.id,
        counted_quantity=Decimal("8"),
        client_operation_id="count-operation-1",
        client_recorded_at=datetime.now(UTC),
        client_expected_quantity=Decimal("10"),
        scanned_code=None,
        reason_code="PHYSICAL_COUNT",
        reason_note=None,
        correlation_id="inventory-count-duplicate",
    )
    second = service.record_count(
        user=admin,
        session_id=inventory_session.id,
        product_id=product.id,
        counted_quantity=Decimal("7"),
        client_operation_id="count-operation-2",
        client_recorded_at=datetime.now(UTC),
        client_expected_quantity=Decimal("10"),
        scanned_code=None,
        reason_code="PHYSICAL_COUNT",
        reason_note="Újraszámolva",
        correlation_id="inventory-count-2",
    )
    assert duplicate.id == first.id
    assert second.id != first.id
    assert session.scalar(select(func.count()).select_from(InventoryCount)) == 2

    completed = service.complete(
        user=admin,
        session_id=inventory_session.id,
        note="Leltár lezárva",
        correlation_id="inventory-complete-1",
    )
    session.commit()

    assert completed.status == "COMPLETED"
    session.refresh(balance)
    assert balance.quantity == Decimal("7")
    movement = session.scalar(
        select(StockMovement).where(
            StockMovement.source_type == "MANUAL_COUNT"
        )
    )
    assert movement is not None
    assert movement.quantity_delta == Decimal("-3")
    correction = session.scalar(select(InventoryStockCorrection))
    assert correction is not None
    assert correction.count_id == second.id
    assert correction.expected_quantity == Decimal("10")
    assert correction.counted_quantity == Decimal("7")


def test_large_inventory_difference_requires_manager_approval(
    session: Session, seeded
) -> None:
    organization, admin, product = seeded
    warehouse = User(
        organization_id=organization.id,
        email="raktar@teszt.hu",
        full_name="Raktáros",
        password_hash=hash_password("Secret-1234!"),
        role="warehouse",
    )
    session.add(warehouse)
    balance = session.get(StockBalance, (organization.id, product.id))
    balance.quantity = Decimal("25")
    session.commit()
    service = InventoryService(
        session,
        settings=settings(inventory_approval_threshold=Decimal("5")),
    )
    inventory_session = service.start(
        user=warehouse,
        client_session_id="inventory-session-approval",
        name="Nagy eltérés",
        correlation_id="inventory-approval-start",
    )
    service.record_count(
        user=warehouse,
        session_id=inventory_session.id,
        product_id=product.id,
        counted_quantity=Decimal("10"),
        client_operation_id="count-operation-approval",
        client_recorded_at=datetime.now(UTC),
        client_expected_quantity=Decimal("25"),
        scanned_code=None,
        reason_code="SHRINKAGE",
        reason_note="Hiány",
        correlation_id="inventory-approval-count",
    )

    pending = service.complete(
        user=warehouse,
        session_id=inventory_session.id,
        note="Vezetői ellenőrzést kérek",
        correlation_id="inventory-approval-request",
    )
    session.commit()

    assert pending.status == "PENDING_APPROVAL"
    assert pending.approval_required is True
    assert session.scalar(select(func.count()).select_from(StockMovement)) == 0
    review = session.scalar(
        select(ReviewTask).where(
            ReviewTask.entity_id == inventory_session.id
        )
    )
    assert review is not None
    assert review.status == "OPEN"

    approved = service.approve(
        user=admin,
        session_id=inventory_session.id,
        note="Eltérés ellenőrizve",
        correlation_id="inventory-approval-complete",
    )
    session.commit()

    assert approved.status == "COMPLETED"
    assert approved.approved_by == admin.id
    session.refresh(balance)
    assert balance.quantity == Decimal("10")
    session.refresh(review)
    assert review.status == "RESOLVED"


def test_inventory_session_is_tenant_scoped(session: Session, seeded) -> None:
    _, admin, _ = seeded
    other_org = Organization(name="Másik bolt", slug="masik-bolt")
    session.add(other_org)
    session.flush()
    service = InventoryService(session, settings=settings())
    inventory_session = service.start(
        user=admin,
        client_session_id="inventory-session-tenant",
        name="Tenant leltár",
        correlation_id="inventory-tenant",
    )

    with pytest.raises(InventorySessionNotFoundError):
        service.get_session(other_org.id, inventory_session.id)


def test_inventory_api_scan_count_and_complete(client, session: Session, seeded) -> None:
    organization, _, product = seeded
    balance = session.get(StockBalance, (organization.id, product.id))
    balance.quantity = Decimal("5")
    session.add(
        ProductBarcode(
            organization_id=organization.id,
            product_id=product.id,
            code="5991234567890",
            symbology="EAN_13",
            is_primary=True,
        )
    )
    session.commit()
    login = client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": "tesztbolt",
            "email": "admin@teszt.hu",
            "password": "Secret-1234!",
        },
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    started = client.post(
        "/api/v1/inventory/sessions",
        headers=headers,
        json={
            "client_session_id": "api-inventory-session",
            "name": "API leltár",
        },
    )
    assert started.status_code == 201
    session_id = started.json()["id"]

    counted = client.post(
        f"/api/v1/inventory/sessions/{session_id}/counts",
        headers=headers,
        json={
            "product_id": product.id,
            "counted_quantity": 4,
            "client_operation_id": "api-count-operation",
            "client_recorded_at": datetime.now(UTC).isoformat(),
            "client_expected_quantity": 5,
            "scanned_code": "5991234567890",
            "reason_code": "PHYSICAL_COUNT",
        },
    )
    assert counted.status_code == 201
    assert counted.json()["counts"][0]["counted_quantity"] == "4.000"
    assert counted.json()["counts"][0]["scanned_code"] == "5991234567890"

    completed = client.post(
        f"/api/v1/inventory/sessions/{session_id}/complete",
        headers=headers,
        json={"note": "API lezárás"},
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "COMPLETED"
    session.expire_all()
    assert session.get(
        StockBalance, (organization.id, product.id)
    ).quantity == Decimal("4")
