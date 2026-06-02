"""Heuristic rule functions for the recommendation engine.

Each rule is a pure function that takes already-fetched analytics objects
(``DishPerformance`` / ``WeekdayPoint``) and returns zero or more ``Draft``
recommendations. No DB, no LLM, no I/O — easy to unit-test.

Adding a rule:

1. Write a function that takes pre-computed stats and returns ``list[Draft]``.
2. Tag each ``Draft`` with the correct ``RecommendationType`` /
   ``RecommendationCategory`` / ``RecommendationEffort`` /
   ``RecommendationPriority``.
3. Wire it into ``RecommendationEngine`` (call site in ``engine.py``).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.models.recommendation import (
    RecommendationCategory,
    RecommendationEffort,
    RecommendationPriority,
    RecommendationType,
)
from app.schemas.analytics import DishPerformance, WeekdayPoint

WEEKDAY_NAMES = [
    "Понедельник", "Вторник", "Среда", "Четверг",
    "Пятница", "Суббота", "Воскресенье",
]


@dataclass
class Draft:
    type: RecommendationType
    title: str
    description: str
    action: str
    priority: RecommendationPriority
    category: RecommendationCategory
    effort: RecommendationEffort
    confidence: int
    estimated_uplift: Decimal | None
    payload: dict[str, Any]


@dataclass(frozen=True)
class DishQuantiles:
    q1_qty: Decimal
    q3_qty: Decimal
    avg_margin: Decimal


def compute_dish_quantiles(dishes: list[DishPerformance]) -> DishQuantiles | None:
    """Return Q1/Q3 by quantity and mean margin across dishes with revenue.

    Returns ``None`` if there isn't enough data to compute meaningful thresholds.
    """
    qtys = sorted(d.quantity for d in dishes)
    margins = [d.margin_percent for d in dishes if d.revenue > 0]
    if not qtys or not margins:
        return None
    return DishQuantiles(
        q1_qty=qtys[int(len(qtys) * 0.25)],
        q3_qty=qtys[int(len(qtys) * 0.75)],
        avg_margin=sum(margins, Decimal("0")) / Decimal(len(margins)),
    )


# ---------- Per-dish rules ----------

def remove_dish(dish: DishPerformance) -> Draft | None:
    """Chronic loss-maker: had sales but profit <= 0."""
    if not (dish.revenue > 0 and dish.profit <= Decimal("0")):
        return None
    return Draft(
        type=RecommendationType.REMOVE_DISH,
        title=f"Убрать из меню: {dish.name}",
        description=(
            f"За последние 4 недели «{dish.name}» дало выручку {dish.revenue:.2f} "
            f"и прибыль {dish.profit:.2f}. Это убыточная позиция."
        ),
        action="Убрать из меню или пересмотреть рецептуру/цену.",
        priority=RecommendationPriority.HIGH,
        category=RecommendationCategory.MENU,
        effort=RecommendationEffort.LOW,
        confidence=80,
        estimated_uplift=-dish.profit,
        payload={"dish": dish.model_dump(mode="json")},
    )


def cost_reduce(dish: DishPerformance, q: DishQuantiles) -> Draft | None:
    """High-volume dish with food-cost share above 45%."""
    if not (dish.revenue > 0 and dish.quantity >= q.q3_qty):
        return None
    cost_share = dish.cost / dish.revenue
    if cost_share <= Decimal("0.45"):
        return None
    return Draft(
        type=RecommendationType.COST_REDUCE,
        title=f"Снизить себестоимость: {dish.name}",
        description=(
            f"Food-cost share по «{dish.name}» = {cost_share * 100:.1f}% "
            f"при объёме продаж {dish.quantity:.0f} шт. Это выше нормы 45%."
        ),
        action="Пересогласовать закупочные цены ингредиентов или уменьшить порцию на 5–10%.",
        priority=RecommendationPriority.HIGH,
        category=RecommendationCategory.STOCK,
        effort=RecommendationEffort.MEDIUM,
        confidence=75,
        estimated_uplift=(cost_share - Decimal("0.40")) * dish.revenue,
        payload={"dish": dish.model_dump(mode="json"), "cost_share": float(cost_share)},
    )


def price_up(dish: DishPerformance, q: DishQuantiles) -> Draft | None:
    """Strong demand, margin notably below average."""
    if not (dish.quantity >= q.q3_qty and dish.margin_percent < q.avg_margin - Decimal("5")):
        return None
    return Draft(
        type=RecommendationType.PRICE_UP,
        title=f"Поднять цену: {dish.name}",
        description=(
            f"«{dish.name}» хорошо покупают ({dish.quantity:.0f} шт.), "
            f"но маржа {dish.margin_percent:.1f}% ниже средней по меню "
            f"({q.avg_margin:.1f}%)."
        ),
        action="Повысить цену на 5–7% — спрос вероятно сохранится.",
        priority=RecommendationPriority.MEDIUM,
        category=RecommendationCategory.PRICING,
        effort=RecommendationEffort.LOW,
        confidence=70,
        estimated_uplift=dish.revenue * Decimal("0.05"),
        payload={"dish": dish.model_dump(mode="json"), "avg_margin": float(q.avg_margin)},
    )


def price_down(dish: DishPerformance, q: DishQuantiles) -> Draft | None:
    """High-margin item that barely sells — price may be the blocker."""
    if not (dish.quantity <= q.q1_qty and dish.margin_percent > q.avg_margin + Decimal("10")):
        return None
    return Draft(
        type=RecommendationType.PRICE_DOWN,
        title=f"Снизить цену или акция: {dish.name}",
        description=(
            f"«{dish.name}» имеет высокую маржу {dish.margin_percent:.1f}%, "
            f"но продаётся редко ({dish.quantity:.0f} шт.). Цена может отпугивать."
        ),
        action="Снизить цену на 8–10% или запустить таргетированную акцию на 2 недели.",
        priority=RecommendationPriority.LOW,
        category=RecommendationCategory.PRICING,
        effort=RecommendationEffort.LOW,
        confidence=60,
        estimated_uplift=None,
        payload={"dish": dish.model_dump(mode="json")},
    )


def promote_dish(dish: DishPerformance, q: DishQuantiles) -> Draft | None:
    """Top profit contributor — push visibility."""
    if not (
        dish.profit > Decimal("0")
        and dish.quantity >= q.q3_qty
        and dish.margin_percent >= q.avg_margin
    ):
        return None
    return Draft(
        type=RecommendationType.PROMOTE_DISH,
        title=f"Продвигать: {dish.name}",
        description=(
            f"«{dish.name}» — топ по прибыли (+{dish.profit:.2f}) "
            f"и маржа {dish.margin_percent:.1f}%."
        ),
        action="Поднять в меню, добавить в spotlight, обучить персонал предлагать.",
        priority=RecommendationPriority.MEDIUM,
        category=RecommendationCategory.PROMOTION,
        effort=RecommendationEffort.MEDIUM,
        confidence=80,
        estimated_uplift=dish.profit * Decimal("0.15"),
        payload={"dish": dish.model_dump(mode="json")},
    )


# ---------- Aggregating helpers ----------

def dish_drafts(dishes: list[DishPerformance]) -> list[Draft]:
    """Run every per-dish rule across the given dish list."""
    q = compute_dish_quantiles(dishes)
    if q is None:
        return []
    rules = (remove_dish,)
    quantile_rules = (cost_reduce, price_up, price_down, promote_dish)

    drafts: list[Draft] = []
    for dish in dishes:
        for rule in rules:
            if (d := rule(dish)) is not None:
                drafts.append(d)
                break  # REMOVE_DISH is terminal — skip other suggestions for this dish.
        else:
            for qrule in quantile_rules:
                if (d := qrule(dish, q)) is not None:
                    drafts.append(d)
    return drafts


def weekday_draft(best: WeekdayPoint, worst: WeekdayPoint) -> Draft | None:
    """Recommend reinforcing the best weekday and addressing the worst."""
    if best.profit <= worst.profit:
        return None
    delta = best.profit - worst.profit
    return Draft(
        type=RecommendationType.DAY_OF_WEEK,
        title=(
            f"{WEEKDAY_NAMES[best.weekday]} — лучший день, "
            f"{WEEKDAY_NAMES[worst.weekday]} — худший"
        ),
        description=(
            f"За последние 4 недели прибыль в {WEEKDAY_NAMES[best.weekday]} "
            f"в среднем выше на {delta:.2f} ₽, чем в {WEEKDAY_NAMES[worst.weekday]}."
        ),
        action=(
            f"Усилить смену и маркетинг в {WEEKDAY_NAMES[best.weekday]}; "
            f"запустить акцию или мероприятие в {WEEKDAY_NAMES[worst.weekday]}."
        ),
        priority=RecommendationPriority.MEDIUM,
        category=RecommendationCategory.PROMOTION,
        effort=RecommendationEffort.HIGH,
        confidence=75,
        estimated_uplift=delta * Decimal("0.10"),
        payload={
            "best": best.model_dump(mode="json"),
            "worst": worst.model_dump(mode="json"),
        },
    )


__all__ = [
    "Draft",
    "DishQuantiles",
    "compute_dish_quantiles",
    "remove_dish",
    "cost_reduce",
    "price_up",
    "price_down",
    "promote_dish",
    "dish_drafts",
    "weekday_draft",
    "WEEKDAY_NAMES",
]
