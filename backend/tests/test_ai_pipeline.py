import json
from datetime import timedelta
from io import BytesIO

from pypdf import PdfWriter
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.gateway import (
    AiProviderResponse,
    AiProviderUnavailableError,
)
from app.ai.preprocessing import DocumentImagePreprocessor
from app.config import Settings
from app.models import (
    AiRequest,
    AiToolCall,
    AuditLog,
    GoodsReceiptDraft,
    PackagingUnit,
    ProductBarcode,
    ReviewTask,
    StockBalance,
    StockMovement,
    utc_now,
)
from app.services.ai_processing import DocumentAiPipeline
from app.services.documents import DocumentService
from app.services.goods_receipts import GoodsReceiptService
from app.storage import LocalObjectStorage
from app.virus_scan import DisabledVirusScanner


def pdf_bytes() -> bytes:
    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    writer.write(output)
    return output.getvalue()


class FakeProvider:
    name = "fake"
    model = "gemma4:31b-test"

    def __init__(self, content: dict):
        self.content = content

    def extract(self, images: list[str]) -> AiProviderResponse:
        assert images and all(isinstance(image, str) for image in images)
        return AiProviderResponse(
            content=json.dumps(self.content),
            model=self.model,
            model_version="test-model-sha",
            duration_ms=42,
            prompt_tokens=120,
            completion_tokens=35,
            provider_metadata={"done_reason": "stop"},
        )


class UnavailableProvider:
    name = "unavailable"
    model = "unavailable-model"

    def __init__(self):
        self.calls = 0

    def extract(self, images: list[str]) -> AiProviderResponse:
        del images
        self.calls += 1
        raise AiProviderUnavailableError


def settings(tmp_path) -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        max_upload_mb=1,
        max_document_pages=5,
        object_store_backend="local",
        object_store_local_path=str(tmp_path / "objects"),
        ai_confidence_threshold=0.9,
        ai_lexical_match_threshold=0.88,
        ai_quantity_outlier_threshold=1000,
        ai_retry_base_seconds=1,
    )


def extraction(*, confidence: float = 0.99, extra: dict | None = None) -> dict:
    result = {
        "document_type": "goods_receipt",
        "document_number": "DL-2026-1048",
        "document_date": "2026-07-25",
        "items": [
            {
                "description": "Teszt termék",
                "barcode": "5990000000012",
                "quantity": 2,
                "unit": "carton",
                "confidence": confidence,
                "source_page": 1,
            }
        ],
    }
    if extra:
        result.update(extra)
    return result


def prepare_job(
    session: Session,
    seeded,
    tmp_path,
    *,
    auto_confirm_requested: bool = False,
):
    _, user, product = seeded
    packaging = PackagingUnit(
        organization_id=user.organization_id,
        product_id=product.id,
        name="carton",
        multiplier_to_base_unit=12,
    )
    session.add(packaging)
    session.flush()
    session.add(
        ProductBarcode(
            organization_id=user.organization_id,
            product_id=product.id,
            packaging_unit_id=packaging.id,
            code="5990000000012",
            symbology="EAN_13",
            is_primary=True,
        )
    )
    session.commit()

    resolved_settings = settings(tmp_path)
    storage = LocalObjectStorage(tmp_path / "objects")
    document = DocumentService(
        session,
        storage=storage,
        scanner=DisabledVirusScanner(),
        settings=resolved_settings,
    ).ingest(
        user=user,
        stream=BytesIO(pdf_bytes()),
        filename="known-receipt.pdf",
        declared_content_type="application/pdf",
        correlation_id="ai-document-upload",
        source_metadata={
            "auto_process_requested": auto_confirm_requested,
            "auto_confirm_requested": auto_confirm_requested,
        },
    )
    job = DocumentService(
        session,
        storage=storage,
        scanner=DisabledVirusScanner(),
        settings=resolved_settings,
    ).queue_processing(
        user=user,
        document_id=document.id,
        idempotency_key="ai-processing-known-receipt",
        correlation_id="ai-document-queue",
    ).job
    return user, product, document, job, storage, resolved_settings


