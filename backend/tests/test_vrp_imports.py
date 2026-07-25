from datetime import date, time
from decimal import Decimal
from io import BytesIO

import pytest
from sqlalchemy import select

from app.models import (
    ExternalProductMapping,
    Organization,
    Product,
    ReviewTask,
    StockBalance,
    StockMovement,
    User,
)
from app.services.vrp_imports import (
    VrpDuplicateError,
    VrpImportService,
    VrpNegativeStockError,
)
from app.storage import LocalObjectStorage
from app.virus_scan import DisabledVirusScanner


def _csv(code: str, name: str, quantity: str) -> BytesIO:
    return BytesIO(
        (
            "Kód tovaru;Označenie tovaru;Množstvo;Jednotka\n"
            f"{code};{name};{quantity};piece\n"
        ).encode()
    )


def _service(session, tmp_path) -> VrpImportService:
    return VrpImportService(
        session,
        storage=LocalObjectStorage(tmp_path / "objects"),
        scanner=DisabledVirusScanner(),
    )


def _upload(
    service: VrpImportService,
    user: User,
    *,
    quantity: str = "3",
    code: str = "TEST-001",
    name: str = "Teszt termék",
    period_start: date = date(2026, 7, 1),
    period_end: date = date(2026, 7, 1),
):
    return service.ingest(
        user=user,
        stream=_csv(code, name, quantity),
        filename="predaj.csv",
        declared_content_type="text/csv",
        period_start=period_start,
        period_end=period_end,
        external_report_id=None,
        correlation_id="test-vrp",
    ).batch


def test_import_books_once_and_reversal_nets_to_zero(
    session, seeded, tmp_path
) -> None:
    organization, user, product = seeded
    balance = session.get(StockBalance, (organization.id, product.id))
    balance.quantity = Decimal("10")
    session.commit()
    service = _service(session, tmp_path)

    batch = _upload(service, user)

    assert batch.status == "READY"
    assert batch.items[0].matched_product_id == product.id
    assert batch.items[0].conversion_factor == Decimal("1.000")
    processed = service.process(
        user=user,
        batch_id=batch.id,
        correlation_id="test-process",
        force=True,
    )
    assert processed.status == "COMPLETED"
    assert session.get(StockBalance, (organization.id, product.id)).quantity == Decimal(
        "7.000"
    )

    service.process(
        user=user,
        batch_id=batch.id,
        correlation_id="test-process-again",
        force=True,
    )
    sale_movements = list(
        session.scalars(
            select(StockMovement).where(
                StockMovement.source_type == "VRP_IMPORT_BATCH",
                StockMovement.source_id == batch.id,
            )
        )
    )
    assert len(sale_movements) == 1

    reversed_batch = service.reverse(
        user=user,
        batch_id=batch.id,
        reason="Teszt visszafordítás",
        correlation_id="test-reverse",
    )
    assert reversed_batch.status == "REVERSED"
    assert session.get(StockBalance, (organization.id, product.id)).quantity == Decimal(
        "10.000"
    )
    service.reverse(
        user=user,
        batch_id=batch.id,
        reason="Ismételt kérés",
        correlation_id="test-reverse-again",
    )
    assert session.get(StockBalance, (organization.id, product.id)).quantity == Decimal(
        "10.000"
    )


def test_duplicate_and_period_overlap_are_blocked(session, seeded, tmp_path) -> None:
    _, user, _ = seeded
    service = _service(session, tmp_path)
    first = _upload(service, user)

    with pytest.raises(VrpDuplicateError) as duplicate:
        _upload(service, user)

    assert duplicate.value.existing_batch_id == first.id
    overlap = _upload(
        service,
        user,
        quantity="4",
        period_start=date(2026, 7, 1),
        period_end=date(2026, 7, 2),
    )
    assert overlap.status == "OVERLAP"
    assert overlap.error_summary["overlap_batch_id"] == first.id
    review = session.scalar(
        select(ReviewTask).where(ReviewTask.entity_id == overlap.id)
    )
    assert review is not None
    assert review.reason_code == "PERIOD_OVERLAP"


def test_manual_mapping_persists_for_future_reports(session, seeded, tmp_path) -> None:
    _, user, product = seeded
    service = _service(session, tmp_path)
    first = _upload(
        service,
        user,
        code="VRP-ALMA",
        name="Alma külső név",
    )
    assert first.status == "NEEDS_REVIEW"

    mapped = service.update_item(
        user=user,
        batch_id=first.id,
        item_id=first.items[0].id,
        product_id=product.id,
        conversion_factor=Decimal("2"),
        correlation_id="test-map",
    )
    assert mapped.status == "READY"
    assert mapped.items[0].base_quantity == Decimal("6.000")
    assert session.scalar(select(ExternalProductMapping)) is not None

    second = _upload(
        service,
        user,
        code="VRP-ALMA",
        name="Alma új megnevezés",
        quantity="5",
        period_start=date(2026, 7, 2),
        period_end=date(2026, 7, 2),
    )
    assert second.status == "READY"
    assert second.items[0].match_method == "EXTERNAL_MAPPING"
    assert second.items[0].base_quantity == Decimal("10.000")


