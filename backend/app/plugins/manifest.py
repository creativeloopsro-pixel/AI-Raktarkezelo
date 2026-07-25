from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

PLUGIN_ID_PATTERN = r"^[a-z][a-z0-9-]{2,79}$"
SEMVER_PATTERN = r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?$"
EVENT_PATTERN = r"^[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+$"

ALLOWED_PLUGIN_PERMISSIONS = frozenset(
    {
        "products.read",
        "products.mapping.write",
        "documents.read",
        "documents.process",
        "stock.movements.create",
        "reports.generate",
        "notifications.create",
        "settings.read",
        "settings.write",
    }
)


class PluginManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=PLUGIN_ID_PATTERN, max_length=80)
    name: str = Field(min_length=2, max_length=160)
    description: str = Field(default="", max_length=500)
    version: str = Field(pattern=SEMVER_PATTERN, max_length=40)
    api_version: str = Field(default="1", pattern=r"^[1-9]\d*$", max_length=20)
    entrypoint: str = Field(default="", max_length=200)
    permissions: list[str] = Field(default_factory=list, max_length=50)
    subscribes: list[str] = Field(default_factory=list, max_length=100)
    emits: list[str] = Field(default_factory=list, max_length=100)
    settings_schema: dict[str, Any] = Field(default_factory=dict)

    @field_validator("permissions")
    @classmethod
    def validate_permissions(cls, values: list[str]) -> list[str]:
        unique = list(dict.fromkeys(values))
        unknown = sorted(set(unique) - ALLOWED_PLUGIN_PERMISSIONS)
        if unknown:
            raise ValueError(f"Ismeretlen plugin jogosultság: {', '.join(unknown)}")
        return unique

    @field_validator("subscribes", "emits")
    @classmethod
    def validate_events(cls, values: list[str]) -> list[str]:
        unique = list(dict.fromkeys(values))
        import re

        invalid = [value for value in unique if not re.fullmatch(EVENT_PATTERN, value)]
        if invalid:
            raise ValueError(f"Érvénytelen eseménynév: {', '.join(invalid)}")
        return unique


AI_GOODS_RECEIPT_MANIFEST = PluginManifest(
    id="ai-goods-receipt",
    name="AI Goods Receipt",
    description="A bizonylatmellékleteket a tartós Ollama-feldolgozási sorba irányítja.",
    version="1.0.0",
    api_version="1",
    entrypoint="app.plugins.builtin:handle_ai_document_uploaded",
    permissions=["documents.read", "documents.process", "settings.read"],
    subscribes=["document.uploaded"],
    emits=["document.processing.requested"],
    settings_schema={
        "type": "object",
        "properties": {
            "auto_process_email": {"type": "boolean", "default": True},
        },
        "additionalProperties": False,
    },
)

VRP_IMPORT_MANIFEST = PluginManifest(
    id="vrp-import",
    name="VRP Import",
    description="VRP2 riportok párosítása, ütemezése és készletkönyvelése.",
    version="1.0.0",
    api_version="1",
    entrypoint="app.plugins.builtin:handle_vrp_schedule_triggered",
    permissions=[
        "documents.read",
        "products.read",
        "products.mapping.write",
        "stock.movements.create",
        "settings.read",
        "settings.write",
    ],
    subscribes=["schedule.triggered"],
    emits=["vrp.import.completed", "stock.changed"],
)

EMAIL_INTAKE_MANIFEST = PluginManifest(
    id="email-intake",
    name="E-mail Document Intake",
    description="Aláírt webhook és IMAP csatorna dokumentummellékletekhez.",
    version="1.0.0",
    api_version="1",
    entrypoint="app.services.email_intake:EmailIntakeService",
    permissions=["documents.read", "documents.process", "settings.read", "settings.write"],
    subscribes=[],
    emits=["document.uploaded"],
)

SAMPLE_STOCK_AUDIT_MANIFEST = PluginManifest(
    id="sample-stock-audit",
    name="Minta készletfigyelő",
    description="SDK-minta: a stock.changed eseményt csak olvasási joggal összegzi.",
    version="1.0.0",
    api_version="1",
    entrypoint="app.plugins.builtin:handle_sample_stock_changed",
    permissions=["products.read", "settings.read"],
    subscribes=["stock.changed"],
    emits=["sample.stock.observed"],
    settings_schema={
        "type": "object",
        "properties": {
            "include_product_name": {"type": "boolean", "default": True},
        },
        "additionalProperties": False,
    },
)

BUILTIN_PLUGIN_MANIFESTS = (
    AI_GOODS_RECEIPT_MANIFEST,
    VRP_IMPORT_MANIFEST,
    EMAIL_INTAKE_MANIFEST,
    SAMPLE_STOCK_AUDIT_MANIFEST,
)

DEFAULT_ENABLED_BUILTINS = frozenset(
    {"ai-goods-receipt", "vrp-import", "email-intake"}
)
