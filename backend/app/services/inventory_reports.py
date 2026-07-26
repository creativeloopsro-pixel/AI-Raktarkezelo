from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from html import escape
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo

import reportlab
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    KeepTogether,
    LongTable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    AuditLog,
    Document,
    InventoryReportRun,
    InventoryReportSchedule,
    Organization,
    Product,
    StockBalance,
    User,
    utc_now,
)
from app.services.documents import DocumentService
from app.vrp.scheduling import calculate_next_run

NAVY = colors.HexColor("#0d2940")
AMBER = colors.HexColor("#c57d08")
CREAM = colors.HexColor("#f7f5ef")
INK = colors.HexColor("#182a39")
MUTED = colors.HexColor("#667681")
LINE = colors.HexColor("#dedbd1")
SUCCESS = colors.HexColor("#2b7a68")
DANGER = colors.HexColor("#a54338")


@dataclass(frozen=True)
class InventoryReportRow:
    name: str
    internal_sku: str
    ean: str
    quantity: Decimal
    min_stock: Decimal
    base_unit: str
    status: str
    updated_at: datetime | None


@dataclass(frozen=True)
class InventoryReportSnapshot:
    organization_name: str
    frequency: str
    generated_at: datetime
    timezone: str
    rows: tuple[InventoryReportRow, ...]

    @property
    def total_quantity(self) -> Decimal:
        return sum((row.quantity for row in self.rows), Decimal("0"))

    @property
    def low_stock_count(self) -> int:
        return sum(
            1
            for row in self.rows
            if row.min_stock > 0 and row.quantity < row.min_stock
        )

    @property
    def negative_stock_count(self) -> int:
        return sum(1 for row in self.rows if row.quantity < 0)

    @property
    def missing_ean_count(self) -> int:
        return sum(1 for row in self.rows if not row.ean)


def _register_fonts() -> tuple[str, str]:
    regular_name = "AiRaktarSans"
    bold_name = "AiRaktarSansBold"
    registered = set(pdfmetrics.getRegisteredFontNames())
    dejavu_directory = Path("/usr/share/fonts/truetype/dejavu")
    if dejavu_directory.joinpath("DejaVuSans.ttf").exists():
        regular_path = dejavu_directory / "DejaVuSans.ttf"
        bold_path = dejavu_directory / "DejaVuSans-Bold.ttf"
    elif Path("C:/Windows/Fonts/arial.ttf").exists():
        regular_path = Path("C:/Windows/Fonts/arial.ttf")
        bold_path = Path("C:/Windows/Fonts/arialbd.ttf")
    else:
        font_directory = Path(reportlab.__file__).resolve().parent / "fonts"
        regular_path = font_directory / "Vera.ttf"
        bold_path = font_directory / "VeraBd.ttf"
    if regular_name not in registered:
        pdfmetrics.registerFont(TTFont(regular_name, regular_path))
    if bold_name not in registered:
        pdfmetrics.registerFont(TTFont(bold_name, bold_path))
    return regular_name, bold_name


def _format_quantity(value: Decimal) -> str:
    normalized = f"{value:,.3f}".rstrip("0").rstrip(".")
    return normalized.replace(",", " ")


def _frequency_label(frequency: str) -> str:
    return {
        "DAILY": "Naponta",
        "WEEKLY": "Hetente",
        "MONTHLY": "Havonta",
        "MANUAL": "Kézi futtatás",
    }.get(frequency, frequency)


