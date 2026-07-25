from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Document,
    OutboxEvent,
    Plugin,
    PluginJob,
    PluginSetting,
    Product,
)
from app.plugins.manifest import PluginManifest
from app.queueing import dispatch_document_job
from app.services.documents import DocumentService
from app.services.stock import StockService


class PluginSdkError(Exception):
    code = "plugin_sdk_error"


class PluginPermissionDeniedError(PluginSdkError):
    code = "plugin_permission_denied"


class PluginResourceNotAssignedError(PluginSdkError):
    code = "plugin_resource_not_assigned"


class PluginEmissionDeniedError(PluginSdkError):
    code = "plugin_emission_denied"


@dataclass(frozen=True)
class PluginEvent:
    id: str
    type: str
    aggregate_type: str
    aggregate_id: str
    payload: dict[str, Any]
    correlation_id: str


class PluginContext:
    """A plugin kizárólag ezen az engedélyellenőrzött felületen érheti el a domaint."""

    def __init__(
        self,
        session: Session,
        *,
        plugin: Plugin,
        job: PluginJob,
        manifest: PluginManifest,
    ):
        self.session = session
        self.plugin = plugin
        self.job = job
        self.manifest = manifest
        self._granted = {
            permission.permission
            for permission in plugin.permissions
            if permission.granted
        }

    @property
    def organization_id(self) -> str:
        return self.plugin.organization_id

    def require(self, permission: str) -> None:
        if permission not in self.manifest.permissions or permission not in self._granted:
            raise PluginPermissionDeniedError(
                f"A plugin nem kapta meg ezt a jogosultságot: {permission}"
            )

    def list_products(self, *, limit: int = 500) -> list[dict[str, Any]]:
        self.require("products.read")
        products = self.session.scalars(
            select(Product)
            .where(
                Product.organization_id == self.organization_id,
                Product.status == "active",
            )
            .order_by(Product.name)
            .limit(min(max(limit, 1), 500))
        )
        return [
            {
                "id": product.id,
                "name": product.name,
                "internal_sku": product.internal_sku,
                "base_unit": product.base_unit,
            }
            for product in products
        ]

    def get_product(self, product_id: str) -> dict[str, Any] | None:
        self.require("products.read")
        product = self.session.scalar(
            select(Product).where(
                Product.id == product_id,
                Product.organization_id == self.organization_id,
            )
        )
        if product is None:
            return None
        return {
            "id": product.id,
            "name": product.name,
            "internal_sku": product.internal_sku,
            "base_unit": product.base_unit,
        }

    def get_assigned_document(self, document_id: str) -> dict[str, Any]:
        self.require("documents.read")
        if self.job.aggregate_type != "document" or self.job.aggregate_id != document_id:
            raise PluginResourceNotAssignedError(
                "A plugin csak az eseményben hozzárendelt dokumentumot olvashatja."
            )
        document = self.session.scalar(
            select(Document).where(
                Document.id == document_id,
                Document.organization_id == self.organization_id,
            )
        )
        if document is None:
            raise PluginResourceNotAssignedError("A dokumentum nem található.")
        return {
            "id": document.id,
            "status": document.status,
            "source_type": document.source_type,
            "document_type": document.document_type,
            "content_type": document.content_type,
            "page_count": document.page_count,
            "validation_summary": document.validation_summary,
        }

    def queue_assigned_document(self, document_id: str) -> dict[str, Any]:
        self.require("documents.process")
        self.get_assigned_document(document_id)
        result = DocumentService(self.session).queue_processing(
            organization_id=self.organization_id,
            actor_id=self.plugin.service_user_id,
            document_id=document_id,
            idempotency_key=f"plugin:{self.job.id}:document:{document_id}",
            correlation_id=self.job.correlation_id,
        )
        if result.created:
            dispatch_document_job(result.job.id)
        return {"job_id": result.job.id, "created": result.created}

    def create_stock_movement(
        self,
        *,
        product_id: str,
        quantity_delta: Decimal,
        source_id: str,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.require("stock.movements.create")
        result = StockService(self.session).apply_plugin_movement(
            user=self.plugin.service_user,
            plugin_key=self.plugin.plugin_key,
            product_id=product_id,
            quantity_delta=quantity_delta,
            source_id=source_id,
            idempotency_key=f"plugin:{self.job.id}:stock:{source_id}",
            correlation_id=self.job.correlation_id,
            details=details,
        )
        return {
            "movement_id": result.movement.id,
            "created": result.created,
            "resulting_quantity": str(result.balance.quantity),
        }

    def get_setting(self, key: str, default: Any = None) -> Any:
        self.require("settings.read")
        setting = self.session.scalar(
            select(PluginSetting).where(
                PluginSetting.plugin_id == self.plugin.id,
                PluginSetting.organization_id == self.organization_id,
                PluginSetting.setting_key == key,
            )
        )
        return default if setting is None else setting.value

    def set_setting(self, key: str, value: Any) -> None:
        self.require("settings.write")
        setting = self.session.scalar(
            select(PluginSetting).where(
                PluginSetting.plugin_id == self.plugin.id,
                PluginSetting.organization_id == self.organization_id,
                PluginSetting.setting_key == key,
            )
        )
        if setting is None:
            setting = PluginSetting(
                organization_id=self.organization_id,
                plugin_id=self.plugin.id,
                setting_key=key,
                value=value,
                updated_by=self.plugin.service_user_id,
            )
            self.session.add(setting)
        else:
            setting.value = value
            setting.updated_by = self.plugin.service_user_id

    def emit(self, event_type: str, payload: dict[str, Any]) -> str:
        if event_type not in self.manifest.emits:
            raise PluginEmissionDeniedError(
                f"A manifest nem deklarálja ezt az eseményt: {event_type}"
            )
        event = OutboxEvent(
            organization_id=self.organization_id,
            event_type=event_type,
            aggregate_type="plugin",
            aggregate_id=self.plugin.id,
            payload={
                **payload,
                "plugin_id": self.plugin.plugin_key,
                "source_plugin_job_id": self.job.id,
                "correlation_id": self.job.correlation_id,
            },
        )
        self.session.add(event)
        self.session.flush()
        return event.id
