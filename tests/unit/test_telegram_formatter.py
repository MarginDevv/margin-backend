"""Unit tests for HTML formatting of Telegram digests."""
from __future__ import annotations

import os
import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

os.environ.setdefault("APP_SECRET_KEY", "x" * 32)
os.environ.setdefault("JWT_SECRET_KEY", "y" * 32)


def _report(**overrides):
    base = dict(
        net_revenue=Decimal("125000"),
        profit=Decimal("47500"),
        margin_percent=Decimal("38.0"),
        orders_count=82,
        avg_check=Decimal("1524"),
        guests_count=150,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _rec(title: str, action: str, priority: str = "high", uplift: str | None = None):
    from app.models.recommendation import RecommendationPriority

    pmap = {
        "low": RecommendationPriority.LOW,
        "medium": RecommendationPriority.MEDIUM,
        "high": RecommendationPriority.HIGH,
        "critical": RecommendationPriority.CRITICAL,
    }
    return SimpleNamespace(
        title=title,
        action=action,
        priority=pmap[priority],
        estimated_uplift=Decimal(uplift) if uplift else None,
    )


def test_digest_contains_kpis_and_recs() -> None:
    from app.services.telegram.formatter import render_daily_digest

    text = render_daily_digest(
        restaurant_name="Кафе «Угол»",
        for_date=date(2026, 6, 1),
        report=_report(),
        top_recommendations=[
            _rec("Поднять цену: Пицца Маргарита", "Цена +6%", priority="high", uplift="2400"),
            _rec("Снизить себестоимость: Бургер", "Пересогласовать булку", priority="medium"),
        ],
        currency="₽",
        dashboard_url="https://app.margin.example/r/abc",
    )
    assert "Margin · отчёт" in text
    assert "Кафе «Угол»" in text
    assert "01.06.2026" in text
    assert "Прибыль" in text
    assert "47 500 ₽" in text or "47 500 ₽" in text or "47,500" in text
    assert "38.0%" in text
    assert "Топ рекомендации" in text
    assert "Пицца Маргарита" in text
    assert "Бургер" in text
    assert "https://app.margin.example/r/abc" in text


def test_digest_html_escapes_user_text() -> None:
    from app.services.telegram.formatter import render_daily_digest

    text = render_daily_digest(
        restaurant_name="<script>alert(1)</script>",
        for_date=date(2026, 6, 1),
        report=_report(),
        top_recommendations=[_rec("Bad <b>html</b>", "do < this")],
    )
    assert "<script>" not in text
    assert "&lt;script&gt;" in text
    assert "&lt;b&gt;html&lt;/b&gt;" in text


def test_help_text_has_commands() -> None:
    from app.services.telegram.formatter import render_help

    text = render_help()
    assert "/today" in text
    assert "/yesterday" in text
    assert "/unlink" in text


def test_link_success_handles_no_name() -> None:
    from app.services.telegram.formatter import render_link_success

    text = render_link_success(None)
    assert "друг" in text
    assert "Готово" in text


def test_priority_icons_present() -> None:
    from app.services.telegram.formatter import PRIORITY_LABEL
    from app.models.recommendation import RecommendationPriority

    assert PRIORITY_LABEL[RecommendationPriority.CRITICAL] == "🔴"
    assert PRIORITY_LABEL[RecommendationPriority.HIGH] == "🔸"
