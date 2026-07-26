from io import BytesIO

from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import (
    AuditLog,
    InventoryReportSchedule,
    ProductBarcode,
    StockBalance,
)
from app.services.documents import DocumentService
from app.services.inventory_reports import InventoryReportService
from app.storage import LocalObjectStorage
from app.virus_scan import DisabledVirusScanner


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


def test_inventory_report_schedule_can_be_configured(client) -> None:
    headers = _headers(client)

    initial = client.get(
        "/api/v1/reports/inventory/schedule",
        headers=headers,
    )
    assert initial.status_code == 200
    assert initial.json()["enabled"] is False
    assert initial.json()["frequency"] == "WEEKLY"

    updated = client.put(
        "/api/v1/reports/inventory/schedule",
        headers=headers,
        json={
            "enabled": True,
            "frequency": "MONTHLY",
            "generation_time": "05:30:00",
            "timezone": "Europe/Bratislava",
            "weekly_day": "MONDAY",
            "monthly_rule": "LAST_DAY",
        },
    )
    assert updated.status_code == 200
    payload = updated.json()
    assert payload["enabled"] is True
    assert payload["frequency"] == "MONTHLY"
    assert payload["next_run_at"] is not None


def test_generated_inventory_pdf_is_stored_as_completed_document(
    session: Session,
    seeded,
    tmp_path,
) -> None:
    organization, user, product = seeded
    balance = session.scalar(
        select(StockBalance).where(StockBalance.product_id == product.id)
    )
    balance.quantity = 3
    session.add(
        ProductBarcode(
            organization_id=organization.id,
            product_id=product.id,
            code="5991234567890",
            is_primary=True,
        )
    )
    session.commit()

    storage = LocalObjectStorage(tmp_path / "objects")
    settings = Settings(
        _env_file=None,
        max_upload_mb=2,
        max_document_pages=10,
        object_store_backend="local",
        object_store_local_path=str(tmp_path / "objects"),
    )
    document_service = DocumentService(
        session,
        storage=storage,
        scanner=DisabledVirusScanner(),
        settings=settings,
    )
    service = InventoryReportService(
        session,
        document_service=document_service,
    )
    schedule = service.get_schedule(organization.id)
    schedule.frequency = "DAILY"
    session.commit()

    document = service.generate_now(
        user=user,
        correlation_id="inventory-report-test",
    )

    assert document.status == "COMPLETED"
    assert document.document_type == "inventory_report"
    assert document.source_type == "SYSTEM_GENERATED"
    assert document.content_type == "application/pdf"
    assert document.page_count >= 1
    assert document.validation_summary["product_count"] == 1
    assert document.validation_summary["low_stock_count"] == 1
    assert document.validation_summary["report_frequency"] == "DAILY"
    stored_path = storage.local_path(document.object_key)
    assert stored_path is not None

    reader = PdfReader(BytesIO(stored_path.read_bytes()))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "Automatikus AI készletleltár" in text
    assert "Teszt termék" in text
    assert "5991234567890" in text
    assert "MINIMUM ALATT" in text

    session.expire_all()
    saved_schedule = session.get(InventoryReportSchedule, organization.id)
    assert saved_schedule.last_document_id == document.id
    assert saved_schedule.last_run_at is not None
    assert session.scalar(
        select(AuditLog).where(
            AuditLog.action == "inventory_report.generated",
            AuditLog.entity_id == document.id,
        )
    ) is not None
