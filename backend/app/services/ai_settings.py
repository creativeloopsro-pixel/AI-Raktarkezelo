from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from pydantic import SecretStr
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models import (
    AuditLog,
    OrganizationAiSettings,
    OutboxEvent,
    User,
)
from app.security import decrypt_secret, encrypt_secret


@dataclass(frozen=True)
class AiSettingsSnapshot:
    organization_id: str
    provider: str
    base_url: str
    model: str
    api_key_configured: bool
    api_key_source: str
    api_key_hint: str | None
    provider_enabled: bool
    updated_by: str | None
    updated_at: datetime | None


class AiSettingsService:
    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
    ):
        self.session = session
        self.settings = settings or get_settings()

    def snapshot(self, organization_id: str) -> AiSettingsSnapshot:
        configured = self.session.get(OrganizationAiSettings, organization_id)
        environment_key = self.settings.ollama_api_key.get_secret_value()
        organization_configured = bool(
            configured and configured.api_key_encrypted
        )
        environment_configured = bool(environment_key)

        if configured is not None and configured.api_key_encrypted:
            source = "organization"
            hint = f"••••{configured.api_key_last_four}"
        elif environment_configured:
            source = "environment"
            hint = None
        else:
            source = "none"
            hint = None

        return AiSettingsSnapshot(
            organization_id=organization_id,
            provider="ollama",
            base_url=self.settings.ollama_base_url,
            model=self.settings.ollama_model,
            api_key_configured=organization_configured or environment_configured,
            api_key_source=source,
            api_key_hint=hint,
            provider_enabled=organization_configured
            or self.settings.ai_provider.casefold() == "ollama",
            updated_by=configured.updated_by if configured else None,
            updated_at=configured.updated_at if configured else None,
        )

    def update_api_key(
        self,
        *,
        user: User,
        api_key: str,
        correlation_id: str,
    ) -> AiSettingsSnapshot:
        configured = self.session.get(OrganizationAiSettings, user.organization_id)
        if configured is None:
            configured = OrganizationAiSettings(
                organization_id=user.organization_id
            )
            self.session.add(configured)

        configured.provider = "ollama"
        configured.api_key_encrypted = encrypt_secret(api_key, self.settings)
        configured.api_key_last_four = api_key[-4:]
        configured.updated_by = user.id
        self.session.add(
            AuditLog(
                organization_id=user.organization_id,
                actor_id=user.id,
                action="ai.api_key_updated",
                entity_type="organization_ai_settings",
                entity_id=user.organization_id,
                correlation_id=correlation_id,
                details={"provider": "ollama", "configured": True},
            )
        )
        self.session.add(
            OutboxEvent(
                organization_id=user.organization_id,
                event_type="ai.settings.updated",
                aggregate_type="organization_ai_settings",
                aggregate_id=user.organization_id,
                payload={"correlation_id": correlation_id, "provider": "ollama"},
            )
        )
        self.session.commit()
        return self.snapshot(user.organization_id)

    def clear_api_key(
        self,
        *,
        user: User,
        correlation_id: str,
    ) -> AiSettingsSnapshot:
        configured = self.session.get(OrganizationAiSettings, user.organization_id)
        if configured is not None:
            configured.api_key_encrypted = None
            configured.api_key_last_four = None
            configured.updated_by = user.id

        self.session.add(
            AuditLog(
                organization_id=user.organization_id,
                actor_id=user.id,
                action="ai.api_key_cleared",
                entity_type="organization_ai_settings",
                entity_id=user.organization_id,
                correlation_id=correlation_id,
                details={"provider": "ollama", "configured": False},
            )
        )
        self.session.add(
            OutboxEvent(
                organization_id=user.organization_id,
                event_type="ai.settings.updated",
                aggregate_type="organization_ai_settings",
                aggregate_id=user.organization_id,
                payload={"correlation_id": correlation_id, "provider": "ollama"},
            )
        )
        self.session.commit()
        return self.snapshot(user.organization_id)

    def runtime_settings(self, organization_id: str) -> Settings:
        configured = self.session.get(OrganizationAiSettings, organization_id)
        if configured is None or not configured.api_key_encrypted:
            return self.settings
        api_key = decrypt_secret(configured.api_key_encrypted, self.settings)
        return self.settings.model_copy(
            update={
                "ai_provider": "ollama",
                "ollama_api_key": SecretStr(api_key),
            }
        )