def render_inventory_report_pdf(snapshot: InventoryReportSnapshot) -> bytes:
    regular_font, bold_font = _register_fonts()
    output = BytesIO()
    page_size = landscape(A4)
    local_generated_at = snapshot.generated_at.astimezone(ZoneInfo(snapshot.timezone))
    generated_label = local_generated_at.strftime("%Y. %m. %d. %H:%M")

    document = SimpleDocTemplate(
        output,
        pagesize=page_size,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=25 * mm,
        bottomMargin=17 * mm,
        title="Automatikus AI készletleltár",
        author="AI Raktár",
        subject="Automatikusan generált készletleltár",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "InventoryTitle",
        parent=styles["Title"],
        fontName=bold_font,
        fontSize=22,
        leading=27,
        textColor=INK,
        alignment=TA_LEFT,
        spaceAfter=4 * mm,
    )
    section_style = ParagraphStyle(
        "InventorySection",
        parent=styles["Heading2"],
        fontName=bold_font,
        fontSize=11,
        leading=14,
        textColor=INK,
        spaceBefore=4 * mm,
        spaceAfter=2.5 * mm,
    )
    body_style = ParagraphStyle(
        "InventoryBody",
        parent=styles["BodyText"],
        fontName=regular_font,
        fontSize=8.4,
        leading=12,
        textColor=MUTED,
    )
    table_header_style = ParagraphStyle(
        "InventoryTableHeader",
        parent=body_style,
        fontName=bold_font,
        fontSize=7.2,
        leading=9,
        textColor=colors.white,
    )
    table_body_style = ParagraphStyle(
        "InventoryTableBody",
        parent=body_style,
        fontSize=7.4,
        leading=9.5,
        textColor=INK,
    )

    def draw_page(canvas: Canvas, _: SimpleDocTemplate) -> None:
        width, height = page_size
        canvas.saveState()
        canvas.setFillColor(NAVY)
        canvas.rect(0, height - 16 * mm, width, 16 * mm, stroke=0, fill=1)
        canvas.setFillColor(colors.white)
        canvas.setFont(bold_font, 10)
        canvas.drawString(16 * mm, height - 10.3 * mm, "AI Raktár")
        canvas.setFont(regular_font, 7)
        canvas.drawRightString(
            width - 16 * mm,
            height - 10.3 * mm,
            f"{snapshot.organization_name} | Automatikus leltár",
        )
        canvas.setStrokeColor(LINE)
        canvas.line(16 * mm, 10.5 * mm, width - 16 * mm, 10.5 * mm)
        canvas.setFillColor(MUTED)
        canvas.setFont(regular_font, 6.7)
        canvas.drawString(
            16 * mm,
            6.3 * mm,
            f"Generálva: {generated_label} | {snapshot.timezone}",
        )
        canvas.drawRightString(
            width - 16 * mm,
            6.3 * mm,
            f"{canvas.getPageNumber()}. oldal",
        )
        canvas.restoreState()

    story: list = [
        Paragraph("Automatikus AI készletleltár", title_style),
        Paragraph(
            "A jelentés a rögzített termékek és a generálás pillanatában érvényes "
            "készletegyenlegek automatikus ellenőrzésével készült.",
            body_style,
        ),
        Spacer(1, 5 * mm),
    ]

    summary_data = [
        [
            Paragraph("TERMÉKEK", table_header_style),
            Paragraph("TELJES KÉSZLET", table_header_style),
            Paragraph("MINIMUM ALATT", table_header_style),
            Paragraph("NEGATÍV KÉSZLET", table_header_style),
            Paragraph("HIÁNYZÓ EAN", table_header_style),
            Paragraph("GYAKORISÁG", table_header_style),
        ],
        [
            Paragraph(f"<b>{len(snapshot.rows)}</b>", table_body_style),
            Paragraph(f"<b>{_format_quantity(snapshot.total_quantity)}</b>", table_body_style),
            Paragraph(f"<b>{snapshot.low_stock_count}</b>", table_body_style),
            Paragraph(f"<b>{snapshot.negative_stock_count}</b>", table_body_style),
            Paragraph(f"<b>{snapshot.missing_ean_count}</b>", table_body_style),
            Paragraph(f"<b>{_frequency_label(snapshot.frequency)}</b>", table_body_style),
        ],
    ]
    summary_table = Table(summary_data, colWidths=[40 * mm] * 6)
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("BACKGROUND", (0, 1), (-1, 1), CREAM),
                ("BOX", (0, 0), (-1, -1), 0.55, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, LINE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(summary_table)

    findings: list[str] = []
    if not snapshot.rows:
        findings.append("Nincs rögzített termék, ezért a leltár tételeket nem tartalmaz.")
    else:
        if snapshot.negative_stock_count:
            findings.append(
                f"{snapshot.negative_stock_count} terméknél negatív készlet látható; "
                "ezeket azonnal ellenőrizni kell."
            )
        if snapshot.low_stock_count:
            findings.append(
                f"{snapshot.low_stock_count} termék készlete a beállított minimum alatt van."
            )
        if snapshot.missing_ean_count:
            findings.append(
                f"{snapshot.missing_ean_count} termékhez nincs elsődleges EAN-kód rendelve."
            )
        if not findings:
            findings.append(
                "A készletben nincs negatív vagy minimum alatti tétel, és minden "
                "termék rendelkezik EAN-kóddal."
            )

    story.extend(
        [
            Paragraph("Automatikus ellenőrzés", section_style),
            KeepTogether(
                [
                    Table(
                        [
                            [
                                Paragraph(
                                    "<br/>".join(
                                        f"• {escape(finding)}" for finding in findings
                                    ),
                                    body_style,
                                )
                            ]
                        ],
                        colWidths=[240 * mm],
                        style=TableStyle(
                            [
                                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                                ("BOX", (0, 0), (-1, -1), 0.55, LINE),
                                ("LINEBEFORE", (0, 0), (0, -1), 3, AMBER),
                                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                                ("TOPPADDING", (0, 0), (-1, -1), 8),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                            ]
                        ),
                    )
                ]
            ),
            Paragraph("Készlettételek", section_style),
        ]
    )

    headers = [
        "Termék",
        "Belső cikkszám",
        "Elsődleges EAN",
        "Készlet",
        "Minimum",
        "Egység",
        "Állapot",
    ]
    table_data = [[Paragraph(header, table_header_style) for header in headers]]
    for row in snapshot.rows:
        table_data.append(
            [
                Paragraph(escape(row.name), table_body_style),
                Paragraph(escape(row.internal_sku), table_body_style),
                Paragraph(escape(row.ean or "Nincs megadva"), table_body_style),
                Paragraph(_format_quantity(row.quantity), table_body_style),
                Paragraph(_format_quantity(row.min_stock), table_body_style),
                Paragraph(escape(row.base_unit), table_body_style),
                Paragraph(escape(row.status), table_body_style),
            ]
        )

    inventory_table = LongTable(
        table_data,
        colWidths=[68 * mm, 34 * mm, 40 * mm, 24 * mm, 24 * mm, 22 * mm, 28 * mm],
        repeatRows=1,
    )
    table_commands = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.35, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]
    for index in range(1, len(table_data)):
        table_commands.append(
            ("BACKGROUND", (0, index), (-1, index), colors.white if index % 2 else CREAM)
        )
        status = snapshot.rows[index - 1].status
        if status == "NEGATÍV":
            table_commands.append(("TEXTCOLOR", (-1, index), (-1, index), DANGER))
        elif status == "MINIMUM ALATT":
            table_commands.append(("TEXTCOLOR", (-1, index), (-1, index), AMBER))
        else:
            table_commands.append(("TEXTCOLOR", (-1, index), (-1, index), SUCCESS))
    inventory_table.setStyle(TableStyle(table_commands))
    story.append(inventory_table)

    document.build(story, onFirstPage=draw_page, onLaterPages=draw_page)
    return output.getvalue()


