from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, Product, StockBalance


def _admin_headers(client) -> dict[str, str]:
    login = client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": "tesztbolt",
            "email": "admin@teszt.hu",
            "password": "Secret-1234!",
        },
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_zero_stock_product_can_be_deleted(
    client,
    session: Session,
    seeded,
) -> None:
    _, _, product = seeded
    headers = _admin_headers(client)

    response = client.delete(f"/api/v1/products/{product.id}", headers=headers)

    assert response.status_code == 204
    assert client.get("/api/v1/products", headers=headers).json() == []
    assert client.get(
        f"/api/v1/products/{product.id}",
        headers=headers,
    ).status_code == 404

    session.expire_all()
    archived = session.get(Product, product.id)
    assert archived is not None
    assert archived.status == "archived"
    audit = session.scalar(
        select(AuditLog).where(
            AuditLog.action == "catalog.product_deleted",
            AuditLog.entity_id == product.id,
        )
    )
    assert audit is not None


def test_product_with_stock_cannot_be_deleted(
    client,
    session: Session,
    seeded,
) -> None:
    organization, _, product = seeded
    balance = session.scalar(
        select(StockBalance).where(
            StockBalance.organization_id == organization.id,
            StockBalance.product_id == product.id,
        )
    )
    assert balance is not None
    balance.quantity = 2
    session.commit()
    headers = _admin_headers(client)

    response = client.delete(f"/api/v1/products/{product.id}", headers=headers)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "product_has_stock"
    session.refresh(product)
    assert product.status == "active"
