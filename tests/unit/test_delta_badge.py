"""Render of week-over-week delta annotations in the Telegram digest."""
from __future__ import annotations

import os
from decimal import Decimal

os.environ.setdefault("APP_SECRET_KEY", "x" * 32)
os.environ.setdefault("JWT_SECRET_KEY", "y" * 32)


def test_positive_delta_shows_up_arrow() -> None:
    from app.services.telegram.formatter import _delta_badge

    assert _delta_badge(Decimal("12.3")) == " ↑+12.3%"


def test_negative_delta_shows_down_arrow_with_minus_sign() -> None:
    from app.services.telegram.formatter import _delta_badge

    assert _delta_badge(Decimal("-4.5")) == " ↓−4.5%"


def test_near_zero_delta_collapses_to_approx() -> None:
    from app.services.telegram.formatter import _delta_badge

    assert _delta_badge(Decimal("0.1")) == " (≈)"
    assert _delta_badge(Decimal("-0.4")) == " (≈)"


def test_none_delta_returns_empty() -> None:
    from app.services.telegram.formatter import _delta_badge

    assert _delta_badge(None) == ""


def test_static_delta_pct_math() -> None:
    from app.services.analytics.analytics_service import AnalyticsService

    # 110 vs 100 → +10%
    assert AnalyticsService._delta_pct(Decimal("110"), Decimal("100")) == Decimal("10")
    # 50 vs 100 → -50%
    assert AnalyticsService._delta_pct(Decimal("50"), Decimal("100")) == Decimal("-50")
    # No baseline → None
    assert AnalyticsService._delta_pct(Decimal("50"), Decimal("0")) is None
