from app.plugins.registry import plugin_registry
from app.plugins.sdk import PluginContext, PluginEvent


@plugin_registry.handler("product-observer", "stock.changed")
def handle_stock_changed(
    context: PluginContext,
    event: PluginEvent,
) -> dict:
    product = context.get_product(event.aggregate_id)
    if product is None:
        return {"status": "SKIPPED", "reason": "product_not_found"}

    payload = {
        "product_id": product["id"],
        "movement_id": event.payload.get("movement_id"),
        "resulting_quantity": event.payload.get("resulting_quantity"),
    }
    if context.get_setting("include_product_name", True):
        payload["product_name"] = product["name"]

    emitted_event_id = context.emit("sample.stock.observed", payload)
    return {
        "status": "OBSERVED",
        "emitted_event_id": emitted_event_id,
    }
