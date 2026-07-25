from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from difflib import SequenceMatcher
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import BinaryIO

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.config import Settings, get_settings
from app.models import (
    AuditLog,
    ExternalProductMapping,
    OutboxEvent,
    Product,
    ProductBarcode,
    ReviewTask,
    StockBalance,
    StockMovement,
    User,
    VrpImportBatch,
    VrpImportError,
    VrpImportItem,
    VrpImportSchedule,
    new_id,
    utc_now,
)
from app.services.stock import StockService
from app.storage import ObjectStorage, get_object_storage
from app.virus_scan import (
    InfectedFileError,
    VirusScanner,
    VirusScannerUnavailableError,
    get_virus_scanner,
)
from app.vrp.parser import (
    ParsedVrpItem,
    VrpReportParserError,
    VrpSalesReportParser,
    normalize_vrp_text,
)
from app.vrp.scheduling import calculate_next_run

VRP_PLUGIN_ID = "vrp-import"
ACTIVE_PERIOD_STATUSES = {
    "READY",
    "SCHEDULED",
    "PROCESSING",
    "COMPLETED",
    "NEEDS_REVIEW",
}


class VrpImportErrorBase(Exception):
    code = "vrp_import_error"


class VrpImportNotFoundError(VrpImportErrorBase):
    code = "vrp_import_not_found"


class VrpItemNotFoundError(VrpImportErrorBase):
    code = "vrp_item_not_found"


class VrpDuplicateError(VrpImportErrorBase):
    code = "vrp_duplicate"

    def __init__(self, existing_batch_id: str):
        self.existing_batch_id = existing_batch_id


class VrpUnsupportedFileError(VrpImportErrorBase):
    code = "vrp_unsupported_file"


class VrpFileTooLargeError(VrpImportErrorBase):
    code = "vrp_file_too_large"


class VrpUnsafeFileError(VrpImportErrorBase):
    code = "vrp_unsafe_file"


class VrpScannerUnavailableError(VrpImportErrorBase):
    code = "vrp_scanner_unavailable"


class VrpInvalidPeriodError(VrpImportErrorBase):
    code = "vrp_invalid_period"


class VrpInvalidReportError(VrpImportErrorBase):
    code = "vrp_invalid_report"

    def __init__(self, message: str):
        self.message = message


class VrpNotProcessableError(VrpImportErrorBase):
    code = "vrp_not_processable"


class VrpInvalidMappingError(VrpImportErrorBase):
    code = "vrp_invalid_mapping"


class VrpNegativeStockError(VrpImportErrorBase):
    code = "vrp_negative_stock_blocked"


class VrpNotReversibleError(VrpImportErrorBase):
    code = "vrp_not_reversible"


@dataclass(frozen=True)
class VrpUploadResult:
    batch: VrpImportBatch
    overlap_batch_id: str | None


def external_mapping_key(external_id: str | None, external_name: str) -> str:
    if external_id:
        return f"id:{normalize_vrp_text(external_id)}"
    return f"name:{normalize_vrp_text(external_name)}"


