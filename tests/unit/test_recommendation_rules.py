"""Unit tests for the pure recommendation rule functions."""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.models.recommendation import (
    RecommendationCategory,
    RecommendationEffort,
    RecommendationPriority,
    RecommendationType,
)
from app.schemas.analytics import DishPerformance, WeekdayPoint
from app.services.recommendations import rules


def _dish(
    *,
    name: str = "Dish",
    quantity: str = "10",
    revenue: str = "1000",
    cost: str = "300",
    profit: str | None = None,
    margin_percent: str | None = None,
) -> DishPerformance:
    rev = Decimal(revenue)
    c = Decimal(cost)
    p = Decimal(profit) if profit is not None else rev - c
    m = Decimal(margin_percent) if margin_percent is not None else (
        (p / rev * Decimal("100")) if rev else Decimal("0")
    )
    return DishPerformance(
        menu_item_id=uuid.uuid4(),
        name=name,
        category=None,
        quantity=Decimal(quantity),
        revenue=rev,
        cost=c,
        profit=p,
        margin_percent=m,
    )


def _q(q1: str = "1", q3: str = "10", avg_margin: str = "30") -> rules.DishQuantiles:
    return rules.DishQuantiles(
        q1_qty=Decimal(q1),
        q3_qty=Decimal(q3),
        avg_margin=Decimal(avg_margin),
    )


# ---------- compute_dish_quantiles ----------

def test_compute_quantiles_empty_returns_none() -> None:
    assert rules.compute_dish_quantiles([]) is None


def test_compute_quantiles_no_revenue_returns_none() -> None:
    dishes = [_dish(revenue="0", cost="0", profit="0", margin_percent="0")]
    assert rules.compute_dish_quantiles(dishes) is None


def test_compute_quantiles_yields_thresholds() -> None:
    dishes = [
        _dish(quantity=str(i), revenue="100", cost="50", margin_percent=str(20 + i))
        for i in range(1, 21)
    ]
    q = rules.compute_dish_quantiles(dishes)
    assert q is not None
    assert q.q1_qty == Decimal("6")   # index = int(20*0.25) = 5 → sorted[5] = 6
    assert q.q3_qty == Decimal("16")  # index = int(20*0.75) = 15 → sorted[15] = 16
    assert q.avg_margin > Decimal("0")


# ---------- remove_dish ----------

def test_remove_dish_triggers_on_zero_profit() -> None:
    dish = _dish(revenue="500", cost="500", profit="0", margin_percent="0")
    draft = rules.remove_dish(dish)
    assert draft is not None
    assert draft.type is RecommendationType.REMOVE_DISH
    assert draft.category is RecommendationCategory.MENU
    assert draft.effort is RecommendationEffort.LOW
    assert draft.priority is RecommendationPriority.HIGH


def test_remove_dish_skips_when_profitable() -> None:
    assert rules.remove_dish(_dish(revenue="1000", cost="300", profit="700")) is None


def test_remove_dish_skips_when_no_revenue() -> None:
    assert rules.remove_dish(_dish(revenue="0", cost="0", profit="0", margin_percent="0")) is None


# ---------- cost_reduce ----------

def test_cost_reduce_triggers_above_threshold() -> None:
    dish = _dish(quantity="50", revenue="1000", cost="500")  # cost_share = 0.50
    draft = rules.cost_reduce(dish, _q(q3="10"))
    assert draft is not None
    assert draft.category is RecommendationCategory.STOCK
    assert draft.effort is RecommendationEffort.MEDIUM
    assert draft.payload["cost_share"] == pytest.approx(0.5)


def test_cost_reduce_skips_below_threshold() -> None:
    dish = _dish(quantity="50", revenue="1000", cost="300")  # cost_share = 0.30
    assert rules.cost_reduce(dish, _q(q3="10")) is None


def test_cost_reduce_skips_low_volume() -> None:
    dish = _dish(quantity="3", revenue="1000", cost="600")
    assert rules.cost_reduce(dish, _q(q3="10")) is None


