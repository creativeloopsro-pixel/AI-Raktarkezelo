from datetime import UTC, datetime, time
from decimal import Decimal
from io import BytesIO

from openpyxl import Workbook

from app.vrp.parser import VrpSalesReportParser
from app.vrp.scheduling import calculate_next_run


def test_parser_reads_csv_and_ignores_financial_columns() -> None:
    payload = (
        "Kód tovaru;Označenie tovaru;Množstvo;Jednotka;Cena;DPH\n"
        "TEST-001;Teszt termék;2,5;piece;99,90;20\n"
    ).encode()

    report = VrpSalesReportParser().parse(payload, "predaj.csv")

    assert len(report.items) == 1
    assert report.items[0].external_product_id == "TEST-001"
    assert report.items[0].quantity == Decimal("2.500")
    assert report.items[0].unit == "piece"
    assert report.errors == []


def test_parser_reads_xlsx() -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["PLU", "Názov položky", "Predané množstvo", "Merná jednotka"])
    sheet.append(["TEST-001", "Teszt termék", 3, "piece"])
    output = BytesIO()
    workbook.save(output)

    report = VrpSalesReportParser().parse(output.getvalue(), "predaj.xlsx")

    assert report.items[0].quantity == Decimal("3.000")
    assert report.items[0].external_name == "Teszt termék"


def test_parser_canonical_hash_is_order_independent() -> None:
    first = (
        "product code;product name;quantity\n"
        "A;Alma;1\n"
        "B;Banán;2\n"
    ).encode()
    second = (
        "product code;product name;quantity\n"
        "B;Banán;2\n"
        "A;Alma;1\n"
    ).encode()

    parser = VrpSalesReportParser()

    assert (
        parser.parse(first, "first.csv").canonical_items_hash
        == parser.parse(second, "second.csv").canonical_items_hash
    )


def test_parser_keeps_valid_rows_and_reports_invalid_rows() -> None:
    payload = (
        "product code;product name;quantity\n"
        "TEST-001;Teszt termék;2\n"
        "BROKEN;Hibás mennyiség;nem-szám\n"
    ).encode()

    report = VrpSalesReportParser().parse(payload, "mixed.csv")

    assert len(report.items) == 1
    assert len(report.errors) == 1
    assert report.errors[0].error_code == "INVALID_QUANTITY"
    assert report.errors[0].line_number == 3


def test_daily_weekly_monthly_and_manual_schedule() -> None:
    reference = datetime(2026, 7, 25, 12, 0, tzinfo=UTC)

    daily = calculate_next_run(
        frequency="DAILY",
        processing_time=time(23, 55),
        timezone_name="Europe/Bratislava",
        weekly_day="SUNDAY",
        monthly_rule="LAST_DAY",
        after=reference,
    )
    weekly = calculate_next_run(
        frequency="WEEKLY",
        processing_time=time(23, 55),
        timezone_name="Europe/Bratislava",
        weekly_day="SUNDAY",
        monthly_rule="LAST_DAY",
        after=reference,
    )
    monthly = calculate_next_run(
        frequency="MONTHLY",
        processing_time=time(23, 55),
        timezone_name="Europe/Bratislava",
        weekly_day="SUNDAY",
        monthly_rule="LAST_DAY",
        after=reference,
    )
    manual = calculate_next_run(
        frequency="MANUAL",
        processing_time=time(23, 55),
        timezone_name="Europe/Bratislava",
        weekly_day="SUNDAY",
        monthly_rule="LAST_DAY",
        after=reference,
    )

    assert daily == datetime(2026, 7, 25, 21, 55, tzinfo=UTC)
    assert weekly == datetime(2026, 7, 26, 21, 55, tzinfo=UTC)
    assert monthly == datetime(2026, 7, 31, 21, 55, tzinfo=UTC)
    assert manual is None
