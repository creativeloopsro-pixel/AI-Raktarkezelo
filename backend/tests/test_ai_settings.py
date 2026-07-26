from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.gateway import get_ai_provider
from app.config import get_settings
from app.models import AuditLog, OrganizationAiSettings, OutboxEvent
from app.security import decrypt_secret
from app.services.ai_settings import AiSettingsService


def _headers(client) -> dict[str, str]:
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


def test_ai_api_key_is_encrypted_masked_and_used_at_runtime(
    client,
    session: Session,
    seeded,
) -> None:
    organization, user, _ = seeded
    headers = _headers(client)
    raw_key = "ollama-test-secret-9876"

    initial = client.get("/api/v1/ai/settings", headers=headers)
    assert initial.status_code == 200
    assert initial.json()["api_key_source"] == "none"
    assert initial.json()["api_key_configured"] is False

    updated = client.put(
        "/api/v1/ai/settings",
        headers=headers,
        json={"api_key": raw_key},
    )
    assert updated.status_code == 200
    payload = updated.json()
    assert payload["provider"] == "ollama"
    assert payload["provider_enabled"] is True
    assert payload["api_key_configured"] is True
    assert payload["api_key_source"] == "organization"
    assert payload["api_key_hint"] == "••••9876"
    assert raw_key not in updated.text

    session.expire_all()
    configured = session.get(OrganizationAiSettings, organization.id)
    assert configured is not None
    assert configured.api_key_encrypted
    assert raw_key not in configured.api_key_encrypted
    assert (
        decrypt_secret(configured.api_key_encrypted, get_settings())
        == raw_key
    )

    runtime = AiSettingsService(session).runtime_settings(organization.id)
    assert runtime.ai_provider == "ollama"
    assert runtime.ollama_api_key.get_secret_value() == raw_key
    assert get_ai_provider(runtime).name == "ollama"

    audit = session.scalar(
        select(AuditLog).where(
            AuditLog.organization_id == organization.id,
            AuditLog.action == "ai.api_key_updated",
        )
    )
    assert audit is not None
    assert raw_key not in str(audit.details)
    event = session.scalar(
        select(OutboxEvent).where(
            OutboxEvent.organization_id == organization.id,
            OutboxEvent.event_type == "ai.settings.updated",
        )
    )
    assert event is not None
    assert raw_key not in str(event.payload)
    assert configured.updated_by == user.id

    reread = client.get("/api/v1/ai/settings", headers=headers)
    assert reread.status_code == 200
    assert reread.json()["api_key_hint"] == "••••9876"
    assert raw_key not in reread.text

    cleared = client.delete("/api/v1/ai/settings", headers=headers)
    assert cleared.status_code == 200
    assert cleared.json()["api_key_source"] == "none"
    assert cleared.json()["api_key_configured"] is False
    session.expire_all()
    configured = session.get(OrganizationAiSettings, organization.id)
    assert configured is not None
    assert configured.api_key_encrypted is None
    assert configured.api_key_last_four is None


def test_ai_api_key_rejects_whitespace(client) -> None:
    response = client.put(
        "/api/v1/ai/settings",
        headers=_headers(client),
        json={"api_key": "invalid key with spaces"},
    )
    assert response.status_code == 422