def test_ai_pipeline_matches_packaging_and_confirms_exactly_once(
    session: Session, seeded, tmp_path
) -> None:
    user, product, document, job, storage, resolved_settings = prepare_job(
        session, seeded, tmp_path
    )
    draft = DocumentAiPipeline(
        session,
        provider=FakeProvider(extraction()),
        preprocessor=DocumentImagePreprocessor(
            storage=storage,
            settings=resolved_settings,
        ),
        settings=resolved_settings,
    ).process(job.id)

    assert draft is not None
    assert draft.status == "READY"
    assert draft.items[0].matched_product_id == product.id
    assert draft.items[0].base_quantity == 24
    session.refresh(document)
    assert document.status == "READY_FOR_CONFIRMATION"
    assert session.scalar(select(func.count()).select_from(AiRequest)) == 1
    assert session.scalar(select(func.count()).select_from(AiToolCall)) == 2

    receipt_service = GoodsReceiptService(session, resolved_settings)
    confirmed = receipt_service.confirm(
        user=user,
        draft_id=draft.id,
        correlation_id="receipt-confirmation",
    )
    confirmed_again = receipt_service.confirm(
        user=user,
        draft_id=draft.id,
        correlation_id="receipt-confirmation-repeated",
    )

    assert confirmed.status == "CONFIRMED"
    assert confirmed_again.status == "CONFIRMED"
    balance = session.scalar(
        select(StockBalance).where(StockBalance.product_id == product.id)
    )
    assert balance is not None and balance.quantity == 24
    assert session.scalar(select(func.count()).select_from(StockMovement)) == 1
    session.refresh(document)
    assert document.status == "COMPLETED"


def test_ai_pipeline_auto_confirms_high_confidence_requested_receipt(
    session: Session,
    seeded,
    tmp_path,
) -> None:
    user, product, document, job, storage, resolved_settings = prepare_job(
        session,
        seeded,
        tmp_path,
        auto_confirm_requested=True,
    )
    confirmed = DocumentAiPipeline(
        session,
        provider=FakeProvider(extraction(confidence=0.99)),
        preprocessor=DocumentImagePreprocessor(
            storage=storage,
            settings=resolved_settings,
        ),
        settings=resolved_settings,
    ).process(job.id)

    assert confirmed is not None
    assert confirmed.status == "CONFIRMED"
    assert confirmed.confirmed_by == user.id
    balance = session.scalar(
        select(StockBalance).where(StockBalance.product_id == product.id)
    )
    assert balance is not None and balance.quantity == 24
    assert session.scalar(select(func.count()).select_from(StockMovement)) == 1
    session.refresh(document)
    assert document.status == "COMPLETED"
    confirmation = session.scalar(
        select(AuditLog).where(
            AuditLog.entity_id == confirmed.id,
            AuditLog.action == "goods_receipt.confirmed",
        )
    )
    assert confirmation is not None
    assert confirmation.details["confirmation_source"] == "AI_AUTOMATIC"


def test_ai_pipeline_keeps_borderline_auto_receipt_for_manual_confirmation(
    session: Session,
    seeded,
    tmp_path,
) -> None:
    _, product, document, job, storage, resolved_settings = prepare_job(
        session,
        seeded,
        tmp_path,
        auto_confirm_requested=True,
    )
    draft = DocumentAiPipeline(
        session,
        provider=FakeProvider(extraction(confidence=0.95)),
        preprocessor=DocumentImagePreprocessor(
            storage=storage,
            settings=resolved_settings,
        ),
        settings=resolved_settings,
    ).process(job.id)

    assert draft is not None and draft.status == "READY"
    balance = session.scalar(
        select(StockBalance).where(StockBalance.product_id == product.id)
    )
    assert balance is not None and balance.quantity == 0
    assert session.scalar(select(func.count()).select_from(StockMovement)) == 0
    session.refresh(document)
    assert document.status == "READY_FOR_CONFIRMATION"
    skipped = session.scalar(
        select(AuditLog).where(
            AuditLog.entity_id == draft.id,
            AuditLog.action == "goods_receipt.auto_confirmation_skipped",
        )
    )
    assert skipped is not None
    assert (
        "CONFIDENCE_BELOW_AUTO_CONFIRM_THRESHOLD"
        in skipped.details["reasons"]
    )


def test_invalid_ai_output_cannot_create_receipt_or_stock(
    session: Session, seeded, tmp_path
) -> None:
    _, product, document, job, storage, resolved_settings = prepare_job(
        session, seeded, tmp_path
    )
    pipeline = DocumentAiPipeline(
        session,
        provider=FakeProvider(
            extraction(extra={"execute_sql": "UPDATE stock_balances SET quantity = 999"})
        ),
        preprocessor=DocumentImagePreprocessor(
            storage=storage,
            settings=resolved_settings,
        ),
        settings=resolved_settings,
    )

    assert pipeline.process(job.id) is None
    session.refresh(job)
    session.refresh(document)
    assert job.status == "FAILED"
    assert job.error_code == "ai_response_invalid"
    assert document.status == "NEEDS_REVIEW"
    assert session.scalar(select(func.count()).select_from(GoodsReceiptDraft)) == 0
    balance = session.scalar(
        select(StockBalance).where(StockBalance.product_id == product.id)
    )
    assert balance is not None and balance.quantity == 0
    review = session.scalar(
        select(ReviewTask).where(ReviewTask.entity_id == document.id)
    )
    assert review is not None and review.reason_code == "ai_response_invalid"


