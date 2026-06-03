"""Unit tests for ``iiko_dt`` timezone handling.

Background: iikoCloud Transport API expects date filters in the restaurant's
local time (swagger: "Local for delivery terminal"). Earlier the helper always
formatted as UTC, producing wrong cross-day ranges for non-UTC restaurants.
"""
from __future__ import annotations

import os
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

os.environ.setdefault("APP_SECRET_KEY", "x" * 32)
os.environ.setdefault("JWT_SECRET_KEY", "y" * 32)


def test_iiko_dt_defaults_to_utc() -> None:
    from app.utils.datetime import iiko_dt

    dt = datetime(2026, 6, 3, 21, 30, 0, tzinfo=UTC)
    assert iiko_dt(dt) == "2026-06-03 21:30:00.000"


def test_iiko_dt_converts_to_restaurant_tz() -> None:
    from app.utils.datetime import iiko_dt

    # 21:30 UTC == 00:30 next day in Moscow (UTC+3)
    dt = datetime(2026, 6, 3, 21, 30, 0, tzinfo=UTC)
    assert iiko_dt(dt, tz=ZoneInfo("Europe/Moscow")) == "2026-06-04 00:30:00.000"


def test_iiko_dt_day_boundary_does_not_leak_into_next_day_in_utc() -> None:
    """A request for the last second of a Moscow day should land in that day,
    not the next one (regression: the old UTC-only formatter shifted it)."""
    from app.utils.datetime import iiko_dt

    moscow = ZoneInfo("Europe/Moscow")
    # 23:59:59 local Moscow time == 20:59:59 UTC same day.
    local_end_of_day = datetime(2026, 6, 3, 23, 59, 59, tzinfo=moscow)
    utc_value = local_end_of_day.astimezone(UTC)
    assert iiko_dt(utc_value, tz=moscow).startswith("2026-06-03")


def test_iiko_dt_normalises_naive_aware_mix() -> None:
    from app.utils.datetime import iiko_dt

    aware = datetime(2026, 1, 1, 9, 0, 0, tzinfo=UTC)
    # Hawaii is UTC-10 → 01.01 09:00 UTC == 31.12 23:00 local.
    assert iiko_dt(aware, tz=ZoneInfo("Pacific/Honolulu")).startswith("2025-12-31")
