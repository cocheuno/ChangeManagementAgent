"""Maintenance windows, freezes, and lead time. Policy code owns service freezes."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from cm_agents.data.import_time import EASTERN, UTC

Span = tuple[datetime, datetime]


def inside_maintenance(start: datetime, end: datetime, tier: int) -> bool:
    for span_start, span_end in _spans(tier, start - timedelta(days=2), end + timedelta(days=2)):
        if span_start <= start and end <= span_end:
            return True
    return False


def lead_time_met(now: datetime, start: datetime, business_days: int) -> bool:
    if business_days <= 0:
        return start >= now
    elapsed = _business_days_between(
        now.astimezone(EASTERN).date(), start.astimezone(EASTERN).date()
    )
    return elapsed >= business_days


def freeze_hit(
    service: str, start: datetime, end: datetime, freezes: list[dict[str, Any]]
) -> str | None:
    local_start = start.astimezone(EASTERN)
    local_end = end.astimezone(EASTERN)
    for freeze in freezes:
        services = freeze.get("services")
        if services != "all" and service not in services:
            continue
        for day in _days(local_start, local_end):
            if _freeze_covers(str(freeze["name"]), day):
                return str(freeze["name"])
    return None


def earliest_window(
    *,
    now: datetime,
    duration: timedelta,
    tier: int,
    service: str,
    lead_business_days: int,
    freezes: list[dict[str, Any]],
    occupied: list[Span],
    horizon_days: int = 120,
) -> Span | None:
    """Earliest maintenance span that meets lead time, skips freezes, and is free."""
    search_from = now.astimezone(UTC)
    horizon = search_from + timedelta(days=horizon_days)
    for span_start, span_end in _spans(tier, search_from, horizon):
        if span_end - span_start < duration:
            continue
        start = span_start
        end = start + duration
        if end > span_end:
            continue
        if start < search_from or not lead_time_met(now, start, lead_business_days):
            continue
        if freeze_hit(service, start, end, freezes):
            continue
        if any(
            _overlaps(start, end, taken_start, taken_end) for taken_start, taken_end in occupied
        ):
            continue
        return start, end
    return None


def deployment_blocked_by_policy(
    change_type: str, start: datetime, end: datetime, tier: int
) -> bool:
    """True only when policy refuses this approved window.

    A standard change must sit inside a maintenance span. A normal or emergency
    change may deploy an approved window that ServiceNow marks
    not_in_maintenance_window. The caller still requires the clock to fall
    inside the approved planned start and end.
    """
    if change_type != "standard":
        return False
    return not inside_maintenance(start, end, tier)


def blocks(
    *,
    now: datetime,
    start: datetime,
    end: datetime,
    change_type: str,
    tier: int,
    service: str,
    lead_business_days: int,
    freezes: list[dict[str, Any]],
    schedule_conflict: bool,
) -> list[str]:
    """Reasons a requested window cannot be kept. Normal may sit outside maintenance."""
    reasons: list[str] = []
    freeze = freeze_hit(service, start, end, freezes)
    if freeze:
        reasons.append(f"freeze {freeze}")
    if schedule_conflict:
        reasons.append("conflict")
    if not lead_time_met(now, start, lead_business_days):
        reasons.append("lead time")
    if change_type == "standard" and not inside_maintenance(start, end, tier):
        reasons.append("outside maintenance window")
    return reasons


def _spans(tier: int, start: datetime, end: datetime) -> list[Span]:
    local_start = start.astimezone(EASTERN).date()
    local_end = end.astimezone(EASTERN).date() + timedelta(days=1)
    spans: list[Span] = []
    day = local_start
    while day <= local_end:
        if tier == 1 and day.weekday() == 5:
            span_start = datetime(day.year, day.month, day.day, 22, 0, tzinfo=EASTERN)
            span_end = span_start + timedelta(hours=6)
            spans.append((span_start.astimezone(UTC), span_end.astimezone(UTC)))
        if tier != 1 and day.weekday() in {1, 3}:
            span_start = datetime(day.year, day.month, day.day, 20, 0, tzinfo=EASTERN)
            span_end = span_start + timedelta(hours=3)
            spans.append((span_start.astimezone(UTC), span_end.astimezone(UTC)))
        day += timedelta(days=1)
    return spans


def _days(start: datetime, end: datetime) -> list[datetime]:
    day = start.date()
    last = end.date()
    found = []
    while day <= last:
        found.append(datetime(day.year, day.month, day.day, tzinfo=EASTERN))
        day += timedelta(days=1)
    return found


def _freeze_covers(name: str, day: datetime) -> bool:
    if "Month-End" in name:
        return _month_end(day.date())
    if "Holiday" in name:
        return _holiday(day.date())
    return False


def _month_end(day: Any) -> bool:
    if day.weekday() >= 5:
        return False
    first = _first_business_day(day.year, day.month)
    if day == first:
        return True
    if day.month == 12:
        next_first = _first_business_day(day.year + 1, 1)
    else:
        next_first = _first_business_day(day.year, day.month + 1)
    return day in {_add_business_days(next_first, -1), _add_business_days(next_first, -2)}


def _holiday(day: Any) -> bool:
    if (day.month == 12 and day.day >= 20) or (day.month == 1 and day.day <= 2):
        return True
    thanksgiving = _nth_weekday(day.year, 11, 4, 3)
    cyber_monday = thanksgiving + timedelta(days=4)
    week_start = thanksgiving - timedelta(days=thanksgiving.weekday())
    return week_start <= day <= cyber_monday


def _first_business_day(year: int, month: int) -> Any:
    day = datetime(year, month, 1).date()
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day


def _add_business_days(day: Any, count: int) -> Any:
    step = 1 if count >= 0 else -1
    left = abs(count)
    cursor = day
    while left:
        cursor += timedelta(days=step)
        if cursor.weekday() < 5:
            left -= 1
    return cursor


def _business_days_between(today: Any, start_day: Any) -> int:
    if start_day <= today:
        return 0
    span = (start_day - today).days
    return sum(
        1 for offset in range(1, span + 1) if (today + timedelta(days=offset)).weekday() < 5
    )


def _nth_weekday(year: int, month: int, n: int, weekday: int) -> Any:
    day = datetime(year, month, 1).date()
    shift = (weekday - day.weekday()) % 7
    return day + timedelta(days=shift + 7 * (n - 1))


def _overlaps(start: datetime, end: datetime, other_start: datetime, other_end: datetime) -> bool:
    return start < other_end and other_start < end


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def policy_zone() -> ZoneInfo:
    return EASTERN
