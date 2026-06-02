"""Datetime helpers — timezone-aware, ISO weekday math."""
from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.core.config import settings


def app_tz() -> ZoneInfo:
    return ZoneInfo(settings.app_timezone)


def restaurant_tz(tz_name: str | None) -> ZoneInfo:
    return ZoneInfo(tz_name) if tz_name else app_tz()


def now_utc() -> datetime:
    return datetime.now(UTC)


def to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("Cannot convert naive datetime to UTC; specify a timezone first")
    return value.astimezone(UTC)


def day_bounds_local(day: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """Return (start_of_day_utc, end_of_day_utc) for the given local day."""
    start_local = datetime.combine(day, time.min, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


def week_bounds_local(any_day: date, tz: ZoneInfo) -> tuple[datetime, datetime, date, date]:
    """Return (start_utc, end_utc, monday_date, sunday_date) for the ISO week containing the day."""
    monday = any_day - timedelta(days=any_day.weekday())
    sunday = monday + timedelta(days=6)
    start_local = datetime.combine(monday, time.min, tzinfo=tz)
    end_local = datetime.combine(sunday + timedelta(days=1), time.min, tzinfo=tz)
    return start_local.astimezone(UTC), end_local.astimezone(UTC), monday, sunday


def iiko_dt(value: datetime) -> str:
    """Format datetime for iikoCloud API: 'YYYY-MM-DD HH:MM:SS.000'."""
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S.000")