def test_negative_stock_stop_policy_creates_review_without_movement(
    session, seeded, tmp_path
) -> None:
    organization, user, product = seeded
    service = _service(session, tmp_path)
    service.update_schedule(
        user=user,
        frequency="MANUAL",
        processing_time=time(23, 55),
        timezone="Europe/Bratislava",
        weekly_day="SUNDAY",
        monthly_rule="LAST_DAY",
        auto_process=False,
        unknown_product_policy="STOP",
        negative_stock_policy="STOP",
        overlap_policy="BLOCK",
        correlation_id="test-policy",
    )
    batch = _upload(service, user)

    with pytest.raises(VrpNegativeStockError):
        service.process(
            user=user,
            batch_id=batch.id,
            correlation_id="test-negative",
            force=True,
        )

    refreshed = service.get_batch(organization.id, batch.id)
    assert refreshed.status == "NEEDS_REVIEW"
    assert session.get(StockBalance, (organization.id, product.id)).quantity == Decimal(
        "0.000"
    )
    assert (
        session.scalar(
            select(StockMovement.id).where(
                StockMovement.source_id == batch.id,
            )
        )
        is None
    )


def test_duplicate_detection_is_tenant_scoped(session, seeded, tmp_path) -> None:
    _, user, _ = seeded
    other_organization = Organization(name="Másik bolt", slug="masik-bolt")
    session.add(other_organization)
    session.flush()
    other_user = User(
        organization_id=other_organization.id,
        email="admin@masik.hu",
        full_name="Másik Admin",
        password_hash=user.password_hash,
        role="admin",
    )
    other_product = Product(
        organization_id=other_organization.id,
        name="Teszt termék",
        internal_sku="TEST-001",
    )
    session.add_all([other_user, other_product])
    session.commit()
    service = _service(session, tmp_path)

    first = _upload(service, user)
    second = _upload(service, other_user)

    assert first.organization_id != second.organization_id


def test_process_known_policy_books_only_matched_items(
    session, seeded, tmp_path
) -> None:
    organization, user, product = seeded
    balance = session.get(StockBalance, (organization.id, product.id))
    balance.quantity = Decimal("10")
    session.commit()
    service = _service(session, tmp_path)
    service.update_schedule(
        user=user,
        frequency="MANUAL",
        processing_time=time(23, 55),
        timezone="Europe/Bratislava",
        weekly_day="SUNDAY",
        monthly_rule="LAST_DAY",
        auto_process=False,
        unknown_product_policy="PROCESS_KNOWN",
        negative_stock_policy="STOP",
        overlap_policy="BLOCK",
        correlation_id="test-process-known-policy",
    )
    payload = BytesIO(
        (
            "Kód tovaru;Označenie tovaru;Množstvo;Jednotka\n"
            "TEST-001;Teszt termék;2;piece\n"
            "UNKNOWN-1;Ismeretlen termék;5;piece\n"
        ).encode()
    )
    batch = service.ingest(
        user=user,
        stream=payload,
        filename="process-known.csv",
        declared_content_type="text/csv",
        period_start=date(2026, 7, 1),
        period_end=date(2026, 7, 1),
        external_report_id=None,
        correlation_id="test-process-known-upload",
    ).batch

    assert batch.status == "READY"
    assert {item.status for item in batch.items} == {"READY", "SKIPPED"}
    completed = service.process(
        user=user,
        batch_id=batch.id,
        correlation_id="test-process-known",
        force=True,
    )

    assert completed.status == "COMPLETED"
    assert session.get(StockBalance, (organization.id, product.id)).quantity == Decimal(
        "8.000"
    )
    open_review = session.scalar(
        select(ReviewTask).where(
            ReviewTask.entity_id == batch.id,
            ReviewTask.status == "OPEN",
        )
    )
    assert open_review is not None


def test_process_known_policy_requires_at_least_one_known_item(
    session, seeded, tmp_path
) -> None:
    _, user, _ = seeded
    service = _service(session, tmp_path)
    service.update_schedule(
        user=user,
        frequency="MANUAL",
        processing_time=time(23, 55),
        timezone="Europe/Bratislava",
        weekly_day="SUNDAY",
        monthly_rule="LAST_DAY",
        auto_process=False,
        unknown_product_policy="PROCESS_KNOWN",
        negative_stock_policy="STOP",
        overlap_policy="BLOCK",
        correlation_id="test-all-unknown-policy",
    )

    batch = _upload(
        service,
        user,
        code="UNKNOWN-ONLY",
        name="Csak ismeretlen termék",
    )

    assert batch.status == "NEEDS_REVIEW"
    assert batch.items[0].status == "SKIPPED"


def test_manual_schedule_cannot_enable_automatic_processing(
    session, seeded, tmp_path
) -> None:
    _, user, _ = seeded
    service = _service(session, tmp_path)

    schedule = service.update_schedule(
        user=user,
        frequency="MANUAL",
        processing_time=time(23, 55),
        timezone="Europe/Bratislava",
        weekly_day="SUNDAY",
        monthly_rule="LAST_DAY",
        auto_process=True,
        unknown_product_policy="STOP",
        negative_stock_policy="STOP",
        overlap_policy="BLOCK",
        correlation_id="test-manual-auto",
    )

    assert schedule.auto_process is False
    assert schedule.next_run_at is None
