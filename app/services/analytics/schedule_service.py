"""Per-restaurant schedule logic: when is the daily report due?

Working hours are stored as `{weekday_key: {"open": "HH:MM", "close": "HH:MM"}}`,
where weekday_key ∈ {mon, tue, wed, thu, fri, sat, sun}. A close earlier than the
open means the business day spans midnight (e.g., open 18:00, close 02:00).

The "business day" of a restaurant is the calendar date when its shift opened —
so a shift that closes at 02:00 Tuesday belongs to business day = Monday.

`due_business_day(now_local, hours, delay)` returns the business date whose
"close + delay" falls in the half-open interval (now - step, now], or None.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

WEEKDAY_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _parse_hm(value: str) -> time:
    hour, minute = value.split(":")
    return time(int(hour), int(minute))


def _close_datetime(business_day: date, hours_for_day: dict[str, Any]) -> datetime:
    """Compute the local close datetime for a given business day."""
    open_t = _parse_hm(hours_for_day["open"])
    close_t = _parse_hm(hours_for_day["close"])
    if close_t <= open_t:
        # Spans midnight: close belongs to the next calendar day.
        return datetime.combine(business_day + timedelta(days=1), close_t)
    return datetime.combine(business_day, close_t)


def due_business_day(
    now_local_naive: datetime,
    working_hours: dict[str, Any] | None,
    *,
    delay_minutes: int,
    step_minutes: int,
) -> date | None:
    """Return business_day whose close+delay just fired, else None.

    `now_local_naive` must be a naive datetime in restaurant-local timezone.
    `step_minutes` should be the cadence of the scheduler beat: any close+delay
    that fell into (now − step, now] triggers exactly once.
    """
    if not working_hours:
        return None

    window_end = now_local_naive
    window_start = now_local_naive - timedelta(minutes=step_minutes)

    # Check business days that could plausibly have a "close+delay" inside the
    # window: yesterday and the day before (close may span midnight).
    for offset in (0, 1, 2):
        candidate = (now_local_naive - timedelta(days=offset)).date()
        weekday_key = WEEKDAY_KEYS[candidate.weekday()]
        day_hours = working_hours.get(weekday_key)
        if not day_hours:
            continue
        close_dt = _close_datetime(candidate, day_hours)
        trigger_dt = close_dt + timedelta(minutes=delay_minutes)
        if window_start < trigger_dt <= window_end:
            return candidate
    return None
