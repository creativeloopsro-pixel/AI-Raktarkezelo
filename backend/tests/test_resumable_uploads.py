from hashlib import sha256
from io import BytesIO

from PIL import Image

from app.storage import LocalObjectStorage


def _headers(client) -> dict[str, str]:
    login = client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": "tesztbolt",
            "email": "admin@teszt.hu",
            "password": "Secret-1234!",
        },
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _png() -> bytes:
    stream = BytesIO()
    Image.new("RGB", (32, 32), "white").save(stream, format="PNG")
    return stream.getvalue()


def _create_upload(
    client,
    headers: dict[str, str],
    *,
    client_upload_id: str,
    target_type: str,
    filename: str,
    content_type: str,
    payload: bytes,
    metadata: dict,
) -> dict:
    response = client.post(
        "/api/v1/uploads",
        headers=headers,
        json={
            "client_upload_id": client_upload_id,
            "target_type": target_type,
            "filename": filename,
            "declared_content_type": content_type,
            "total_size": len(payload),
            "file_sha256": sha256(payload).hexdigest(),
            "metadata": metadata,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_resumable_document_upload_is_idempotent_and_cancellable(
    client,
    monkeypatch,
    tmp_path,
) -> None:
    storage = LocalObjectStorage(tmp_path / "resumable-objects")
    monkeypatch.setattr(
        "app.services.resumable_uploads.get_object_storage",
        lambda: storage,
    )
    headers = _headers(client)
    payload = _png()
    upload = _create_upload(
        client,
        headers,
        client_upload_id="document-upload-0001",
        target_type="DOCUMENT",
        filename="szamla.png",
        content_type="image/png",
        payload=payload,
        metadata={"document_type": "goods_receipt"},
    )
    assert upload["total_chunks"] == 1
    chunk_headers = {
        **headers,
        "Content-Type": "application/octet-stream",
        "X-Chunk-SHA256": sha256(payload).hexdigest(),
    }
    first = client.put(
        f"/api/v1/uploads/{upload['id']}/chunks/0",
        headers=chunk_headers,
        content=payload,
    )
    assert first.status_code == 200
    assert first.json()["received_chunks"] == [0]
    repeated = client.put(
        f"/api/v1/uploads/{upload['id']}/chunks/0",
        headers=chunk_headers,
        content=payload,
    )
    assert repeated.status_code == 200
    assert repeated.json()["received_chunks"] == [0]

    completed = client.post(
        f"/api/v1/uploads/{upload['id']}/complete",
        headers=headers,
        json={"file_sha256": sha256(payload).hexdigest()},
    )
    assert completed.status_code == 200
    assert completed.json()["entity_type"] == "document"
    assert completed.json()["upload"]["status"] == "COMPLETED"
    document_id = completed.json()["entity_id"]
    assert client.get(
        f"/api/v1/documents/{document_id}",
        headers=headers,
    ).status_code == 200

    pending = _create_upload(
        client,
        headers,
        client_upload_id="document-upload-cancel",
        target_type="DOCUMENT",
        filename="megszakit.png",
        content_type="image/png",
        payload=payload,
        metadata={"document_type": "goods_receipt"},
    )
    cancelled = client.delete(
        f"/api/v1/uploads/{pending['id']}",
        headers=headers,
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"

    vrp_payload = (
        "Kód tovaru;Označenie tovaru;Množstvo;Jednotka\n"
        "TEST-001;Teszt termék;1;piece\n"
    ).encode()
    _create_upload(
        client,
        headers,
        client_upload_id="vrp-filtered-from-documents",
        target_type="VRP",
        filename="filtered.csv",
        content_type="text/csv",
        payload=vrp_payload,
        metadata={
            "period_start": "2026-07-02",
            "period_end": "2026-07-02",
        },
    )
    document_uploads = client.get(
        "/api/v1/uploads",
        params={"target_type": "DOCUMENT"},
        headers=headers,
    )
    assert document_uploads.status_code == 200
    assert {
        item["target_type"] for item in document_uploads.json()
    } == {"DOCUMENT"}

    roles = client.get("/api/v1/identity/roles", headers=headers).json()
    warehouse_role = next(role for role in roles if role["slug"] == "warehouse")
    created_user = client.post(
        "/api/v1/identity/users",
        headers=headers,
        json={
            "email": "feltolto@teszt.hu",
            "full_name": "Másik feltöltő",
            "password": "Uploader-1234!",
            "role_ids": [warehouse_role["id"]],
        },
    )
    assert created_user.status_code == 201
    other_login = client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": "tesztbolt",
            "email": "feltolto@teszt.hu",
            "password": "Uploader-1234!",
        },
    )
    other_headers = {
        "Authorization": f"Bearer {other_login.json()['access_token']}"
    }
    hidden = client.get(
        f"/api/v1/uploads/{pending['id']}",
        headers=other_headers,
    )
    assert hidden.status_code == 404


def test_resumable_vrp_upload_completes_existing_import_pipeline(
    client,
    monkeypatch,
    tmp_path,
) -> None:
    storage = LocalObjectStorage(tmp_path / "resumable-vrp-objects")
    monkeypatch.setattr(
        "app.services.resumable_uploads.get_object_storage",
        lambda: storage,
    )
    headers = _headers(client)
    payload = (
        "Kód tovaru;Označenie tovaru;Množstvo;Jednotka\n"
        "TEST-001;Teszt termék;2;piece\n"
    ).encode()
    upload = _create_upload(
        client,
        headers,
        client_upload_id="vrp-upload-0001",
        target_type="VRP",
        filename="predaj.csv",
        content_type="text/csv",
        payload=payload,
        metadata={
            "period_start": "2026-07-01",
            "period_end": "2026-07-01",
            "external_report_id": "VRP-OFFLINE-1",
        },
    )
    chunk = client.put(
        f"/api/v1/uploads/{upload['id']}/chunks/0",
        headers={
            **headers,
            "Content-Type": "application/octet-stream",
            "X-Chunk-SHA256": sha256(payload).hexdigest(),
        },
        content=payload,
    )
    assert chunk.status_code == 200
    completed = client.post(
        f"/api/v1/uploads/{upload['id']}/complete",
        headers=headers,
        json={"file_sha256": sha256(payload).hexdigest()},
    )
    assert completed.status_code == 200
    assert completed.json()["entity_type"] == "vrp_import_batch"
    batch = client.get(
        f"/api/v1/vrp/imports/{completed.json()['entity_id']}",
        headers=headers,
    )
    assert batch.status_code == 200
    assert batch.json()["external_report_id"] == "VRP-OFFLINE-1"
