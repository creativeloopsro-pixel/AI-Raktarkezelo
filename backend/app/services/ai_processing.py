from __future__ import annotations

import logging
import unicodedata
from datetime import timedelta
from decimal import Decimal
from difflib import SequenceMatcher
from hashlib import sha256

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.contracts import ExtractedGoodsReceiptItem, GoodsReceiptExtraction
from app.ai.gateway import (
    AiCircuitOpenError,
    AiGatewayError,
    AiProvider,
    AiResponseInvalidError,
    get_ai_provider,
)
from app.ai.preprocessing import DocumentImagePreprocessor, DocumentPreprocessingError
from app.config import Settings, get_settings
from app.models import (
    AiRequest,
    AiResult,
    AiToolCall,
    AuditLog,
    Document,
    DocumentProcessingJob,
    GoodsReceiptDraft,
    GoodsReceiptItem,
    PackagingUnit,
    Product,
    ProductBarcode,
    ReviewTask,
    User,
    utc_now,
)
from app.services.ai_settings import AiSettingsService
from app.services.goods_receipts import GoodsReceiptService
from app.services.identity import effective_permissions

logger = logging.getLogger(__name__)


def normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    ascii_text = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    letters_and_spaces = "".join(
        character if character.isalnum() else " " for character in ascii_text
    )
    return " ".join(letters_and_spaces.split())


class ProductMatcher:
    def __init__(self, session: Session, organization_id: str, settings: Settings):
        self.session = session
        self.organization_id = organization_id
        self.settings = settings

    def match(
        self,
        item: ExtractedGoodsReceiptItem,
        result: AiResult,
        document: Document,
    ) -> GoodsReceiptItem:
        product: Product | None = None
        packaging: PackagingUnit | None = None
        method: str | None = None
        issues: list[str] = []

        if item.barcode:
            barcode = self.session.scalar(
                select(ProductBarcode).where(
                    ProductBarcode.organization_id == self.organization_id,
                    ProductBarcode.code == item.barcode,
                )
            )
            self._record_tool(
                result,
                "find_product_by_barcode",
                {"code": item.barcode},
                {"found": barcode is not None},
            )
            if barcode is not None:
                product = self._product(barcode.product_id)
                if barcode.packaging_unit_id:
                    packaging = self._packaging(product.id, barcode.packaging_unit_id)
                method = "BARCODE"

        if product is None:
            products = list(
                self.session.scalars(
                    select(Product).where(
                        Product.organization_id == self.organization_id,
                        Product.status == "active",
                    )
                )
            )
            normalized_description = normalize_text(item.description)
            exact = next(
                (
                    candidate
                    for candidate in products
                    if normalize_text(candidate.name) == normalized_description
                ),
                None,
            )
            if exact is not None:
                product = exact
                method = "EXACT_NAME"
            elif products:
                scored = [
                    (
                        SequenceMatcher(
                            None,
                            normalized_description,
                            normalize_text(candidate.name),
                        ).ratio(),
                        candidate,
                    )
                    for candidate in products
                ]
                score, candidate = max(scored, key=lambda pair: pair[0])
                if score >= self.settings.ai_lexical_match_threshold:
                    product = candidate
                    method = "LEXICAL"
            self._record_tool(
                result,
                "search_products",
                {"query": item.description},
                {
                    "product_id": product.id if product else None,
                    "match_method": method,
                },
            )

        factor: Decimal | None = None
        if product is None:
            issues.append("UNKNOWN_PRODUCT")
        else:
            if packaging is None:
                packaging = self._packaging_by_name(product.id, item.unit)
            if packaging is not None:
                factor = packaging.multiplier_to_base_unit
            elif normalize_text(item.unit) in {
                normalize_text(product.base_unit),
                "piece",
                "pcs",
                "db",
                "darab",
            }:
                factor = Decimal("1")
            else:
                issues.append("UNKNOWN_PACKAGING_UNIT")
            self._record_tool(
                result,
                "get_packaging_units",
                {"product_id": product.id},
                {
                    "selected_packaging_unit_id": packaging.id if packaging else None,
                    "conversion_factor": str(factor) if factor is not None else None,
                },
            )

        if item.confidence < Decimal(str(self.settings.ai_confidence_threshold)):
            issues.append("LOW_CONFIDENCE")
        base_quantity = item.quantity * factor if factor is not None else None
        if (
            base_quantity is not None
            and base_quantity > Decimal(str(self.settings.ai_quantity_outlier_threshold))
        ):
            issues.append("QUANTITY_OUTLIER")
        if document.page_count and item.source_page > document.page_count:
            issues.append("INVALID_SOURCE_PAGE")

        return GoodsReceiptItem(
            organization_id=self.organization_id,
            line_number=0,
            description=item.description,
            barcode=item.barcode,
            quantity=item.quantity,
            unit=item.unit,
            confidence=item.confidence,
            source_page=item.source_page,
            matched_product_id=product.id if product else None,
            packaging_unit_id=packaging.id if packaging else None,
            conversion_factor=factor,
            base_quantity=base_quantity,
            match_method=method,
            status="READY" if not issues else "NEEDS_REVIEW",
            validation_issues=issues,
        )

    def _product(self, product_id: str) -> Product | None:
        return self.session.scalar(
            select(Product).where(
                Product.id == product_id,
                Product.organization_id == self.organization_id,
                Product.status == "active",
            )
        )

    def _packaging(self, product_id: str, packaging_id: str) -> PackagingUnit | None:
        return self.session.scalar(
            select(PackagingUnit).where(
                PackagingUnit.id == packaging_id,
                PackagingUnit.organization_id == self.organization_id,
                PackagingUnit.product_id == product_id,
            )
        )

    def _packaging_by_name(self, product_id: str, unit: str) -> PackagingUnit | None:
        normalized_unit = normalize_text(unit)
        units = self.session.scalars(
            select(PackagingUnit).where(
                PackagingUnit.organization_id == self.organization_id,
                PackagingUnit.product_id == product_id,
            )
        )
        return next(
            (candidate for candidate in units if normalize_text(candidate.name) == normalized_unit),
            None,
        )

    def _record_tool(
        self,
        result: AiResult,
        name: str,
        arguments: dict,
        summary: dict,
    ) -> None:
        self.session.add(
            AiToolCall(
                organization_id=self.organization_id,
                ai_result_id=result.id,
                tool_name=name,
                arguments=arguments,
                result_summary=summary,
            )
        )