# ---------- price_up ----------

def test_price_up_triggers_for_low_margin_bestseller() -> None:
    dish = _dish(quantity="50", revenue="1000", margin_percent="20")
    draft = rules.price_up(dish, _q(q3="10", avg_margin="30"))
    assert draft is not None
    assert draft.category is RecommendationCategory.PRICING
    assert draft.estimated_uplift == Decimal("1000") * Decimal("0.05")


def test_price_up_skips_when_margin_close_to_average() -> None:
    dish = _dish(quantity="50", revenue="1000", margin_percent="28")
    assert rules.price_up(dish, _q(q3="10", avg_margin="30")) is None


# ---------- price_down ----------

def test_price_down_triggers_for_high_margin_low_demand() -> None:
    dish = _dish(quantity="1", revenue="100", margin_percent="50")
    draft = rules.price_down(dish, _q(q1="2", avg_margin="30"))
    assert draft is not None
    assert draft.category is RecommendationCategory.PRICING
    assert draft.priority is RecommendationPriority.LOW
    assert draft.estimated_uplift is None


def test_price_down_skips_for_high_demand() -> None:
    dish = _dish(quantity="20", revenue="2000", margin_percent="50")
    assert rules.price_down(dish, _q(q1="2", avg_margin="30")) is None


# ---------- promote_dish ----------

def test_promote_dish_triggers_for_high_volume_high_margin() -> None:
    dish = _dish(quantity="50", revenue="1000", margin_percent="40", profit="400")
    draft = rules.promote_dish(dish, _q(q3="10", avg_margin="30"))
    assert draft is not None
    assert draft.category is RecommendationCategory.PROMOTION
    assert draft.effort is RecommendationEffort.MEDIUM


def test_promote_dish_skips_when_unprofitable() -> None:
    dish = _dish(quantity="50", revenue="1000", profit="-50", margin_percent="40")
    assert rules.promote_dish(dish, _q(q3="10", avg_margin="30")) is None


# ---------- dish_drafts (orchestration) ----------

def test_dish_drafts_remove_is_terminal_per_dish() -> None:
    """A loss-making bestseller should produce only REMOVE_DISH, not PRICE_UP."""
    losers_and_winners = [
        _dish(name="Loss-bestseller", quantity="50", revenue="1000", cost="1200",
              profit="-200", margin_percent="-20"),
        # enough other dishes for quantiles to be meaningful
        *(_dish(name=f"Filler-{i}", quantity=str(i), revenue="100",
                cost="50", margin_percent="50") for i in range(1, 11)),
    ]
    drafts = rules.dish_drafts(losers_and_winners)
    loser_drafts = [d for d in drafts if "Loss-bestseller" in d.title]
    assert len(loser_drafts) == 1
    assert loser_drafts[0].type is RecommendationType.REMOVE_DISH


def test_dish_drafts_empty_input_returns_empty() -> None:
    assert rules.dish_drafts([]) == []


# ---------- weekday_draft ----------

def _wd(weekday: int, profit: str, revenue: str = "5000") -> WeekdayPoint:
    return WeekdayPoint(
        weekday=weekday,
        orders_count=10,
        revenue=Decimal(revenue),
        profit=Decimal(profit),
    )


def test_weekday_draft_triggers_when_best_beats_worst() -> None:
    draft = rules.weekday_draft(_wd(4, "1000"), _wd(1, "200"))
    assert draft is not None
    assert draft.type is RecommendationType.DAY_OF_WEEK
    assert draft.category is RecommendationCategory.PROMOTION
    assert draft.effort is RecommendationEffort.HIGH
    assert "Пятница" in draft.title  # weekday=4
    assert "Вторник" in draft.title  # weekday=1


def test_weekday_draft_returns_none_when_equal() -> None:
    assert rules.weekday_draft(_wd(0, "500"), _wd(1, "500")) is None
