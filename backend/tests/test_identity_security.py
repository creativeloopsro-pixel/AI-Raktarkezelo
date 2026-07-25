from datetime import UTC, datetime

from sqlalchemy import delete, select

from app.models import Role, User, UserRole
from app.security import totp_code
from app.services.identity import IdentityService, effective_role_slugs


def _login(client, email: str = "admin@teszt.hu", password: str = "Secret-1234!"):
    return client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": "tesztbolt",
            "email": email,
            "password": password,
        },
    )


def _headers(payload: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {payload['access_token']}"}


def test_custom_role_user_and_permission_enforcement(client) -> None:
    login = _login(client)
    assert login.status_code == 200
    headers = _headers(login.json())

    permissions = client.get("/api/v1/identity/permissions", headers=headers)
    assert permissions.status_code == 200
    assert any(item["code"] == "products.read" for item in permissions.json())

    role = client.post(
        "/api/v1/identity/roles",
        headers=headers,
        json={
            "name": "Katalógus olvasó",
            "slug": "catalog-reader",
            "description": "Csak a terméktörzset olvashatja.",
            "permission_codes": ["products.read"],
        },
    )
    assert role.status_code == 201
    role_id = role.json()["id"]

    created = client.post(
        "/api/v1/identity/users",
        headers=headers,
        json={
            "email": "olvaso@teszt.hu",
            "full_name": "Katalógus Olvasó",
            "password": "Catalog-Reader-2026!",
            "role_ids": [role_id],
        },
    )
    assert created.status_code == 201
    assert created.json()["roles"] == ["catalog-reader"]
    assert created.json()["permissions"] == ["products.read"]

    reader_login = _login(
        client,
        email="olvaso@teszt.hu",
        password="Catalog-Reader-2026!",
    )
    assert reader_login.status_code == 200
    reader_headers = _headers(reader_login.json())
    assert client.get("/api/v1/products", headers=reader_headers).status_code == 200
    denied = client.post(
        "/api/v1/products",
        headers=reader_headers,
        json={
            "name": "Tiltott termék",
            "internal_sku": "DENIED-001",
            "base_unit": "piece",
            "min_stock": 0,
        },
    )
    assert denied.status_code == 403
    assert denied.json()["detail"]["required_permissions"] == ["products.write"]


def test_scoped_api_token_can_be_revoked(client) -> None:
    login = _login(client)
    headers = _headers(login.json())
    created = client.post(
        "/api/v1/identity/tokens",
        headers=headers,
        json={
            "name": "Termék olvasó integráció",
            "scopes": ["products.read"],
            "expires_at": None,
        },
    )
    assert created.status_code == 201
    payload = created.json()
    raw_token = payload["raw_token"]
    assert raw_token.startswith("airk_")
    api_headers = {"Authorization": f"Bearer {raw_token}"}

    assert client.get("/api/v1/products", headers=api_headers).status_code == 200
    denied = client.post(
        "/api/v1/products",
        headers=api_headers,
        json={
            "name": "Tokennel tiltott",
            "internal_sku": "TOKEN-DENIED",
            "base_unit": "piece",
            "min_stock": 0,
        },
    )
    assert denied.status_code == 403
    assert denied.json()["detail"]["code"] == "api_token_scope_denied"
    interactive_denied = client.post(
        "/api/v1/auth/mfa/setup",
        headers=api_headers,
    )
    assert interactive_denied.status_code == 403
    assert (
        interactive_denied.json()["detail"]["code"]
        == "interactive_session_required"
    )

    revoked = client.delete(
        f"/api/v1/identity/tokens/{payload['token']['id']}",
        headers=headers,
    )
    assert revoked.status_code == 200
    assert revoked.json()["revoked_at"] is not None
    assert client.get("/api/v1/products", headers=api_headers).status_code == 401


def test_mfa_setup_recovery_login_and_replay_protection(client) -> None:
    login = _login(client)
    headers = _headers(login.json())
    setup = client.post("/api/v1/auth/mfa/setup", headers=headers)
    assert setup.status_code == 200
    secret = setup.json()["secret"]
    counter = int(datetime.now(UTC).timestamp()) // 30
    confirmation = client.post(
        "/api/v1/auth/mfa/confirm",
        headers=headers,
        json={"code": totp_code(secret, counter)},
    )
    assert confirmation.status_code == 200
    confirmation_payload = confirmation.json()
    assert len(confirmation_payload["recovery_codes"]) == 8
    assert confirmation_payload["session"]["user"]["mfa_enabled"] is True

    challenged = _login(client)
    assert challenged.status_code == 200
    assert challenged.json()["mfa_required"] is True
    recovery_code = confirmation_payload["recovery_codes"][0]
    verified = client.post(
        "/api/v1/auth/mfa/verify",
        json={
            "challenge_token": challenged.json()["challenge_token"],
            "code": recovery_code,
        },
    )
    assert verified.status_code == 200
    assert verified.json()["user"]["mfa_enabled"] is True

    second_challenge = _login(client)
    replay = client.post(
        "/api/v1/auth/mfa/verify",
        json={
            "challenge_token": second_challenge.json()["challenge_token"],
            "code": recovery_code,
        },
    )
    assert replay.status_code == 401
    assert replay.json()["detail"]["code"] == "invalid_mfa_code"


def test_refresh_rotation_detects_reuse_and_revokes_family(client) -> None:
    login = _login(client).json()
    rotated = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": login["refresh_token"]},
    )
    assert rotated.status_code == 200
    reused = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": login["refresh_token"]},
    )
    assert reused.status_code == 401
    assert reused.json()["detail"]["code"] == "refresh_token_reuse"
    family_token = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": rotated.json()["refresh_token"]},
    )
    assert family_token.status_code == 401
    invalidated_access = client.get(
        "/api/v1/products",
        headers=_headers(rotated.json()),
    )
    assert invalidated_access.status_code == 401


def test_manual_session_revocation_invalidates_access_immediately(client) -> None:
    login = _login(client).json()
    headers = _headers(login)
    sessions = client.get("/api/v1/auth/sessions", headers=headers)
    current = next(item for item in sessions.json() if item["current"])
    revoked = client.delete(
        f"/api/v1/auth/sessions/{current['id']}",
        headers=headers,
    )
    assert revoked.status_code == 204
    assert client.get("/api/v1/products", headers=headers).status_code == 401


def test_legacy_plugin_service_is_restricted_to_service_role(
    session,
    seeded,
) -> None:
    organization, _, _ = seeded
    service_user = User(
        organization_id=organization.id,
        email="plugin+legacy@service.invalid",
        full_name="Legacy plugin",
        password_hash="not-used",
        role="plugin_service",
        is_active=False,
    )
    session.add(service_user)
    session.flush()
    identity = IdentityService(session)
    identity.ensure_organization(organization.id)
    session.flush()
    assert effective_role_slugs(session, service_user) == {"service"}

    warehouse_role = session.scalar(
        select(Role).where(
            Role.organization_id == organization.id,
            Role.slug == "warehouse",
        )
    )
    session.execute(
        delete(UserRole).where(UserRole.user_id == service_user.id)
    )
    session.add(
        UserRole(
            organization_id=organization.id,
            user_id=service_user.id,
            role_id=warehouse_role.id,
        )
    )
    session.flush()
    identity.ensure_organization(organization.id)
    session.flush()
    assert effective_role_slugs(session, service_user) == {"service"}
