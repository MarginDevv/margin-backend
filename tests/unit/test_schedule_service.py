"""Unit tests for due_business_day — the per-restaurant report scheduler."""

from __future__ import annotations

import os
from datetime import datetime

os.environ.setdefault("APP_SECRET_KEY", "x" * 32)
os.environ.setdefault("JWT_SECRET_KEY", "y" * 32)


def test_returns_none_when_hours_missing() -> None:
    from app.services.analytics.schedule_service import due_business_day

    assert (
        due_business_day(datetime(2026, 6, 2, 0, 0), None, delay_minutes=60, step_minutes=15)
        is None
    )
    assert (
        due_business_day(datetime(2026, 6, 2, 0, 0), {}, delay_minutes=60, step_minutes=15) is None
    )


def test_same_day_close_within_window() -> None:
    """Restaurant closes Mon 23:00; delay 60m → trigger at Mon 00:00 (Tue)."""
    from app.services.analytics.schedule_service import due_business_day

    hours = {"mon": {"open": "10:00", "close": "23:00"}}
    # 2026-06-01 is a Monday. Now is Tue 00:05 — within the 15-min window
    # after the trigger moment 00:00.
    now = datetime(2026, 6, 2, 0, 5)
    result = due_business_day(now, hours, delay_minutes=60, step_minutes=15)
    assert result is not None
    assert result.isoformat() == "2026-06-01"


def test_trigger_outside_window_returns_none() -> None:
    from app.services.analytics.schedule_service import due_business_day

    hours = {"mon": {"open": "10:00", "close": "23:00"}}
    # Now is Tue 02:00 — well past the trigger; not in current 15-min window.
    now = datetime(2026, 6, 2, 2, 0)
    assert due_business_day(now, hours, delay_minutes=60, step_minutes=15) is None


def test_close_after_midnight_belongs_to_previous_business_day() -> None:
    """Restaurant works Mon 18:00 → Tue 02:00. Business day = Monday.
    Trigger: 02:00 + 60m = 03:00 Tuesday. So at Tue 03:10 we should fire for Mon.
    """
    from app.services.analytics.schedule_service import due_business_day

    hours = {"mon": {"open": "18:00", "close": "02:00"}}
    now = datetime(2026, 6, 2, 3, 10)  # Tuesday morning
    result = due_business_day(now, hours, delay_minutes=60, step_minutes=15)
    assert result is not None
    assert result.isoformat() == "2026-06-01"  # Monday


def test_closed_day_skipped() -> None:
    """If the weekday isn't in working_hours, no trigger."""
    from app.services.analytics.schedule_service import due_business_day

    hours = {"tue": {"open": "10:00", "close": "23:00"}}  # but candidate is Monday
    now = datetime(2026, 6, 2, 0, 5)  # Tue 00:05; candidate days = Tue, Mon, Sun
    # Tuesday's close hasn't happened yet (it's 00:05). Mon isn't in hours.
    assert due_business_day(now, hours, delay_minutes=60, step_minutes=15) is None


def test_custom_delay() -> None:
    from app.services.analytics.schedule_service import due_business_day

    hours = {"mon": {"open": "10:00", "close": "23:00"}}
    # Delay 30m → trigger at Mon 23:30. Now = 23:35.
    now = datetime(2026, 6, 1, 23, 35)
    result = due_business_day(now, hours, delay_minutes=30, step_minutes=15)
    assert result is not None
    assert result.isoformat() == "2026-06-01"
