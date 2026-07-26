from __future__ import annotations

from app.models import VrpImportBatch
from app.plugins.registry import plugin_registry
from app.plugins.sdk import PluginContext, PluginEvent
from app.services.vrp_imports import VrpImportService


@plugin_registry.handler("ai-goods-receipt", "document.uploaded")
def handle_ai_document_uploaded(
    context: PluginContext, event: PluginEvent
) -> dict:
    document = context.get_assigned_document(event.aggregate_id)
    if document["document_type"] not in {"goods_receipt", "delivery_note"}:
        return {"status": "SKIPPED", "reason": "unsupported_document_type"}
    if document["status"] != "UPLOADED":
        return {"status": "SKIPPED", "reason": "document_not_upload_ready"}
    if not bool(event.payload.get("auto_process_requested", False)):
        return {"status": "SKIPPED", "reason": "automatic_processing_not_requested"}
    if (
        document["source_type"] == "EMAIL_ATTACHMENT"
        and not context.get_setting("auto_process_email", True)
    ):
        return {"status": "SKIPPED", "reason": "email_automation_disabled"}
    queued = context.queue_assigned_document(document["id"])
    return {"status": "QUEUED", **queued}


@plugin_registry.handler("vrp-import", "schedule.triggered")
def handle_vrp_schedule_triggered(
    context: PluginContext, event: PluginEvent
) -> dict:
    context.require("stock.movements.create")
    batch_id = str(event.payload.get("batch_id", "")).strip()
    if not batch_id:
        return {"status": "SKIPPED", "reason": "batch_id_missing"}
    batch = context.session.get(VrpImportBatch, batch_id)
    if batch is None or batch.organization_id != context.organization_id:
        return {"status": "SKIPPED", "reason": "batch_not_found"}
    processed = VrpImportService(context.session).process(
        user=context.plugin.service_user,
        batch_id=batch.id,
        correlation_id=event.correlation_id,
    )
    return {"status": processed.status, "batch_id": processed.id}


@plugin_registry.handler("sample-stock-audit", "stock.changed")
def handle_sample_stock_changed(
    context: PluginContext, event: PluginEvent
) -> dict:
    product = context.get_product(event.aggregate_id)
    if product is None:
        return {"status": "SKIPPED", "reason": "product_not_found"}
    include_name = context.get_setting("include_product_name", True)
    payload = {
        "product_id": product["id"],
        "movement_id": event.payload.get("movement_id"),
        "quantity_delta": event.payload.get("quantity_delta"),
        "resulting_quantity": event.payload.get("resulting_quantity"),
    }
    if include_name:
        payload["product_name"] = product["name"]
    emitted_event_id = context.emit("sample.stock.observed", payload)
    return {"status": "OBSERVED", "emitted_event_id": emitted_event_id}