class VrpImportService:
    def __init__(
        self,
        session: Session,
        *,
        storage: ObjectStorage | None = None,
        scanner: VirusScanner | None = None,
        parser: VrpSalesReportParser | None = None,
        settings: Settings | None = None,
    ):
        self.session = session
        self.settings = settings or get_settings()
        self.storage = storage or get_object_storage()
        self.scanner = scanner or get_virus_scanner()
        self.parser = parser or VrpSalesReportParser(max_rows=self.settings.vrp_max_rows)

    def list_batches(
        self, organization_id: str, *, limit: int = 100
    ) -> list[VrpImportBatch]:
        return list(
            self.session.scalars(
                select(VrpImportBatch)
                .options(
                    selectinload(VrpImportBatch.items).selectinload(
                        VrpImportItem.matched_product
                    ),
                    selectinload(VrpImportBatch.errors),
                )
                .where(VrpImportBatch.organization_id == organization_id)
                .order_by(VrpImportBatch.created_at.desc())
                .limit(limit)
            )
        )

    def get_batch(self, organization_id: str, batch_id: str) -> VrpImportBatch:
        batch = self.session.scalar(
            select(VrpImportBatch)
            .options(
                selectinload(VrpImportBatch.items).selectinload(
                    VrpImportItem.matched_product
                ),
                selectinload(VrpImportBatch.errors),
            )
            .where(
                VrpImportBatch.id == batch_id,
                VrpImportBatch.organization_id == organization_id,
            )
        )
        if batch is None:
            raise VrpImportNotFoundError
        return batch

    def get_schedule(self, organization_id: str) -> VrpImportSchedule:
        schedule = self.session.get(VrpImportSchedule, organization_id)
        if schedule is None:
            schedule = VrpImportSchedule(organization_id=organization_id)
            self.session.add(schedule)
            self.session.commit()
            self.session.refresh(schedule)
        return schedule

    def update_schedule(
        self,
        *,
        user: User,
        frequency: str,
        processing_time,
        timezone: str,
        weekly_day: str,
        monthly_rule: str,
        auto_process: bool,
        unknown_product_policy: str,
        negative_stock_policy: str,
        overlap_policy: str,
        correlation_id: str,
    ) -> VrpImportSchedule:
        effective_auto_process = auto_process and frequency != "MANUAL"
        schedule = self.session.get(
            VrpImportSchedule,
            user.organization_id,
            with_for_update=True,
        )
        if schedule is None:
            schedule = VrpImportSchedule(organization_id=user.organization_id)
            self.session.add(schedule)

        schedule.frequency = frequency
        schedule.processing_time = processing_time
        schedule.timezone = timezone
        schedule.weekly_day = weekly_day
        schedule.monthly_rule = monthly_rule
        schedule.auto_process = effective_auto_process
        schedule.unknown_product_policy = unknown_product_policy
        schedule.negative_stock_policy = negative_stock_policy
        schedule.overlap_policy = overlap_policy
        schedule.updated_by = user.id
        schedule.next_run_at = (
            calculate_next_run(
                frequency=frequency,
                processing_time=processing_time,
                timezone_name=timezone,
                weekly_day=weekly_day,
                monthly_rule=monthly_rule,
            )
            if effective_auto_process
            else None
        )

        batches = self.session.scalars(
            select(VrpImportBatch)
            .where(
                VrpImportBatch.organization_id == user.organization_id,
                VrpImportBatch.status.in_(("READY", "SCHEDULED")),
            )
            .with_for_update()
        )
        for batch in batches:
            if effective_auto_process:
                batch.status = "SCHEDULED"
                batch.scheduled_for = schedule.next_run_at
            else:
                batch.status = "READY"
                batch.scheduled_for = None

        self.session.add(
            AuditLog(
                organization_id=user.organization_id,
                actor_id=user.id,
                action="vrp.schedule_updated",
                entity_type="vrp_import_schedule",
                entity_id=user.organization_id,
                correlation_id=correlation_id,
                details={
                    "frequency": frequency,
                    "auto_process": effective_auto_process,
                    "unknown_product_policy": unknown_product_policy,
                    "negative_stock_policy": negative_stock_policy,
                },
            )
        )
        self.session.commit()
        self.session.refresh(schedule)
        return schedule

    def ingest(
        self,
        *,
        user: User,
        stream: BinaryIO,
        filename: str,
        declared_content_type: str | None,
        period_start: date,
        period_end: date,
        external_report_id: str | None,
        correlation_id: str,
    ) -> VrpUploadResult:
        if period_start > period_end or (period_end - period_start).days > 366:
            raise VrpInvalidPeriodError

        safe_filename = Path(filename or "vrp-report").name[:255]
        suffix = Path(safe_filename).suffix.casefold()
        content_type = self._content_type(suffix)
        max_bytes = self.settings.vrp_max_upload_mb * 1024 * 1024
        stored = False
        object_key = ""

        with TemporaryDirectory(prefix="ai-raktar-vrp-") as temp_directory:
            temporary_path = Path(temp_directory) / f"report{suffix}"
            file_hash = sha256()
            total_bytes = 0
            with temporary_path.open("wb") as temporary_file:
                while chunk := stream.read(1024 * 1024):
                    total_bytes += len(chunk)
                    if total_bytes > max_bytes:
                        raise VrpFileTooLargeError
                    file_hash.update(chunk)
                    temporary_file.write(chunk)
            if total_bytes == 0:
                raise VrpUnsupportedFileError

            payload = temporary_path.read_bytes()
            self._validate_signature(suffix, payload)
            try:
                self.scanner.scan(temporary_path)
            except InfectedFileError as exc:
                raise VrpUnsafeFileError from exc
            except VirusScannerUnavailableError as exc:
                raise VrpScannerUnavailableError from exc

            digest = file_hash.hexdigest()
            duplicate = self._duplicate(
                user.organization_id,
                digest,
                external_report_id,
            )
            if duplicate is not None:
                raise VrpDuplicateError(duplicate.id)

            try:
                parsed = self.parser.parse(payload, safe_filename)
            except VrpReportParserError as exc:
                raise VrpInvalidReportError(str(exc)) from exc
            canonical_duplicate = self.session.scalar(
                select(VrpImportBatch).where(
                    VrpImportBatch.organization_id == user.organization_id,
                    VrpImportBatch.canonical_items_hash
                    == parsed.canonical_items_hash,
                )
            )
            if canonical_duplicate is not None:
                raise VrpDuplicateError(canonical_duplicate.id)

            schedule = self.get_schedule(user.organization_id)
            overlap = self._overlap(
                user.organization_id,
                period_start,
                period_end,
            )
            batch_id = new_id()
            object_key = (
                f"{user.organization_id}/vrp/{batch_id}/{digest[:20]}{suffix}"
            )

            try:
                self.storage.put_file(temporary_path, object_key, content_type)
                stored = True
                items = [
                    self._match_item(
                        user.organization_id,
                        batch_id,
                        item,
                        schedule.unknown_product_policy,
                    )
                    for item in parsed.items
                ]
                parser_errors = [
                    VrpImportError(
                        organization_id=user.organization_id,
                        line_number=error.line_number,
                        error_code=error.error_code,
                        message=error.message,
                        raw_row=error.raw_row,
                    )
                    for error in parsed.errors
                ]

                status, scheduled_for = self._initial_status(
                    items=items,
                    parser_errors=parser_errors,
                    schedule=schedule,
                    overlap=overlap,
                )
                error_summary: dict = {
                    "parser_error_count": len(parser_errors),
                    "unknown_product_count": sum(
                        "UNKNOWN_PRODUCT" in item.validation_issues
                        for item in items
                    ),
                }
                if overlap is not None:
                    error_summary["overlap_batch_id"] = overlap.id

                batch = VrpImportBatch(
                    id=batch_id,
                    organization_id=user.organization_id,
                    original_filename=safe_filename,
                    content_type=content_type,
                    size_bytes=total_bytes,
                    object_key=object_key,
                    file_hash=digest,
                    canonical_items_hash=parsed.canonical_items_hash,
                    parser_version=parsed.parser_version,
                    external_report_id=external_report_id,
                    period_start=period_start,
                    period_end=period_end,
                    status=status,
                    scheduled_for=scheduled_for,
                    error_summary=error_summary,
                    uploaded_by=user.id,
                    items=items,
                    errors=parser_errors,
                )
                self.session.add(batch)
                self.session.flush()

                review_reason = self._review_reason(
                    overlap=overlap,
                    parser_error_count=len(parser_errors),
                    items=items,
                )
                if review_reason:
                    self._create_review(batch, review_reason)

                self.session.add(
                    AuditLog(
                        organization_id=user.organization_id,
                        actor_id=user.id,
                        action="vrp.import_uploaded",
                        entity_type="vrp_import_batch",
                        entity_id=batch.id,
                        correlation_id=correlation_id,
                        details={
                            "filename": safe_filename,
                            "file_hash": digest,
                            "period_start": period_start.isoformat(),
                            "period_end": period_end.isoformat(),
                            "status": status,
                            "item_count": len(items),
                        },
                    )
                )
                self.session.add(
                    OutboxEvent(
                        organization_id=user.organization_id,
                        event_type="vrp.import.ready",
                        aggregate_type="vrp_import_batch",
                        aggregate_id=batch.id,
                        payload={
                            "batch_id": batch.id,
                            "status": status,
                            "scheduled_for": (
                                scheduled_for.isoformat()
                                if scheduled_for is not None
                                else None
                            ),
                            "correlation_id": correlation_id,
                        },
                    )
                )
                self.session.commit()
                return VrpUploadResult(
                    batch=self.get_batch(user.organization_id, batch.id),
                    overlap_batch_id=overlap.id if overlap else None,
                )
            except IntegrityError as exc:
                self.session.rollback()
                if stored:
                    self.storage.delete(object_key)
                duplicate = self._duplicate(
                    user.organization_id,
                    digest,
                    external_report_id,
                )
                if duplicate is None:
                    duplicate = self.session.scalar(
                        select(VrpImportBatch).where(
                            VrpImportBatch.organization_id
                            == user.organization_id,
                            VrpImportBatch.canonical_items_hash
                            == parsed.canonical_items_hash,
                        )
                    )
                if duplicate is not None:
                    raise VrpDuplicateError(duplicate.id) from exc
                raise
            except Exception:
                self.session.rollback()
                if stored:
                    self.storage.delete(object_key)
                raise

    def update_item(
        self,
        *,
        user: User,
        batch_id: str,
        item_id: str,
        product_id: str,
        conversion_factor: Decimal,
        correlation_id: str,
    ) -> VrpImportBatch:
        batch = self._locked_batch(user.organization_id, batch_id)
        if batch.status in {"COMPLETED", "REVERSED", "PROCESSING"}:
            raise VrpNotProcessableError
        item = self.session.scalar(
            select(VrpImportItem)
            .where(
                VrpImportItem.id == item_id,
                VrpImportItem.batch_id == batch.id,
                VrpImportItem.organization_id == user.organization_id,
            )
            .with_for_update()
        )
        if item is None:
            raise VrpItemNotFoundError
        product = self.session.scalar(
            select(Product).where(
                Product.id == product_id,
                Product.organization_id == user.organization_id,
                Product.status == "active",
            )
        )
        if product is None or conversion_factor <= 0:
            raise VrpInvalidMappingError

        item.matched_product_id = product.id
        item.conversion_factor = conversion_factor
        item.base_quantity = item.quantity * conversion_factor
        item.match_method = "MANUAL_MAPPING"
        item.status = "READY"
        item.validation_issues = []

        key = external_mapping_key(item.external_product_id, item.external_name)
        mapping = self.session.scalar(
            select(ExternalProductMapping)
            .where(
                ExternalProductMapping.organization_id == user.organization_id,
                ExternalProductMapping.plugin_id == VRP_PLUGIN_ID,
                ExternalProductMapping.external_key == key,
            )
            .with_for_update()
        )
        if mapping is None:
            mapping = ExternalProductMapping(
                organization_id=user.organization_id,
                plugin_id=VRP_PLUGIN_ID,
                external_key=key,
                external_id=item.external_product_id,
                external_name=item.external_name,
                normalized_external_name=item.normalized_external_name,
                product_id=product.id,
                conversion_factor=conversion_factor,
                confirmed_by=user.id,
            )
            self.session.add(mapping)
        else:
            mapping.external_name = item.external_name
            mapping.normalized_external_name = item.normalized_external_name
            mapping.product_id = product.id
            mapping.conversion_factor = conversion_factor
            mapping.confirmed_by = user.id

        self._refresh_batch_state(batch)
        self.session.add(
            AuditLog(
                organization_id=user.organization_id,
                actor_id=user.id,
                action="vrp.item_mapped",
                entity_type="vrp_import_item",
                entity_id=item.id,
                correlation_id=correlation_id,
                details={
                    "product_id": product.id,
                    "conversion_factor": str(conversion_factor),
                    "mapping_key": key,
                },
            )
        )
        self.session.commit()
        return self.get_batch(user.organization_id, batch.id)

    def process(
        self,
        *,
        user: User,
        batch_id: str,
        correlation_id: str,
        force: bool = False,
    ) -> VrpImportBatch:
        batch = self._locked_batch(user.organization_id, batch_id)
        if batch.status == "COMPLETED":
            return self.get_batch(user.organization_id, batch.id)
        if batch.status == "REVERSED":
            raise VrpNotProcessableError
        if batch.status not in {"READY", "SCHEDULED"}:
            raise VrpNotProcessableError
        if (
            batch.status == "SCHEDULED"
            and not force
            and batch.scheduled_for is not None
            and batch.scheduled_for > utc_now()
        ):
            raise VrpNotProcessableError

        schedule = self.get_schedule(user.organization_id)
        items = list(
            self.session.scalars(
                select(VrpImportItem)
                .where(
                    VrpImportItem.batch_id == batch.id,
                    VrpImportItem.organization_id == user.organization_id,
                    VrpImportItem.status == "READY",
                )
                .order_by(VrpImportItem.line_number)
                .with_for_update()
            )
        )
        if not items or any(
            item.matched_product_id is None
            or item.base_quantity is None
            or item.base_quantity == 0
            for item in items
        ):
            raise VrpNotProcessableError

        totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        for item in items:
            totals[item.matched_product_id] += item.base_quantity
        try:
            warnings = self._lock_and_check_balances(
                user.organization_id,
                totals,
                schedule.negative_stock_policy,
            )
        except VrpNegativeStockError:
            batch.status = "NEEDS_REVIEW"
            batch.scheduled_for = None
            batch.error_summary = {
                **batch.error_summary,
                "negative_stock_blocked": True,
            }
            self._create_review(batch, "NEGATIVE_STOCK_BLOCKED")
            self.session.commit()
            raise

        batch.status = "PROCESSING"
        batch.processing_started_at = utc_now()
        stock_service = StockService(self.session)
        for item in items:
            stock_service.issue_vrp_sale_item(
                user=user,
                product_id=item.matched_product_id,
                quantity=item.base_quantity,
                batch_id=batch.id,
                batch_item_id=item.id,
                idempotency_key=f"vrp:{batch.id}:{item.id}",
                correlation_id=correlation_id,
            )

        now = utc_now()
        batch.status = "COMPLETED"
        batch.processed_by = user.id
        batch.processed_at = now
        batch.processing_started_at = None
        batch.scheduled_for = None
        if warnings:
            batch.error_summary = {
                **batch.error_summary,
                "negative_stock_warnings": warnings,
            }
        self._resolve_reviews(batch, user)
        self.session.add(
            AuditLog(
                organization_id=user.organization_id,
                actor_id=user.id,
                action="vrp.import_completed",
                entity_type="vrp_import_batch",
                entity_id=batch.id,
                correlation_id=correlation_id,
                details={
                    "item_count": len(items),
                    "period_start": batch.period_start.isoformat(),
                    "period_end": batch.period_end.isoformat(),
                    "negative_stock_warnings": warnings,
                },
            )
        )
        self.session.add(
            OutboxEvent(
                organization_id=user.organization_id,
                event_type="vrp.import.completed",
                aggregate_type="vrp_import_batch",
                aggregate_id=batch.id,
                payload={
                    "batch_id": batch.id,
                    "item_count": len(items),
                    "correlation_id": correlation_id,
                },
            )
        )
        self.session.commit()
        return self.get_batch(user.organization_id, batch.id)

    def reverse(
        self,
        *,
        user: User,
        batch_id: str,
        reason: str,
        correlation_id: str,
    ) -> VrpImportBatch:
        batch = self._locked_batch(user.organization_id, batch_id)
        if batch.status == "REVERSED":
            return self.get_batch(user.organization_id, batch.id)
        if batch.status != "COMPLETED":
            raise VrpNotReversibleError

        movements = list(
            self.session.scalars(
                select(StockMovement)
                .where(
                    StockMovement.organization_id == user.organization_id,
                    StockMovement.source_type == "VRP_IMPORT_BATCH",
                    StockMovement.source_id == batch.id,
                    StockMovement.movement_type == "VRP_SALE_IMPORT",
                )
                .order_by(StockMovement.created_at)
                .with_for_update()
            )
        )
        if not movements:
            raise VrpNotReversibleError

        stock_service = StockService(self.session)
        for movement in movements:
            stock_service.reverse(
                user=user,
                movement_id=movement.id,
                idempotency_key=f"vrp-reverse:{batch.id}:{movement.id}",
                correlation_id=correlation_id,
                reason=reason,
            )

        now = utc_now()
        batch.status = "REVERSED"
        batch.reversed_by = user.id
        batch.reversed_at = now
        self.session.add(
            AuditLog(
                organization_id=user.organization_id,
                actor_id=user.id,
                action="vrp.import_reversed",
                entity_type="vrp_import_batch",
                entity_id=batch.id,
                correlation_id=correlation_id,
                details={"movement_count": len(movements), "reason": reason},
            )
        )
        self.session.add(
            OutboxEvent(
                organization_id=user.organization_id,
                event_type="vrp.import.reversed",
                aggregate_type="vrp_import_batch",
                aggregate_id=batch.id,
                payload={
                    "batch_id": batch.id,
                    "movement_count": len(movements),
                    "correlation_id": correlation_id,
                },
            )
        )
        self.session.commit()
        return self.get_batch(user.organization_id, batch.id)

    def mark_failed(self, organization_id: str, batch_id: str, error_code: str) -> None:
        batch = self._locked_batch(organization_id, batch_id)
        if batch.status in {"COMPLETED", "REVERSED"}:
            return
        batch.status = "FAILED"
        batch.processing_started_at = None
        batch.error_summary = {**batch.error_summary, "worker_error": error_code}
        self.session.commit()

    def _match_item(
        self,
        organization_id: str,
        batch_id: str,
        parsed: ParsedVrpItem,
        unknown_policy: str,
    ) -> VrpImportItem:
        normalized_name = normalize_vrp_text(parsed.external_name)
        key = external_mapping_key(parsed.external_product_id, parsed.external_name)
        mapping = self.session.scalar(
            select(ExternalProductMapping).where(
                ExternalProductMapping.organization_id == organization_id,
                ExternalProductMapping.plugin_id == VRP_PLUGIN_ID,
                ExternalProductMapping.external_key == key,
            )
        )
        product: Product | None = None
        factor: Decimal | None = None
        method: str | None = None
        issues: list[str] = []

        if mapping is not None:
            product = self._product(organization_id, mapping.product_id)
            if product is not None:
                factor = mapping.conversion_factor
                method = "EXTERNAL_MAPPING"

        if product is None and parsed.external_product_id:
            barcode = self.session.scalar(
                select(ProductBarcode).where(
                    ProductBarcode.organization_id == organization_id,
                    ProductBarcode.code == parsed.external_product_id,
                )
            )
            if barcode is not None:
                product = self._product(organization_id, barcode.product_id)
                if product is not None:
                    factor = Decimal("1")
                    method = "BARCODE"

        products = list(
            self.session.scalars(
                select(Product).where(
                    Product.organization_id == organization_id,
                    Product.status == "active",
                )
            )
        )
        if product is None and parsed.external_product_id:
            product = next(
                (
                    candidate
                    for candidate in products
                    if normalize_vrp_text(candidate.internal_sku)
                    == normalize_vrp_text(parsed.external_product_id)
                ),
                None,
            )
            if product is not None:
                factor = Decimal("1")
                method = "EXACT_SKU"

        if product is None:
            product = next(
                (
                    candidate
                    for candidate in products
                    if normalize_vrp_text(candidate.name) == normalized_name
                ),
                None,
            )
            if product is not None:
                factor = Decimal("1")
                method = "EXACT_NAME"

        if product is None and products:
            scored = [
                (
                    SequenceMatcher(
                        None,
                        normalized_name,
                        normalize_vrp_text(candidate.name),
                    ).ratio(),
                    candidate,
                )
                for candidate in products
            ]
            score, suggestion = max(scored, key=lambda pair: pair[0])
            if score >= self.settings.ai_lexical_match_threshold:
                product = suggestion
                factor = Decimal("1")
                method = "LEXICAL_SUGGESTION"
                issues.append("MAPPING_REVIEW_REQUIRED")

        if product is None:
            issues.append("UNKNOWN_PRODUCT")

        status = "READY" if product is not None and not issues else "NEEDS_REVIEW"
        if product is None and unknown_policy == "PROCESS_KNOWN":
            status = "SKIPPED"
        return VrpImportItem(
            organization_id=organization_id,
            batch_id=batch_id,
            line_number=parsed.line_number,
            external_product_id=parsed.external_product_id,
            external_name=parsed.external_name,
            normalized_external_name=normalized_name,
            quantity=parsed.quantity,
            unit=parsed.unit,
            matched_product_id=product.id if product else None,
            conversion_factor=factor,
            base_quantity=parsed.quantity * factor if factor is not None else None,
            match_method=method,
            status=status,
            validation_issues=issues,
        )

    def _refresh_batch_state(self, batch: VrpImportBatch) -> None:
        if batch.error_summary.get("overlap_batch_id"):
            batch.status = "OVERLAP"
            batch.scheduled_for = None
            return
        if batch.errors:
            batch.status = "NEEDS_REVIEW"
            batch.scheduled_for = None
            return
        items = list(
            self.session.scalars(
                select(VrpImportItem).where(VrpImportItem.batch_id == batch.id)
            )
        )
        if (
            not items
            or not any(item.status == "READY" for item in items)
            or any(item.status == "NEEDS_REVIEW" for item in items)
        ):
            batch.status = "NEEDS_REVIEW"
            batch.scheduled_for = None
            return
        schedule = self.get_schedule(batch.organization_id)
        if schedule.auto_process and schedule.frequency != "MANUAL":
            batch.status = "SCHEDULED"
            batch.scheduled_for = schedule.next_run_at or calculate_next_run(
                frequency=schedule.frequency,
                processing_time=schedule.processing_time,
                timezone_name=schedule.timezone,
                weekly_day=schedule.weekly_day,
                monthly_rule=schedule.monthly_rule,
            )
        else:
            batch.status = "READY"
            batch.scheduled_for = None
        if batch.status in {"READY", "SCHEDULED"}:
            user = self.session.get(User, batch.uploaded_by) if batch.uploaded_by else None
            if user is not None:
                self._resolve_reviews(batch, user)

    def _initial_status(
        self,
        *,
        items: list[VrpImportItem],
        parser_errors: list[VrpImportError],
        schedule: VrpImportSchedule,
        overlap: VrpImportBatch | None,
    ) -> tuple[str, datetime | None]:
        if overlap is not None:
            return "OVERLAP", None
        if (
            parser_errors
            or not any(item.status == "READY" for item in items)
            or any(item.status == "NEEDS_REVIEW" for item in items)
        ):
            return "NEEDS_REVIEW", None
        if schedule.auto_process and schedule.frequency != "MANUAL":
            scheduled_for = schedule.next_run_at or calculate_next_run(
                frequency=schedule.frequency,
                processing_time=schedule.processing_time,
                timezone_name=schedule.timezone,
                weekly_day=schedule.weekly_day,
                monthly_rule=schedule.monthly_rule,
            )
            return "SCHEDULED", scheduled_for
        return "READY", None

    def _review_reason(
        self,
        *,
        overlap: VrpImportBatch | None,
        parser_error_count: int,
        items: list[VrpImportItem],
    ) -> str | None:
        if overlap is not None:
            return "PERIOD_OVERLAP"
        if parser_error_count:
            return "INVALID_REPORT_ROWS"
        if any("UNKNOWN_PRODUCT" in item.validation_issues for item in items):
            return "UNKNOWN_PRODUCT"
        if any("MAPPING_REVIEW_REQUIRED" in item.validation_issues for item in items):
            return "MAPPING_REVIEW_REQUIRED"
        return None

    def _create_review(self, batch: VrpImportBatch, reason: str) -> None:
        self.session.add(
            ReviewTask(
                organization_id=batch.organization_id,
                task_type="VRP_IMPORT_REVIEW",
                entity_type="vrp_import_batch",
                entity_id=batch.id,
                reason_code=reason,
                context={
                    "filename": batch.original_filename,
                    "batch_id": batch.id,
                    "period_start": batch.period_start.isoformat(),
                    "period_end": batch.period_end.isoformat(),
                },
            )
        )

    def _resolve_reviews(self, batch: VrpImportBatch, user: User) -> None:
        unresolved_items = self.session.scalar(
            select(VrpImportItem.id)
            .where(
                VrpImportItem.batch_id == batch.id,
                VrpImportItem.status.in_(("NEEDS_REVIEW", "SKIPPED")),
            )
            .limit(1)
        )
        if unresolved_items is not None:
            return
        now = utc_now()
        reviews = self.session.scalars(
            select(ReviewTask).where(
                ReviewTask.organization_id == batch.organization_id,
                ReviewTask.entity_type == "vrp_import_batch",
                ReviewTask.entity_id == batch.id,
                ReviewTask.status == "OPEN",
            )
        )
        for review in reviews:
            review.status = "RESOLVED"
            review.resolved_by = user.id
            review.resolution_note = "A VRP-import ellenőrizve."
            review.resolved_at = now

    def _lock_and_check_balances(
        self,
        organization_id: str,
        totals: dict[str, Decimal],
        policy: str,
    ) -> list[dict[str, str]]:
        warnings: list[dict[str, str]] = []
        for product_id in sorted(totals):
            balance = self.session.scalar(
                select(StockBalance)
                .where(
                    StockBalance.organization_id == organization_id,
                    StockBalance.product_id == product_id,
                )
                .with_for_update()
            )
            if balance is None:
                balance = StockBalance(
                    organization_id=organization_id,
                    product_id=product_id,
                    quantity=Decimal("0"),
                )
                self.session.add(balance)
                self.session.flush()
            resulting = balance.quantity - totals[product_id]
            if resulting < 0:
                if policy == "STOP":
                    raise VrpNegativeStockError
                warnings.append(
                    {
                        "product_id": product_id,
                        "resulting_quantity": str(resulting),
                    }
                )
        return warnings

    def _duplicate(
        self,
        organization_id: str,
        digest: str,
        external_report_id: str | None,
    ) -> VrpImportBatch | None:
        conditions = [VrpImportBatch.file_hash == digest]
        if external_report_id:
            conditions.append(
                VrpImportBatch.external_report_id == external_report_id
            )
        for condition in conditions:
            duplicate = self.session.scalar(
                select(VrpImportBatch).where(
                    VrpImportBatch.organization_id == organization_id,
                    condition,
                )
            )
            if duplicate is not None:
                return duplicate
        return None

    def _overlap(
        self,
        organization_id: str,
        period_start: date,
        period_end: date,
    ) -> VrpImportBatch | None:
        return self.session.scalar(
            select(VrpImportBatch)
            .where(
                VrpImportBatch.organization_id == organization_id,
                VrpImportBatch.status.in_(ACTIVE_PERIOD_STATUSES),
                VrpImportBatch.period_start <= period_end,
                VrpImportBatch.period_end >= period_start,
            )
            .order_by(VrpImportBatch.created_at)
            .limit(1)
        )

    def _product(self, organization_id: str, product_id: str) -> Product | None:
        return self.session.scalar(
            select(Product).where(
                Product.id == product_id,
                Product.organization_id == organization_id,
                Product.status == "active",
            )
        )

    def _locked_batch(
        self, organization_id: str, batch_id: str
    ) -> VrpImportBatch:
        batch = self.session.scalar(
            select(VrpImportBatch)
            .where(
                VrpImportBatch.id == batch_id,
                VrpImportBatch.organization_id == organization_id,
            )
            .with_for_update()
        )
        if batch is None:
            raise VrpImportNotFoundError
        return batch

    @staticmethod
    def _content_type(suffix: str) -> str:
        supported = {
            ".csv": "text/csv",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".pdf": "application/pdf",
        }
        try:
            return supported[suffix]
        except KeyError as exc:
            raise VrpUnsupportedFileError from exc

    @staticmethod
    def _validate_signature(suffix: str, payload: bytes) -> None:
        valid = (
            suffix == ".csv"
            or (suffix == ".xlsx" and payload.startswith(b"PK\x03\x04"))
            or (suffix == ".pdf" and payload.startswith(b"%PDF"))
        )
        if not valid:
            raise VrpUnsupportedFileError
