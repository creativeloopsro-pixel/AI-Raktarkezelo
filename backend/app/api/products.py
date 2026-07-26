from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.dependencies import CurrentUser, DbSession, InteractiveUser, require_permissions
from app.models import AuditLog, PackagingUnit, Product, ProductBarcode, StockBalance
from app.schemas import ProductCreate, ProductRead

router = APIRouter(prefix="/products", tags=["products"])
CatalogReader = Annotated[object, Depends(require_permissions("products.read"))]
CatalogEditor = Annotated[object, Depends(require_permissions("products.write"))]


def _product_query():
    return select(Product).options(
        selectinload(Product.packaging_units),
        selectinload(Product.barcodes),
    )


@router.get("", response_model=list[ProductRead])
def list_products(
    session: DbSession,
    user: CurrentUser,
    _: CatalogReader,
    search: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[Product]:
    statement = _product_query().where(
        Product.organization_id == user.organization_id,
        Product.status == "active",
    )
    if search:
        pattern = f"%{search.strip()}%"
        statement = statement.where(
            or_(Product.name.ilike(pattern), Product.internal_sku.ilike(pattern))
        )
    return list(session.scalars(statement.order_by(Product.name).limit(limit)).unique())


@router.post("", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
def create_product(
    payload: ProductCreate,
    session: DbSession,
    user: CurrentUser,
    _: CatalogEditor,
) -> Product:
    product = Product(
        organization_id=user.organization_id,
        name=payload.name.strip(),
        internal_sku=payload.internal_sku.strip().upper(),
        base_unit=payload.base_unit,
        min_stock=payload.min_stock,
    )
    session.add(product)
    unit_by_name: dict[str, PackagingUnit] = {}
    for unit_input in payload.packaging_units:
        unit = PackagingUnit(
            organization_id=user.organization_id,
            product=product,
            name=unit_input.name.strip(),
            multiplier_to_base_unit=unit_input.multiplier_to_base_unit,
        )
        unit_by_name[unit.name.casefold()] = unit
        session.add(unit)

    for barcode_input in payload.barcodes:
        unit = (
            unit_by_name.get(barcode_input.packaging_unit_name.casefold())
            if barcode_input.packaging_unit_name
            else None
        )
        if barcode_input.packaging_unit_name and unit is None:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "unknown_packaging_unit",
                    "message": "A vonalkód ismeretlen csomagolási egységre hivatkozik.",
                },
            )
        session.add(
            ProductBarcode(
                organization_id=user.organization_id,
                product=product,
                packaging_unit=unit,
                code=barcode_input.code.strip(),
                symbology=barcode_input.symbology,
                is_primary=barcode_input.is_primary,
            )
        )

    correlation_id = str(uuid4())
    try:
        session.flush()
        session.add(
            StockBalance(
                organization_id=user.organization_id,
                product_id=product.id,
            )
        )
        session.add(
            AuditLog(
                organization_id=user.organization_id,
                actor_id=user.id,
                action="catalog.product_created",
                entity_type="product",
                entity_id=product.id,
                correlation_id=correlation_id,
                details={"sku": product.internal_sku, "name": product.name},
            )
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail={
                "code": "product_conflict",
                "message": "Az SKU vagy a vonalkód már használatban van.",
            },
        ) from exc
    return session.scalar(_product_query().where(Product.id == product.id))


@router.get("/by-code/{code}", response_model=ProductRead)
def get_product_by_code(
    code: str,
    session: DbSession,
    user: CurrentUser,
    _: CatalogReader,
) -> Product:
    product = session.scalar(
        _product_query()
        .join(ProductBarcode)
        .where(
            Product.organization_id == user.organization_id,
            ProductBarcode.organization_id == user.organization_id,
            ProductBarcode.code == code,
            Product.status == "active",
        )
    )
    if product is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "product_not_found", "message": "A kódhoz nem tartozik termék."},
        )
    return product


@router.get("/{product_id}", response_model=ProductRead)
def get_product(
    product_id: str,
    session: DbSession,
    user: CurrentUser,
    _: CatalogReader,
) -> Product:
    product = session.scalar(
        _product_query().where(
            Product.id == product_id,
            Product.organization_id == user.organization_id,
            Product.status == "active",
        )
    )
    if product is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "product_not_found", "message": "A termék nem található."},
        )
    return product


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(
    product_id: str,
    session: DbSession,
    user: InteractiveUser,
    _: CatalogEditor,
) -> None:
    product = session.scalar(
        select(Product)
        .where(
            Product.id == product_id,
            Product.organization_id == user.organization_id,
            Product.status == "active",
        )
        .with_for_update()
    )
    if product is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "product_not_found", "message": "A termék nem található."},
        )

    balance = session.scalar(
        select(StockBalance).where(
            StockBalance.organization_id == user.organization_id,
            StockBalance.product_id == product.id,
        )
    )
    if balance is not None and balance.quantity != 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "product_has_stock",
                "message": "Csak nulla készletű termék törölhető.",
            },
        )

    product.status = "archived"
    product.version += 1
    session.add(
        AuditLog(
            organization_id=user.organization_id,
            actor_id=user.id,
            action="catalog.product_deleted",
            entity_type="product",
            entity_id=product.id,
            correlation_id=str(uuid4()),
            details={
                "sku": product.internal_sku,
                "name": product.name,
                "deletion_mode": "audit_safe_archive",
            },
        )
    )
    session.commit()
