from __future__ import annotations

import calendar
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

WEEKDAYS = {
    "MONDAY": 0,
    "TUESDAY": 1,
    "WEDNESDAY": 2,
    "THURSDAY": 3,
    "FRIDAY": 4,
    "SATURDAY": 5,
    "SUNDAY": 6,
}


def calculate_next_run(
    *,
    frequency: str,
    processing_time: time,
    timezone_name: str,
    weekly_day: str,
    monthly_rule: str,
    after: datetime | None = None,
) -> datetime | None:
    if frequency == "MANUAL":
        return None
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("Ismeretlen időzóna.") from exc
    reference = (after or datetime.now(UTC)).astimezone(zone)

    if frequency == "DAILY":
        local_run = datetime.combine(reference.date(), processing_time, zone)
        if local_run <= reference:
            local_run += timedelta(days=1)
        return local_run.astimezone(UTC)

    if frequency == "WEEKLY":
        target_weekday = WEEKDAYS.get(weekly_day)
        if target_weekday is None:
            raise ValueError("Érvénytelen heti nap.")
        days = (target_weekday - reference.weekday()) % 7
        local_run = datetime.combine(
            reference.date() + timedelta(days=days),
            processing_time,
            zone,
        )
        if local_run <= reference:
            local_run += timedelta(days=7)
        return local_run.astimezone(UTC)

    if frequency == "MONTHLY":
        year, month = reference.year, reference.month
        for _ in range(2):
            day = _monthly_day(year, month, monthly_rule)
            local_run = datetime.combine(date(year, month, day), processing_time, zone)
            if local_run > reference:
                return local_run.astimezone(UTC)
            if month == 12:
                year += 1
                month = 1
            else:
                month += 1
        raise ValueError("A havi futás nem számítható ki.")

    raise ValueError("Érvénytelen VRP ütemezési gyakoriság.")


def _monthly_day(year: int, month: int, monthly_rule: str) -> int:
    last_day = calendar.monthrange(year, month)[1]
    if monthly_rule == "LAST_DAY":
        return last_day
    try:
        requested = int(monthly_rule)
    except ValueError as exc:
        raise ValueError("A havi szabály LAST_DAY vagy 1 és 28 közötti nap lehet.") from exc
    if requested < 1 or requested > 28:
        raise ValueError("A havi nap 1 és 28 közé essen.")
    return min(requested, last_day)