class DocumentAiPipeline:
    def __init__(
        self,
        session: Session,
        *,
        provider: AiProvider | None = None,
        preprocessor: DocumentImagePreprocessor | None = None,
        settings: Settings | None = None,
    ):
        self.session = session
        self.settings = settings or get_settings()
        self.provider = provider
        self.preprocessor = preprocessor or DocumentImagePreprocessor(settings=self.settings)

    def process(self, job_id: str) -> GoodsReceiptDraft | None:
        provider = self.provider or self._provider_for_job(job_id)
        claimed = self._claim(job_id, provider)
        if claimed is None:
            return None
        job, document, ai_request = claimed

        try:
            self._ensure_circuit_closed(ai_request)
            images = self.preprocessor.prepare(document)
            ai_request.request_metadata = {
                "page_count": len(images),
                "content_type": document.content_type,
                "schema": "GoodsReceiptExtraction",
            }
            self.session.commit()
            response = provider.extract(images)
            extraction = GoodsReceiptExtraction.model_validate_json(response.content)
        except ValidationError as exc:
            self._fail(
                job,
                document,
                ai_request,
                AiResponseInvalidError(str(exc)),
                retriable=False,
            )
            return None
        except (AiGatewayError, DocumentPreprocessingError) as exc:
            self._fail(
                job,
                document,
                ai_request,
                exc,
                retriable=getattr(exc, "retriable", False),
            )
            return None
        except Exception:
            logger.exception("Unexpected AI pipeline failure for job %s", job_id)
            self._fail(
                job,
                document,
                ai_request,
                AiResponseInvalidError(),
                retriable=False,
            )
            return None

        return self._complete(job, document, ai_request, extraction, response)

    def _provider_for_job(self, job_id: str) -> AiProvider:
        organization_id = self.session.scalar(
            select(DocumentProcessingJob.organization_id).where(
                DocumentProcessingJob.id == job_id
            )
        )
        runtime_settings = (
            AiSettingsService(
                self.session, settings=self.settings
            ).runtime_settings(organization_id)
            if organization_id
            else self.settings
        )
        return get_ai_provider(runtime_settings)

    def _claim(
        self, job_id: str, provider: AiProvider
    ) -> tuple[DocumentProcessingJob, Document, AiRequest] | None:
        job = self.session.scalar(
            select(DocumentProcessingJob)
            .where(DocumentProcessingJob.id == job_id)
            .with_for_update()
        )
        if job is None or job.status not in {"PENDING", "RETRY"}:
            return None
        now = utc_now()
        if job.next_attempt_at is not None and job.next_attempt_at > now:
            return None
        document = self.session.scalar(
            select(Document)
            .where(
                Document.id == job.document_id,
                Document.organization_id == job.organization_id,
            )
            .with_for_update()
        )
        if document is None:
            job.status = "FAILED"
            job.error_code = "document_not_found"
            job.completed_at = now
            self.session.commit()
            return None

        job.status = "PROCESSING"
        job.attempts += 1
        job.started_at = now
        job.next_attempt_at = None
        document.status = "PROCESSING"
        ai_request = AiRequest(
            organization_id=job.organization_id,
            job_id=job.id,
            document_id=document.id,
            provider=provider.name,
            model_name=provider.model,
            prompt_version=self.settings.ai_prompt_version,
            status="RUNNING",
        )
        self.session.add(ai_request)
        self.session.commit()
        return job, document, ai_request

    def _complete(
        self,
        job: DocumentProcessingJob,
        document: Document,
        ai_request: AiRequest,
        extraction: GoodsReceiptExtraction,
        response,
    ) -> GoodsReceiptDraft:
        now = utc_now()
        normalized = extraction.model_dump(mode="json")
        overall_confidence = min(item.confidence for item in extraction.items)
        result = AiResult(
            organization_id=job.organization_id,
            request_id=ai_request.id,
            document_id=document.id,
            normalized_output=normalized,
            overall_confidence=overall_confidence,
            response_hash=sha256(response.content.encode("utf-8")).hexdigest(),
            model_version=response.model_version,
        )
        self.session.add(result)
        self.session.flush()

        matcher = ProductMatcher(self.session, job.organization_id, self.settings)
        matched_items: list[GoodsReceiptItem] = []
        all_issues: list[str] = []
        for line_number, extracted_item in enumerate(extraction.items, start=1):
            item = matcher.match(extracted_item, result, document)
            item.line_number = line_number
            matched_items.append(item)
            all_issues.extend(item.validation_issues)

        draft_status = "READY" if not all_issues else "NEEDS_REVIEW"
        draft = GoodsReceiptDraft(
            organization_id=job.organization_id,
            document_id=document.id,
            ai_result_id=result.id,
            document_number=extraction.document_number,
            document_date=extraction.document_date,
            status=draft_status,
            validation_issues=sorted(set(all_issues)),
            items=matched_items,
        )
        self.session.add(draft)
        self.session.flush()

        if all_issues:
            self.session.add(
                ReviewTask(
                    organization_id=job.organization_id,
                    task_type="GOODS_RECEIPT_REVIEW",
                    entity_type="goods_receipt_draft",
                    entity_id=draft.id,
                    reason_code=all_issues[0],
                    context={
                        "filename": document.original_filename,
                        "document_id": document.id,
                        "draft_id": draft.id,
                        "issues": sorted(set(all_issues)),
                    },
                )
            )
            document.status = "NEEDS_REVIEW"
        else:
            document.status = "READY_FOR_CONFIRMATION"

        job.status = "COMPLETED"
        job.error_code = None
        job.completed_at = now
        ai_request.status = "COMPLETED"
        ai_request.model_name = response.model
        ai_request.response_metadata = response.provider_metadata
        ai_request.duration_ms = response.duration_ms
        ai_request.prompt_tokens = response.prompt_tokens
        ai_request.completion_tokens = response.completion_tokens
        ai_request.completed_at = now
        self.session.commit()
        self.session.refresh(draft)
        return self._auto_confirm_if_requested(draft, document, job.id)

    def _auto_confirm_if_requested(
        self,
        draft: GoodsReceiptDraft,
        document: Document,
        job_id: str,
    ) -> GoodsReceiptDraft:
        metadata = document.validation_summary or {}
        if not (
            self.settings.ai_auto_confirm_receipts
            and metadata.get("auto_confirm_requested") is True
        ):
            return draft

        reasons: list[str] = []
        items = list(draft.items)
        if draft.status != "READY" or draft.validation_issues or not items:
            reasons.append("DRAFT_NOT_READY")
        minimum_confidence = Decimal(
            str(self.settings.ai_auto_confirm_min_confidence)
        )
        if any(item.confidence < minimum_confidence for item in items):
            reasons.append("CONFIDENCE_BELOW_AUTO_CONFIRM_THRESHOLD")
        if any(item.match_method not in {"BARCODE", "EXACT_NAME"} for item in items):
            reasons.append("MATCH_REQUIRES_REVIEW")

        operator = (
            self.session.get(User, document.uploaded_by)
            if document.uploaded_by
            else None
        )
        if operator is None or not operator.is_active:
            reasons.append("ACTIVE_OPERATOR_MISSING")
        elif not {
            "stock.receive",
            "receipts.confirm",
        }.issubset(effective_permissions(self.session, operator)):
            reasons.append("OPERATOR_PERMISSION_MISSING")

        correlation_id = f"ai-auto-confirm:{job_id}"
        if reasons:
            self._record_auto_confirmation_result(
                document=document,
                draft=draft,
                action="goods_receipt.auto_confirmation_skipped",
                correlation_id=correlation_id,
                reasons=reasons,
            )
            return GoodsReceiptService(
                self.session,
                self.settings,
            ).get_by_document(document.organization_id, document.id)

        assert operator is not None
        try:
            return GoodsReceiptService(self.session, self.settings).confirm(
                user=operator,
                draft_id=draft.id,
                correlation_id=correlation_id,
                confirmation_source="AI_AUTOMATIC",
            )
        except Exception as exc:
            logger.exception(
                "Az automatikus AI-bevételezés sikertelen: %s",
                draft.id,
            )
            self.session.rollback()
            refreshed_document = self.session.get(Document, document.id)
            refreshed_draft = self.session.get(GoodsReceiptDraft, draft.id)
            if refreshed_document is not None and refreshed_draft is not None:
                self.session.add(
                    ReviewTask(
                        organization_id=refreshed_document.organization_id,
                        task_type="GOODS_RECEIPT_REVIEW",
                        entity_type="goods_receipt_draft",
                        entity_id=refreshed_draft.id,
                        reason_code="AUTO_CONFIRM_FAILED",
                        context={
                            "document_id": refreshed_document.id,
                            "draft_id": refreshed_draft.id,
                            "error": exc.__class__.__name__,
                        },
                    )
                )
                self._record_auto_confirmation_result(
                    document=refreshed_document,
                    draft=refreshed_draft,
                    action="goods_receipt.auto_confirmation_failed",
                    correlation_id=correlation_id,
                    reasons=["AUTO_CONFIRM_FAILED"],
                )
            return GoodsReceiptService(
                self.session,
                self.settings,
            ).get_by_document(document.organization_id, document.id)

    def _record_auto_confirmation_result(
        self,
        *,
        document: Document,
        draft: GoodsReceiptDraft,
        action: str,
        correlation_id: str,
        reasons: list[str],
    ) -> None:
        self.session.add(
            AuditLog(
                organization_id=document.organization_id,
                actor_id=document.uploaded_by,
                action=action,
                entity_type="goods_receipt",
                entity_id=draft.id,
                correlation_id=correlation_id,
                details={
                    "document_id": document.id,
                    "reasons": sorted(set(reasons)),
                },
            )
        )
        self.session.commit()

    def _ensure_circuit_closed(self, request: AiRequest) -> None:
        threshold = max(self.settings.ai_circuit_failure_threshold, 1)
        cutoff = utc_now() - timedelta(
            seconds=max(self.settings.ai_circuit_cooldown_seconds, 1)
        )
        history = list(
            self.session.scalars(
                select(AiRequest)
                .where(
                    AiRequest.id != request.id,
                    AiRequest.organization_id == request.organization_id,
                    AiRequest.provider == request.provider,
                    AiRequest.status.in_(("COMPLETED", "FAILED")),
                    AiRequest.completed_at >= cutoff,
                )
                .order_by(AiRequest.completed_at.desc())
                .limit(threshold)
            )
        )
        if len(history) == threshold and all(
            previous.status == "FAILED"
            and previous.error_code == "ai_provider_unavailable"
            for previous in history
        ):
            raise AiCircuitOpenError

    def _fail(
        self,
        job: DocumentProcessingJob,
        document: Document,
        ai_request: AiRequest,
        error: Exception,
        *,
        retriable: bool,
    ) -> None:
        now = utc_now()
        error_code = getattr(error, "code", "ai_processing_failed")
        ai_request.status = "FAILED"
        ai_request.error_code = error_code
        ai_request.completed_at = now
        terminal = not retriable or job.attempts >= self.settings.ai_max_retries
        if terminal:
            job.status = "FAILED"
            job.completed_at = now
            document.status = "NEEDS_REVIEW"
            existing_review = self.session.scalar(
                select(ReviewTask).where(
                    ReviewTask.organization_id == job.organization_id,
                    ReviewTask.entity_type == "document",
                    ReviewTask.entity_id == document.id,
                    ReviewTask.status == "OPEN",
                    ReviewTask.reason_code == error_code,
                )
            )
            if existing_review is None:
                self.session.add(
                    ReviewTask(
                        organization_id=job.organization_id,
                        task_type="AI_PROCESSING_FAILURE",
                        entity_type="document",
                        entity_id=document.id,
                        reason_code=error_code,
                        context={
                            "filename": document.original_filename,
                            "document_id": document.id,
                        },
                    )
                )
        else:
            job.status = "RETRY"
            delay = self.settings.ai_retry_base_seconds * (2 ** (job.attempts - 1))
            job.next_attempt_at = now + timedelta(seconds=delay)
            document.status = "QUEUED"
        job.error_code = error_code
        self.session.commit()