def test_provider_outage_leaves_job_retryable(
    session: Session, seeded, tmp_path
) -> None:
    _, _, document, job, storage, resolved_settings = prepare_job(session, seeded, tmp_path)
    pipeline = DocumentAiPipeline(
        session,
        provider=UnavailableProvider(),
        preprocessor=DocumentImagePreprocessor(
            storage=storage,
            settings=resolved_settings,
        ),
        settings=resolved_settings,
    )

    assert pipeline.process(job.id) is None
    session.refresh(job)
    session.refresh(document)
    assert job.status == "RETRY"
    assert job.next_attempt_at is not None
    assert document.status == "QUEUED"
    assert session.scalar(
        select(func.count()).select_from(ReviewTask)
    ) == 0


def test_circuit_breaker_pauses_repeated_provider_calls(
    session: Session, seeded, tmp_path
) -> None:
    _, _, document, job, storage, resolved_settings = prepare_job(
        session, seeded, tmp_path
    )
    resolved_settings.ai_circuit_failure_threshold = 1
    resolved_settings.ai_circuit_cooldown_seconds = 60
    provider = UnavailableProvider()
    pipeline = DocumentAiPipeline(
        session,
        provider=provider,
        preprocessor=DocumentImagePreprocessor(
            storage=storage,
            settings=resolved_settings,
        ),
        settings=resolved_settings,
    )

    assert pipeline.process(job.id) is None
    session.refresh(job)
    job.next_attempt_at = utc_now() - timedelta(seconds=1)
    session.commit()

    assert pipeline.process(job.id) is None
    session.refresh(job)
    session.refresh(document)
    assert provider.calls == 1
    assert job.status == "RETRY"
    assert job.error_code == "ai_circuit_open"
    assert document.status == "QUEUED"
    assert session.scalar(select(func.count()).select_from(AiRequest)) == 2


def test_manual_review_can_resolve_low_confidence_match(
    session: Session, seeded, tmp_path
) -> None:
    user, product, document, job, storage, resolved_settings = prepare_job(
        session, seeded, tmp_path
    )
    draft = DocumentAiPipeline(
        session,
        provider=FakeProvider(extraction(confidence=0.4)),
        preprocessor=DocumentImagePreprocessor(
            storage=storage,
            settings=resolved_settings,
        ),
        settings=resolved_settings,
    ).process(job.id)
    assert draft is not None and draft.status == "NEEDS_REVIEW"
    packaging = session.scalar(
        select(PackagingUnit).where(PackagingUnit.product_id == product.id)
    )
    assert packaging is not None

    reviewed = GoodsReceiptService(session, resolved_settings).update_item(
        user=user,
        draft_id=draft.id,
        item_id=draft.items[0].id,
        product_id=product.id,
        packaging_unit_id=packaging.id,
        quantity=2,
        correlation_id="manual-ai-review",
    )

    assert reviewed.status == "READY"
    assert reviewed.items[0].match_method == "MANUAL"
    assert reviewed.items[0].validation_issues == []
    session.refresh(document)
    assert document.status == "READY_FOR_CONFIRMATION"


def test_goods_receipt_api_returns_ai_audit_metadata(
    client, session: Session, seeded, tmp_path
) -> None:
    _, _, document, job, storage, resolved_settings = prepare_job(session, seeded, tmp_path)
    draft = DocumentAiPipeline(
        session,
        provider=FakeProvider(extraction()),
        preprocessor=DocumentImagePreprocessor(
            storage=storage,
            settings=resolved_settings,
        ),
        settings=resolved_settings,
    ).process(job.id)
    assert draft is not None

    login_response = client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": "tesztbolt",
            "email": "admin@teszt.hu",
            "password": "Secret-1234!",
        },
    )
    headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}
    response = client.get(
        f"/api/v1/goods-receipts/by-document/{document.id}",
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["document_number"] == "DL-2026-1048"
    assert body["ai_result"]["request"]["prompt_version"] == "goods-receipt-v1"
    assert body["items"][0]["matched_product"]["internal_sku"] == "TEST-001"
