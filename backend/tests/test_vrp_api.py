from decimal import Decimal

from app.models import StockBalance
from app.storage import LocalObjectStorage
from app.virus_scan import DisabledVirusScanner


def test_vrp_upload_process_schedule_and_reverse_api(
    client, monkeypatch, tmp_path, session, seeded
) -> None:
    organization, _, product = seeded
    balance = session.get(StockBalance, (organization.id, product.id))
    balance.quantity = Decimal("10")
    session.commit()
    storage = LocalObjectStorage(tmp_path / "api-vrp-objects")
    monkeypatch.setattr(
        "app.services.vrp_imports.get_object_storage",
        lambda: storage,
    )
    monkeypatch.setattr(
        "app.services.vrp_imports.get_virus_scanner",
        lambda: DisabledVirusScanner(),
    )
    login = client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": "tesztbolt",
            "email": "admin@teszt.hu",
            "password": "Secret-1234!",
        },
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    schedule = client.get("/api/v1/vrp/schedule", headers=headers)
    assert schedule.status_code == 200
    assert schedule.json()["frequency"] == "DAILY"
    update_schedule = client.put(
        "/api/v1/vrp/schedule",
        headers=headers,
        json={
            "frequency": "WEEKLY",
            "processing_time": "23:55",
            "timezone": "Europe/Bratislava",
            "weekly_day": "SUNDAY",
            "monthly_rule": "LAST_DAY",
            "auto_process": False,
            "unknown_product_policy": "STOP",
            "negative_stock_policy": "STOP",
            "overlap_policy": "BLOCK",
        },
    )
    assert update_schedule.status_code == 200
    assert update_schedule.json()["frequency"] == "WEEKLY"

    csv_payload = (
        "Kód tovaru;Označenie tovaru;Množstvo;Jednotka\n"
        "TEST-001;Teszt termék;3;piece\n"
    ).encode()
    upload = client.post(
        "/api/v1/vrp/imports",
        headers=headers,
        files={"file": ("predaj.csv", csv_payload, "text/csv")},
        data={
            "period_start": "2026-07-01",
            "period_end": "2026-07-01",
            "external_report_id": "VRP-API-1",
        },
    )
    assert upload.status_code == 201
    assert upload.json()["status"] == "READY"
    batch_id = upload.json()["id"]

    duplicate = client.post(
        "/api/v1/vrp/imports",
        headers=headers,
        files={"file": ("predaj-copy.csv", csv_payload, "text/csv")},
        data={
            "period_start": "2026-07-02",
            "period_end": "2026-07-02",
        },
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["existing_batch_id"] == batch_id

    process = client.post(
        f"/api/v1/vrp/imports/{batch_id}/process",
        headers=headers,
    )
    assert process.status_code == 200
    assert process.json()["status"] == "COMPLETED"

    reverse = client.post(
        f"/api/v1/vrp/imports/{batch_id}/reverse",
        headers=headers,
        json={"reason": "API integrációs teszt"},
    )
    assert reverse.status_code == 200
    assert reverse.json()["status"] == "REVERSED"

    imports = client.get("/api/v1/vrp/imports", headers=headers)
    assert imports.status_code == 200
    assert [item["id"] for item in imports.json()] == [batch_id]
