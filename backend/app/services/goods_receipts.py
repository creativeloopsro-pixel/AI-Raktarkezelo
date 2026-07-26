from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import Settings, get_settings
from app.models import (
    AiResult,
    AuditLog,
    Document,
    GoodsReceiptDraft,
    GoodsReceiptItem,
    OutboxEvent,
    PackagingUnit,
    Product,
    ReviewTask,
    User,
    utc_now,
)
from app.services.stock import StockService


class GoodsReceiptError(Exception):
    code = "goods_receipt_error"


class GoodsReceiptNotFoundError(GoodsReceiptError):
    code = "goods_receipt_not_found"


class GoodsReceiptItemNotFoundError(GoodsReceiptError):
    code = "goods_receipt_item_not_found"


class GoodsReceiptNotReadyError(GoodsReceiptError):
    code = "goods_receipt_not_ready"


class InvalidProductMatchError(GoodsReceiptError):
    code = "invalid_product_match"


class GoodsReceiptService:
    def __init__(self, session: Session, settings: Settings | None = None):
        self.session = session
        self.settings = settings or get_settings()

    def get_by_document(self, organization_id: str, document_id: str) -> GoodsReceiptDraft:
        draft = self.session.scalar(
            select(GoodsReceiptDraft)
            .options(
                selectinload(GoodsReceiptDraft.items).selectinload(
                    GoodsReceiptItem.matched_product
                ),
                selectinload(GoodsReceiptDraft.items).selectinload(
                    GoodsReceiptItem.packaging_unit
                ),
                selectinload(GoodsReceiptDraft.ai_result).selectinload(AiResult.request),
            )
            .where(
                GoodsReceiptDraft.organization_id == organization_id,
                GoodsReceiptDraft.document_id == document_id,
            )
        )
        if draft is None:
            raise GoodsReceiptNotFoundError
        return draft

    def update_item(
        self,
        *,
        user: User,
        draft_id: str,
        item_id: str,
        product_id: str,
        packaging_unit_id: str | None,
        quantity: Decimal,
        correlation_id: str,
    ) -> GoodsReceiptDraft:
        draft = self._locked_draft(user.organization_id, draft_id)
        if draft.status == "CONFIRMED":
            raise GoodsReceiptNotReadyError
        item = self.session.scalar(
            select(GoodsReceiptItem)
            .where(
                GoodsReceiptItem.id == item_id,
                GoodsReceiptItem.draft_id == draft.id,
                GoodsReceiptItem.organization_id == user.organization_id,
            )
            .with_for_update()
        )
        if item is None:
            raise GoodsReceiptItemNotFoundError
        product = self.session.scalar(
            select(Product).where(
                Product.id == product_id,
                Product.organization_id == user.organization_id,
                Product.status == "active",
            )
        )
        if product is None:
            raise InvalidProductMatchError

        packaging: PackagingUnit | None = None
        factor = Decimal("1")
        if packaging_unit_id:
            packaging = self.session.scalar(
                select(PackagingUnit).where(
                    PackagingUnit.id == packaging_unit_id,
                    PackagingUnit.organization_id == user.organization_id,
                    PackagingUnit.product_id == product.id,
                )
            )
            if packaging is None:
                raise InvalidProductMatchError
            factor = packaging.multiplier_to_base_unit

        item.matched_product_id = product.id
        item.packaging_unit_id = packaging.id if packaging else None
        item.quantity = quantity
        item.unit = packaging.name if packaging else product.base_unit
        item.conversion_factor = factor
        item.base_quantity = quantity * factor
        item.match_method = "MANUAL"
        item.status = "READY"
        item.validation_issues = []
        self._refresh_draft_state(draft)
        self.session.add(
            AuditLog(
                organization_id=user.organization_id,
                actor_id=user.id,
                action="goods_receipt.item_matched",
                entity_type="goods_receipt_item",
                entity_id=item.id,
                correlation_id=correlation_id,
                details={
                    "product_id": product.id,
                    "packaging_unit_id": packaging.id if packaging else None,
                    "base_quantity": str(item.base_quantity),
                },
            )
        )
        self.session.commit()
        return self.get_by_document(user.organization_id, draft.document_id)

    def confirm(
        self,
        *,
        user: User,
        draft_id: str,
        correlation_id: str,
        confirmation_source: str = "MANUAL",
    ) -> GoodsReceiptDraft:
        draft = self._locked_draft(user.organization_id, draft_id)
        if draft.status == "CONFIRMED":
            return self.get_by_document(user.organization_id, draft.document_id)
        items = list(
            self.session.scalars(
                select(GoodsReceiptItem)
                .where(
                    GoodsReceiptItem.draft_id == draft.id,
                    GoodsReceiptItem.organization_id == user.organization_id,
                )
                .order_by(GoodsReceiptItem.line_number)
                .with_for_update()
            )
        )
        if (
            draft.status != "READY"
            or not items
            or any(
                item.status != "READY"
                or item.matched_product_id is None
                or item.base_quantity is None
                or item.base_quantity <= 0
                for item in items
            )
        ):
            raise GoodsReceiptNotReadyError

        stock_service = StockService(self.session)
        for item in items:
            stock_service.receive_document_item(
                user=user,
                product_id=item.matched_product_id,
                quantity=item.base_quantity,
                receipt_id=draft.id,
                receipt_item_id=item.id,
                idempotency_key=f"goods-receipt:{draft.id}:{item.id}",
                correlation_id=correlation_id,
            )

        now = utc_now()
        draft.status = "CONFIRMED"
        draft.confirmed_by = user.id
        draft.confirmed_at = now
        document = self.session.scalar(
            select(Document).where(
                Document.id == draft.document_id,
                Document.organization_id == user.organization_id,
            )
        )
        if document is not None:
            document.status = "COMPLETED"

        open_reviews = self.session.scalars(
            select(ReviewTask).where(
                ReviewTask.organization_id == user.organization_id,
                ReviewTask.entity_type == "goods_receipt_draft",
                ReviewTask.entity_id == draft.id,
                ReviewTask.status == "OPEN",
            )
        )
        for task in open_reviews:
            task.status = "RESOLVED"
            task.resolved_by = user.id
            task.resolution_note = (
                "Az AI magas biztonságú egyezés alapján automatikusan bevételezte."
                if confirmation_source == "AI_AUTOMATIC"
                else "A bevételezési tervezet ellenőrizve és jóváhagyva."
            )
            task.resolved_at = now

        self.session.add(
            AuditLog(
                organization_id=user.organization_id,
                actor_id=user.id,
                action="goods_receipt.confirmed",
                entity_type="goods_receipt",
                entity_id=draft.id,
                correlation_id=correlation_id,
                details={
                    "document_id": draft.document_id,
                    "item_count": len(items),
                    "confirmation_source": confirmation_source,
                },
            )
        )
        self.session.add(
            OutboxEvent(
                organization_id=user.organization_id,
                event_type="goods_receipt.confirmed",
                aggregate_type="goods_receipt",
                aggregate_id=draft.id,
                payload={
                    "document_id": draft.document_id,
                    "item_count": len(items),
                    "confirmation_source": confirmation_source,
                    "correlation_id": correlation_id,
                },
            )
        )
        self.session.commit()
        return self.get_by_document(user.organization_id, draft.document_id)

    def _locked_draft(self, organization_id: str, draft_id: str) -> GoodsReceiptDraft:
        draft = self.session.scalar(
            select(GoodsReceiptDraft)
            .where(
                GoodsReceiptDraft.id == draft_id,
                GoodsReceiptDraft.organization_id == organization_id,
            )
            .with_for_update()
        )
        if draft is None:
            raise GoodsReceiptNotFoundError
        return draft

    def _refresh_draft_state(self, draft: GoodsReceiptDraft) -> None:
        items = list(
            self.session.scalars(
                select(GoodsReceiptItem).where(GoodsReceiptItem.draft_id == draft.id)
            )
        )
        unresolved = sorted(
            {
                issue
                for item in items
                for issue in item.validation_issues
                if item.status != "READY"
            }
        )
        draft.validation_issues = unresolved
        draft.status = (
            "READY"
            if items and all(item.status == "READY" for item in items)
            else "NEEDS_REVIEW"
        )
        document = self.session.scalar(
            select(Document).where(
                Document.id == draft.document_id,
                Document.organization_id == draft.organization_id,
            )
        )
        if document is not None:
            document.status = (
                "READY_FOR_CONFIRMATION" if draft.status == "READY" else "NEEDS_REVIEW"
            )