class InventoryReportService:
    def __init__(
        self,
        session: Session,
        *,
        document_service: DocumentService | None = None,
    ):
        self.session = session
        self.document_service = document_service or DocumentService(session)

    def get_schedule(self, organization_id: str) -> InventoryReportSchedule:
        schedule = self.session.get(InventoryReportSchedule, organization_id)
        if schedule is None:
            schedule = InventoryReportSchedule(organization_id=organization_id)
            self.session.add(schedule)
            self.session.commit()
            self.session.refresh(schedule)
        return schedule

    def update_schedule(
        self,
        *,
        user: User,
        enabled: bool,
        frequency: str,
        generation_time,
        timezone: str,
        weekly_day: str,
        monthly_rule: str,
        correlation_id: str,
    ) -> InventoryReportSchedule:
        schedule = self.session.get(
            InventoryReportSchedule,
            user.organization_id,
            with_for_update=True,
        )
        if schedule is None:
            schedule = InventoryReportSchedule(organization_id=user.organization_id)
            self.session.add(schedule)
        schedule.enabled = enabled
        schedule.frequency = frequency
        schedule.generation_time = generation_time
        schedule.timezone = timezone
        schedule.weekly_day = weekly_day
        schedule.monthly_rule = monthly_rule
        schedule.next_run_at = (
            calculate_next_run(
                frequency=frequency,
                processing_time=generation_time,
                timezone_name=timezone,
                weekly_day=weekly_day,
                monthly_rule=monthly_rule,
            )
            if enabled
            else None
        )
        schedule.updated_by = user.id
        schedule.last_error_message = None
        self.session.add(
            AuditLog(
                organization_id=user.organization_id,
                actor_id=user.id,
                action="inventory_report.schedule_updated",
                entity_type="inventory_report_schedule",
                entity_id=user.organization_id,
                correlation_id=correlation_id,
                details={
                    "enabled": enabled,
                    "frequency": frequency,
                    "generation_time": generation_time.isoformat(),
                    "timezone": timezone,
                    "weekly_day": weekly_day,
                    "monthly_rule": monthly_rule,
                },
            )
        )
        self.session.commit()
        self.session.refresh(schedule)
        return schedule

    def generate_now(
        self,
        *,
        user: User,
        correlation_id: str,
    ) -> Document:
        schedule = self.get_schedule(user.organization_id)
        generated_at = utc_now()
        try:
            document = self._create_document(
                organization_id=user.organization_id,
                actor_id=user.id,
                frequency=schedule.frequency,
                timezone=schedule.timezone,
                scheduled_for=generated_at,
                generated_at=generated_at,
                report_run_id=None,
                correlation_id=correlation_id,
            )
            document.status = "COMPLETED"
            schedule.last_run_at = generated_at
            schedule.last_document_id = document.id
            schedule.last_error_message = None
            self._add_generated_audit(
                organization_id=user.organization_id,
                actor_id=user.id,
                document=document,
                correlation_id=correlation_id,
                scheduled=False,
            )
            self.session.commit()
            self.session.refresh(document)
            return document
        except Exception as exc:
            self.session.rollback()
            schedule = self.session.get(
                InventoryReportSchedule, user.organization_id
            )
            if schedule is not None:
                schedule.last_error_message = str(exc)[:500]
                self.session.commit()
            raise

    def process_run(self, run_id: str) -> Document | None:
        report_run = self.session.scalar(
            select(InventoryReportRun)
            .where(InventoryReportRun.id == run_id)
            .with_for_update()
        )
        if report_run is None or report_run.status != "PENDING":
            return None
        now = utc_now()
        if report_run.next_attempt_at and report_run.next_attempt_at > now:
            return None
        report_run.status = "PROCESSING"
        report_run.attempts += 1
        report_run.started_at = now
        report_run.error_message = None
        self.session.commit()

        try:
            schedule = self.get_schedule(report_run.organization_id)
            document = self._create_document(
                organization_id=report_run.organization_id,
                actor_id=schedule.updated_by,
                frequency=schedule.frequency,
                timezone=schedule.timezone,
                scheduled_for=report_run.scheduled_for,
                generated_at=utc_now(),
                report_run_id=report_run.id,
                correlation_id=f"inventory-report-run:{report_run.id}",
            )
            completed_at = utc_now()
            document.status = "COMPLETED"
            report_run = self.session.get(InventoryReportRun, run_id)
            schedule = self.session.get(
                InventoryReportSchedule, report_run.organization_id
            )
            report_run.status = "COMPLETED"
            report_run.document_id = document.id
            report_run.completed_at = completed_at
            report_run.next_attempt_at = None
            schedule.last_run_at = report_run.scheduled_for
            schedule.last_document_id = document.id
            schedule.last_error_message = None
            self._add_generated_audit(
                organization_id=report_run.organization_id,
                actor_id=schedule.updated_by,
                document=document,
                correlation_id=f"inventory-report-run:{report_run.id}",
                scheduled=True,
            )
            self.session.commit()
            return document
        except Exception as exc:
            self.session.rollback()
            report_run = self.session.get(InventoryReportRun, run_id)
            if report_run is None:
                raise
            report_run.error_message = str(exc)[:500]
            if report_run.attempts < 3:
                report_run.status = "PENDING"
                report_run.next_attempt_at = utc_now() + timedelta(
                    minutes=report_run.attempts * 2
                )
            else:
                report_run.status = "FAILED"
                report_run.completed_at = utc_now()
            schedule = self.session.get(
                InventoryReportSchedule, report_run.organization_id
            )
            if schedule is not None:
                schedule.last_error_message = report_run.error_message
            self.session.commit()
            return None

    def _create_document(
        self,
        *,
        organization_id: str,
        actor_id: str | None,
        frequency: str,
        timezone: str,
        scheduled_for: datetime,
        generated_at: datetime,
        report_run_id: str | None,
        correlation_id: str,
    ) -> Document:
        snapshot = self._snapshot(
            organization_id=organization_id,
            frequency=frequency,
            generated_at=generated_at,
            timezone=timezone,
        )
        pdf = render_inventory_report_pdf(snapshot)
        local_scheduled_for = scheduled_for.astimezone(ZoneInfo(snapshot.timezone))
        filename = f"ai-leltar-{local_scheduled_for:%Y-%m-%d-%H%M}.pdf"
        return self.document_service.ingest(
            organization_id=organization_id,
            actor_id=actor_id,
            stream=BytesIO(pdf),
            filename=filename,
            declared_content_type="application/pdf",
            document_type="inventory_report",
            source_type="SYSTEM_GENERATED",
            correlation_id=correlation_id,
            source_metadata={
                "report_frequency": frequency,
                "scheduled_for": scheduled_for.isoformat(),
                "generated_at": generated_at.isoformat(),
                "report_run_id": report_run_id,
                "product_count": len(snapshot.rows),
                "total_quantity": str(snapshot.total_quantity),
                "low_stock_count": snapshot.low_stock_count,
                "negative_stock_count": snapshot.negative_stock_count,
                "missing_ean_count": snapshot.missing_ean_count,
            },
        )

    def _snapshot(
        self,
        *,
        organization_id: str,
        frequency: str,
        generated_at: datetime,
        timezone: str,
    ) -> InventoryReportSnapshot:
        organization = self.session.get(Organization, organization_id)
        if organization is None:
            raise ValueError("A szervezet nem található.")
        products = list(
            self.session.scalars(
                select(Product)
                .options(selectinload(Product.barcodes))
                .where(Product.organization_id == organization_id)
                .order_by(Product.name, Product.internal_sku)
            )
        )
        balances = {
            balance.product_id: balance
            for balance in self.session.scalars(
                select(StockBalance).where(
                    StockBalance.organization_id == organization_id
                )
            )
        }
        rows: list[InventoryReportRow] = []
        for product in products:
            balance = balances.get(product.id)
            quantity = balance.quantity if balance is not None else Decimal("0")
            primary_barcode = next(
                (barcode for barcode in product.barcodes if barcode.is_primary),
                product.barcodes[0] if product.barcodes else None,
            )
            if quantity < 0:
                report_status = "NEGATÍV"
            elif product.min_stock > 0 and quantity < product.min_stock:
                report_status = "MINIMUM ALATT"
            else:
                report_status = "RENDBEN"
            rows.append(
                InventoryReportRow(
                    name=product.name,
                    internal_sku=product.internal_sku,
                    ean=primary_barcode.code if primary_barcode else "",
                    quantity=quantity,
                    min_stock=product.min_stock,
                    base_unit=product.base_unit,
                    status=report_status,
                    updated_at=balance.updated_at if balance is not None else None,
                )
            )
        return InventoryReportSnapshot(
            organization_name=organization.name,
            frequency=frequency,
            generated_at=generated_at.astimezone(UTC),
            timezone=timezone,
            rows=tuple(rows),
        )

    def _add_generated_audit(
        self,
        *,
        organization_id: str,
        actor_id: str | None,
        document: Document,
        correlation_id: str,
        scheduled: bool,
    ) -> None:
        self.session.add(
            AuditLog(
                organization_id=organization_id,
                actor_id=actor_id,
                action="inventory_report.generated",
                entity_type="document",
                entity_id=document.id,
                correlation_id=correlation_id,
                details={
                    "filename": document.original_filename,
                    "scheduled": scheduled,
                    "product_count": document.validation_summary.get(
                        "product_count", 0
                    ),
                },
            )
        )
