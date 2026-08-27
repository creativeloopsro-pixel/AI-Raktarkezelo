import json
from hashlib import sha256
from zipfile import ZipFile

from sqlalchemy import select

from app.models import (
    BackupSchedule,
    Document,
    OrganizationAiSettings,
    Product,
    User,
)
from app.security import hash_password
from app.storage import LocalObjectStorage


def _login(client) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": "tesztbolt",
            "email": "admin@teszt.hu",
            "password": "Secret-1234!",
        },
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_backup_schedule_generate_overwrite_and_download(
    client,
    session,
    seeded,
    tmp_path,
    monkeypatch,
) -> None:
    storage = LocalObjectStorage(tmp_path / "objects")
    monkeypatch.setattr(
        "app.services.backups.get_object_storage",
        lambda: storage,
    )
    headers = _login(client)
    organization, user, _ = seeded
    document_bytes = b"%PDF-1.4 backup test"
    source_path = tmp_path / "delivery-note.pdf"
    source_path.write_bytes(document_bytes)
    object_key = f"documents/{organization.id}/delivery-note.pdf"
    storage.put_file(source_path, object_key, "application/pdf")
    document = Document(
        organization_id=organization.id,
        original_filename="szallitolevel.pdf",
        content_type="application/pdf",
        size_bytes=len(document_bytes),
        sha256_hash=sha256(document_bytes).hexdigest(),
        object_key=object_key,
        status="COMPLETED",
        uploaded_by=user.id,
    )
    session.add(document)
    session.commit()

    initial = client.get("/api/v1/backups/schedule", headers=headers)
    assert initial.status_code == 200
    assert initial.json()["backup_available"] is False

    updated = client.put(
        "/api/v1/backups/schedule",
        headers=headers,
        json={
            "enabled": True,
            "frequency": "DAILY",
            "backup_time": "02:30:00",
            "timezone": "Europe/Bratislava",
            "weekly_day": "SUNDAY",
            "monthly_rule": "LAST_DAY",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["enabled"] is True
    assert updated.json()["next_run_at"] is not None

    generated = client.post("/api/v1/backups/generate", headers=headers)
    assert generated.status_code == 201
    payload = generated.json()
    assert payload["last_status"] == "COMPLETED"
    assert payload["backup_available"] is True
    assert payload["last_size_bytes"] > 0
    assert len(payload["last_sha256"]) == 64

    backup_path = tmp_path / "objects" / "backups" / organization.id / "latest.zip"
    assert backup_path.exists()
    assert len(list(backup_path.parent.glob("*.zip"))) == 1

    with ZipFile(backup_path) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        users = json.loads(archive.read("data/users.json"))
        assert manifest["organization"]["id"] == organization.id
        assert manifest["table_counts"]["products"] == 1
        assert len(manifest["included_files"]) == 1
        assert archive.read(
            f"files/documents/{document.id}/szallitolevel.pdf"
        ) == document_bytes
        assert "password_hash" not in users[0]
        assert "user_mfa_methods" in manifest["security"]["excluded_tables"]

    session.add(
        Product(
            organization_id=organization.id,
            name="MĂˇsodik termĂ©k",
            internal_sku="TEST-002",
        )
    )
    session.commit()

    regenerated = client.post("/api/v1/backups/generate", headers=headers)
    assert regenerated.status_code == 201
    assert len(list(backup_path.parent.glob("*.zip"))) == 1
    with ZipFile(backup_path) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["table_counts"]["products"] == 2

    download = client.get("/api/v1/backups/download", headers=headers)
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/zip"
    assert download.content.startswith(b"PK")


def test_backup_download_requires_existing_backup(client) -> None:
    headers = _login(client)
    response = client.get("/api/v1/backups/download", headers=headers)
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "backup_not_available"


def test_backup_schedule_is_stored_per_organization(session, seeded) -> None:
    organization, _, _ = seeded
    schedule = BackupSchedule(
        organization_id=organization.id,
        enabled=True,
        frequency="MONTHLY",
    )
    session.add(schedule)
    session.commit()
    assert session.get(BackupSchedule, organization.id).frequency == "MONTHLY"


def test_backup_restore_replaces_business_data_and_preserves_credentials(
    client,
    session,
    seeded,
    tmp_path,
    monkeypatch,
) -> None:
    storage = LocalObjectStorage(tmp_path / "restore-objects")
    monkeypatch.setattr(
        "app.services.backups.get_object_storage",
        lambda: storage,
    )
    monkeypatch.setattr(
        "app.services.backup_restore.get_object_storage",
        lambda: storage,
    )
    headers = _login(client)
    organization, user, product = seeded

    source_bytes = b"%PDF-1.4 restorable delivery note"
    source_path = tmp_path / "restorable.pdf"
    source_path.write_bytes(source_bytes)
    source_object_key = f"documents/{organization.id}/restorable.pdf"
    storage.put_file(source_path, source_object_key, "application/pdf")
    source_document = Document(
        organization_id=organization.id,
        original_filename="visszaallithato.pdf",
        content_type="application/pdf",
        size_bytes=len(source_bytes),
        sha256_hash=sha256(source_bytes).hexdigest(),
        object_key=source_object_key,
        status="COMPLETED",
        uploaded_by=user.id,
    )
    session.add(source_document)
    session.commit()

    original_backup = client.post("/api/v1/backups/generate", headers=headers)
    assert original_backup.status_code == 201
    downloaded = client.get("/api/v1/backups/download", headers=headers)
    assert downloaded.status_code == 200
    restore_bytes = downloaded.content

    replacement_password_hash = hash_password("Replacement-Secret-2026!")
    user.password_hash = replacement_password_hash
    current_ai_secret = "encrypted-current-ai-key"
    session.add(
        OrganizationAiSettings(
            organization_id=organization.id,
            api_key_encrypted=current_ai_secret,
            api_key_last_four="new!",
            updated_by=user.id,
        )
    )
    product.name = "Visszaállítás előtt módosított termék"
    extra_product = Product(
        organization_id=organization.id,
        name="Mentés után létrehozott termék",
        internal_sku="AFTER-BACKUP",
    )
    session.add(extra_product)
    session.commit()

    restored = client.post(
        "/api/v1/backups/restore",
        headers=headers,
        data={"confirmation": "RESTORE"},
        files={
            "file": (
                "ai-raktar-biztonsagi-mentes.zip",
                restore_bytes,
                "application/zip",
            )
        },
    )
    assert restored.status_code == 200
    restored_payload = restored.json()
    assert restored_payload["restored_rows"] > 0
    assert restored_payload["restored_files"] == 1
    assert "felhasználók és jelszavak" in restored_payload["preserved_security_data"]
    assert "AI API-kulcsok" in restored_payload["preserved_security_data"]

    session.expire_all()
    products = list(
        session.scalars(
            select(Product).where(Product.organization_id == organization.id)
        )
    )
    assert [item.internal_sku for item in products] == ["TEST-001"]
    assert products[0].name == "Teszt termék"
    restored_user = session.get(User, user.id)
    assert restored_user is not None
    assert restored_user.password_hash == replacement_password_hash
    ai_settings = session.get(OrganizationAiSettings, organization.id)
    assert ai_settings is not None
    assert ai_settings.api_key_encrypted == current_ai_secret

    restored_document = session.scalar(
        select(Document).where(
            Document.organization_id == organization.id,
            Document.id == source_document.id,
        )
    )
    assert restored_document is not None
    restored_stream = storage.open_stream(restored_document.object_key)
    assert restored_stream is not None
    with restored_stream:
        assert restored_stream.read() == source_bytes

    safety_download = client.get("/api/v1/backups/download", headers=headers)
    assert safety_download.status_code == 200
    safety_path = tmp_path / "safety.zip"
    safety_path.write_bytes(safety_download.content)
    with ZipFile(safety_path) as archive:
        safety_manifest = json.loads(archive.read("manifest.json"))
        assert safety_manifest["table_counts"]["products"] == 2


def test_backup_restore_rejects_missing_confirmation_and_api_token(
    client,
    tmp_path,
    monkeypatch,
) -> None:
    storage = LocalObjectStorage(tmp_path / "restore-auth-objects")
    monkeypatch.setattr(
        "app.services.backups.get_object_storage",
        lambda: storage,
    )
    monkeypatch.setattr(
        "app.services.backup_restore.get_object_storage",
        lambda: storage,
    )
    headers = _login(client)
    assert client.post("/api/v1/backups/generate", headers=headers).status_code == 201
    archive = client.get("/api/v1/backups/download", headers=headers).content

    missing_confirmation = client.post(
        "/api/v1/backups/restore",
        headers=headers,
        data={"confirmation": "NO"},
        files={"file": ("backup.zip", archive, "application/zip")},
    )
    assert missing_confirmation.status_code == 422
    assert (
        missing_confirmation.json()["detail"]["code"]
        == "backup_restore_confirmation_required"
    )

    token = client.post(
        "/api/v1/identity/tokens",
        headers=headers,
        json={
            "name": "Mentési token",
            "scopes": ["backups.restore"],
            "expires_at": None,
        },
    )
    assert token.status_code == 201
    token_headers = {"Authorization": f"Bearer {token.json()['raw_token']}"}
    denied = client.post(
        "/api/v1/backups/restore",
        headers=token_headers,
        data={"confirmation": "RESTORE"},
        files={"file": ("backup.zip", archive, "application/zip")},
    )
    assert denied.status_code == 403
    assert denied.json()["detail"]["code"] == "interactive_session_required"
