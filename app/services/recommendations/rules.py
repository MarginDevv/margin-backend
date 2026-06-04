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
    "Понедельник",
    "Вторник",
    "Среда",
    "Четверг",
    "Пятница",
    "Суббота",
    "Воскресенье",
]

# ---- Tunable thresholds (kept here so a future config layer can override) ----

# cost_reduce: food-cost share at or above this is flagged on bestsellers.
COST_SHARE_THRESHOLD = Decimal("0.45")
COST_SHARE_TARGET = Decimal("0.40")  # used to estimate the saving uplift.

# price_up: how far below average margin a bestseller must be (in percentage points).
PRICE_UP_MARGIN_GAP = Decimal("5")
PRICE_UP_UPLIFT_RATE = Decimal("0.05")  # ~5% extra revenue on the line.

# price_down: how far above average margin a slow-seller must be.
PRICE_DOWN_MARGIN_GAP = Decimal("10")

# promote_dish: uplift estimate = profit * this share (extra demand from promotion).
PROMOTE_UPLIFT_RATE = Decimal("0.15")

# bundle_candidate: high-margin middle-tier dish gets bundled with bestsellers.
BUNDLE_MARGIN_GAP = Decimal("5")
BUNDLE_UPLIFT_RATE = Decimal("0.10")

# slow_seller: drop estimated_uplift is "profit at risk" if we remove it.
SLOW_SELLER_RISK_SHARE = Decimal("0.5")

# weekday_draft: uplift assumes 10% of best-worst delta is recoverable.
WEEKDAY_UPLIFT_RATE = Decimal("0.10")

# weekday_dead_zone: any weekday with profit <= best.profit * this is "dead".
WEEKDAY_DEAD_RATIO = Decimal("0.20")

# menu_concentration: when top-N dishes earn this share of total revenue.
CONCENTRATION_TOP_N = 5
CONCENTRATION_THRESHOLD = Decimal("0.70")

# Per-dish output cap inside ``dish_drafts``.
MAX_DRAFTS_PER_DISH = 2

# Default confidence scores per rule.
CONFIDENCE_REMOVE = 80
CONFIDENCE_COST_REDUCE = 75
CONFIDENCE_PRICE_UP = 70
CONFIDENCE_PRICE_DOWN = 60
CONFIDENCE_PROMOTE = 80
CONFIDENCE_BUNDLE = 65
CONFIDENCE_ZERO_MOVEMENT = 85
CONFIDENCE_SLOW_SELLER = 55
CONFIDENCE_WEEKDAY = 75
CONFIDENCE_WEEKDAY_DEAD = 70
CONFIDENCE_CONCENTRATION = 70


# Numeric ranking for the four priority levels — used to sort drafts.
_PRIORITY_RANK: dict[RecommendationPriority, int] = {
    RecommendationPriority.LOW: 0,
    RecommendationPriority.MEDIUM: 1,
    RecommendationPriority.HIGH: 2,
    RecommendationPriority.CRITICAL: 3,
}


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
        confidence=CONFIDENCE_REMOVE,
        estimated_uplift=-dish.profit,
        payload={"dish": dish.model_dump(mode="json")},
    )


def cost_reduce(dish: DishPerformance, q: DishQuantiles) -> Draft | None:
    """High-volume dish with food-cost share above 45%."""
    if not (dish.revenue > 0 and dish.quantity >= q.q3_qty):
        return None
    cost_share = dish.cost / dish.revenue
    if cost_share <= COST_SHARE_THRESHOLD:
        return None
    return Draft(
        type=RecommendationType.COST_REDUCE,
        title=f"Снизить себестоимость: {dish.name}",
        description=(
            f"Food-cost share по «{dish.name}» = {cost_share * 100:.1f}% "
            f"при объёме продаж {dish.quantity:.0f} шт. Это выше нормы "
            f"{COST_SHARE_THRESHOLD * 100:.0f}%."
        ),
        action="Пересогласовать закупочные цены ингредиентов или уменьшить порцию на 5–10%.",
        priority=RecommendationPriority.HIGH,
        category=RecommendationCategory.STOCK,
        effort=RecommendationEffort.MEDIUM,
        confidence=CONFIDENCE_COST_REDUCE,
        estimated_uplift=(cost_share - COST_SHARE_TARGET) * dish.revenue,
        payload={"dish": dish.model_dump(mode="json"), "cost_share": float(cost_share)},
    )


def price_up(dish: DishPerformance, q: DishQuantiles) -> Draft | None:
    """Strong demand, margin notably below average."""
    if not (dish.quantity >= q.q3_qty and dish.margin_percent < q.avg_margin - PRICE_UP_MARGIN_GAP):
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
        confidence=CONFIDENCE_PRICE_UP,
        estimated_uplift=dish.revenue * PRICE_UP_UPLIFT_RATE,
        payload={"dish": dish.model_dump(mode="json"), "avg_margin": float(q.avg_margin)},
    )


def price_down(dish: DishPerformance, q: DishQuantiles) -> Draft | None:
    """High-margin item that barely sells — price may be the blocker."""
    if not (
        dish.quantity <= q.q1_qty and dish.margin_percent > q.avg_margin + PRICE_DOWN_MARGIN_GAP
    ):
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
        confidence=CONFIDENCE_PRICE_DOWN,
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
        confidence=CONFIDENCE_PROMOTE,
        estimated_uplift=dish.profit * PROMOTE_UPLIFT_RATE,
        payload={"dish": dish.model_dump(mode="json")},
    )


# ---- New per-dish rules ----


def zero_movement(dish: DishPerformance) -> Draft | None:
    """Item present in the menu but with no sales over the 4-week window.

    Different from ``remove_dish``: that one fires on dishes that *do* sell
    but lose money. This one fires on dishes that don't move at all — either
    visibility issue or a forgotten position.
    """
    if dish.quantity > 0:
        return None
    return Draft(
        type=RecommendationType.REMOVE_DISH,
        title=f"Не продаётся: {dish.name}",
        description=(
            f"«{dish.name}» не было продано ни разу за последние 4 недели. "
            "Либо позиция забыта в меню, либо незаметна гостям."
        ),
        action="Удалить из меню или вынести в спецпредложение и проверить за 2 недели.",
        priority=RecommendationPriority.MEDIUM,
        category=RecommendationCategory.MENU,
        effort=RecommendationEffort.LOW,
        confidence=CONFIDENCE_ZERO_MOVEMENT,
        estimated_uplift=None,
        payload={"dish": dish.model_dump(mode="json")},
    )


def slow_seller(dish: DishPerformance, q: DishQuantiles) -> Draft | None:
    """Low-volume but still profitable dish that doesn't qualify for ``price_down``.

    Disjoint from ``price_down`` by margin condition: this rule fires only
    when margin is close to or below average + ``PRICE_DOWN_MARGIN_GAP``
    (so price reduction wouldn't help — the dish just doesn't resonate).
    """
    if dish.quantity <= 0:
        return None  # leave it to ``zero_movement``.
    if not (dish.quantity <= q.q1_qty and dish.profit > Decimal("0")):
        return None
    # Exclude items that would trigger ``price_down`` — they have a different fix.
    if dish.margin_percent > q.avg_margin + PRICE_DOWN_MARGIN_GAP:
        return None
    return Draft(
        type=RecommendationType.REMOVE_DISH,
        title=f"Кандидат на ротацию: {dish.name}",
        description=(
            f"«{dish.name}» прибыльно ({dish.profit:.2f}), но продаётся редко "
            f"({dish.quantity:.0f} шт. за 4 недели) и не имеет высокой маржи. "
            "Кандидат на замену в меню."
        ),
        action="Заменить на сезонную позицию или объединить с похожим блюдом.",
        priority=RecommendationPriority.LOW,
        category=RecommendationCategory.MENU,
        effort=RecommendationEffort.LOW,
        confidence=CONFIDENCE_SLOW_SELLER,
        estimated_uplift=-(dish.profit * SLOW_SELLER_RISK_SHARE),
        payload={"dish": dish.model_dump(mode="json")},
    )


def bundle_candidate(dish: DishPerformance, q: DishQuantiles) -> Draft | None:
    """Middle-of-the-pack dish with above-average margin — easy upsell win.

    These are the dishes that don't qualify as bestsellers (so ``promote_dish``
    doesn't fire) but still have good unit economics; bundling them with a
    bestseller lifts attach rate without sacrificing margin.
    """
    if dish.quantity <= q.q1_qty or dish.quantity >= q.q3_qty:
        return None
    if dish.margin_percent < q.avg_margin + BUNDLE_MARGIN_GAP:
        return None
    if dish.revenue <= Decimal("0"):
        return None
    return Draft(
        type=RecommendationType.PROMOTE_DISH,
        title=f"Включить в комбо: {dish.name}",
        description=(
            f"«{dish.name}» имеет маржу {dish.margin_percent:.1f}% "
            f"(выше средней {q.avg_margin:.1f}%) и стабильный, но не топовый спрос "
            f"({dish.quantity:.0f} шт.). Подходит для bundle с бестселлером."
        ),
        action="Сформировать комбо с топ-блюдом со скидкой 5–10% и протестировать 2 недели.",
        priority=RecommendationPriority.LOW,
        category=RecommendationCategory.PROMOTION,
        effort=RecommendationEffort.MEDIUM,
        confidence=CONFIDENCE_BUNDLE,
        estimated_uplift=dish.revenue * BUNDLE_UPLIFT_RATE,
        payload={"dish": dish.model_dump(mode="json"), "avg_margin": float(q.avg_margin)},
    )


# ---------- Per-dish orchestrator ----------


def _dedupe_per_dish(per_dish: dict[Any, list[Draft]]) -> list[Draft]:
    """Apply per-dish dedup + cap rules:

    - If both ``PROMOTE_DISH`` and ``PRICE_UP`` fired on the same dish, keep
      only ``PROMOTE_DISH`` (positive framing wins over a riskier price hike).
    - Keep at most ``MAX_DRAFTS_PER_DISH`` per dish, ranked by
      ``(priority, estimated_uplift)`` desc.
    """
    out: list[Draft] = []
    for drafts in per_dish.values():
        types = {d.type for d in drafts}
        if RecommendationType.PROMOTE_DISH in types and RecommendationType.PRICE_UP in types:
            drafts = [d for d in drafts if d.type is not RecommendationType.PRICE_UP]
        drafts.sort(key=_draft_sort_key, reverse=True)
        out.extend(drafts[:MAX_DRAFTS_PER_DISH])
    return out


def _draft_sort_key(d: Draft) -> tuple[int, Decimal]:
    return (
        _PRIORITY_RANK[d.priority],
        d.estimated_uplift if d.estimated_uplift is not None else Decimal("0"),
    )


def dish_drafts(dishes: list[DishPerformance]) -> list[Draft]:
    """Run every per-dish rule across the given dish list.

    Order of work per dish:

    1. ``zero_movement`` — dishes that never sold; nothing else makes sense.
    2. ``remove_dish``   — loss-makers; terminal per dish (no further suggestions).
    3. The four quantile rules (``cost_reduce``, ``price_up``, ``price_down``,
       ``promote_dish``), plus ``slow_seller`` and ``bundle_candidate``.

    After collecting candidates per dish we dedupe conflicting suggestions
    (``PROMOTE_DISH`` wins over ``PRICE_UP``) and cap to two drafts per dish
    so the daily feed doesn't get spammy. The final list is sorted by
    ``(priority, estimated_uplift)`` descending.
    """
    if not dishes:
        return []
    q = compute_dish_quantiles(dishes)

    per_dish: dict[Any, list[Draft]] = {}

    def _push(key: Any, draft: Draft | None) -> None:
        if draft is not None:
            per_dish.setdefault(key, []).append(draft)

    for dish in dishes:
        key = dish.menu_item_id or dish.name

        # 1. Never sold — handle and skip the rest.
        if (zm := zero_movement(dish)) is not None:
            _push(key, zm)
            continue

        # 2. Loss-maker — terminal.
        if (rm := remove_dish(dish)) is not None:
            _push(key, rm)
            continue

        # 3. Quantile-driven rules (only if we have enough data).
        if q is not None:
            _push(key, cost_reduce(dish, q))
            _push(key, price_up(dish, q))
            _push(key, price_down(dish, q))
            _push(key, promote_dish(dish, q))
            _push(key, slow_seller(dish, q))
            _push(key, bundle_candidate(dish, q))

    drafts = _dedupe_per_dish(per_dish)
    drafts.sort(key=_draft_sort_key, reverse=True)
    return drafts


# ---------- Weekday rules ----------


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
        confidence=CONFIDENCE_WEEKDAY,
        estimated_uplift=delta * WEEKDAY_UPLIFT_RATE,
        payload={
            "best": best.model_dump(mode="json"),
            "worst": worst.model_dump(mode="json"),
        },
    )


def weekday_dead_zone(points: list[WeekdayPoint]) -> Draft | None:
    """Flag weekdays whose profit is dramatically below the best day.

    Different from ``weekday_draft``, which compares only best vs worst.
    This rule produces a single draft listing every "dead" day so the owner
    can consider reducing hours / running a recurring promo on those days.
    """
    if not points:
        return None
    best = max(points, key=lambda p: p.profit)
    if best.profit <= Decimal("0"):
        return None
    cutoff = best.profit * WEEKDAY_DEAD_RATIO
    dead = [p for p in points if p.weekday != best.weekday and p.profit <= cutoff]
    if not dead:
        return None
    dead_names = ", ".join(WEEKDAY_NAMES[p.weekday] for p in dead)
    return Draft(
        type=RecommendationType.DAY_OF_WEEK,
        title=f"Мёртвые дни: {dead_names}",
        description=(
            f"Прибыль в {dead_names} в среднем ниже {WEEKDAY_DEAD_RATIO * 100:.0f}% "
            f"от лучшего дня ({WEEKDAY_NAMES[best.weekday]}, {best.profit:.2f} ₽). "
            "Стоит пересмотреть график работы или маркетинговую активность."
        ),
        action=(
            "Рассмотреть сокращение часов, доставку только, либо регулярную " "акцию для этих дней."
        ),
        priority=RecommendationPriority.MEDIUM,
        category=RecommendationCategory.OPERATIONS,
        effort=RecommendationEffort.HIGH,
        confidence=CONFIDENCE_WEEKDAY_DEAD,
        estimated_uplift=None,
        payload={
            "dead": [p.model_dump(mode="json") for p in dead],
            "best": best.model_dump(mode="json"),
        },
    )


# ---------- Menu-level aggregating rules ----------


def menu_concentration(dishes: list[DishPerformance]) -> Draft | None:
    """Detect dangerous revenue concentration in the top few dishes.

    When the top ``CONCENTRATION_TOP_N`` items earn more than
    ``CONCENTRATION_THRESHOLD`` of total revenue, the rest of the menu is
    likely dead weight. Informational draft (no uplift estimate).
    """
    earning = [d for d in dishes if d.revenue > Decimal("0")]
    if len(earning) <= CONCENTRATION_TOP_N:
        return None
    total = sum((d.revenue for d in earning), Decimal("0"))
    if total <= Decimal("0"):
        return None
    top = sorted(earning, key=lambda d: d.revenue, reverse=True)[:CONCENTRATION_TOP_N]
    top_revenue = sum((d.revenue for d in top), Decimal("0"))
    share = top_revenue / total
    if share < CONCENTRATION_THRESHOLD:
        return None
    top_names = ", ".join(d.name for d in top)
    return Draft(
        type=RecommendationType.PROMOTE_DISH,
        title=f"Меню держится на {CONCENTRATION_TOP_N} блюдах",
        description=(
            f"Топ-{CONCENTRATION_TOP_N} ({top_names}) даёт {share * 100:.1f}% "
            f"всей выручки из {len(earning)} продающихся позиций. "
            "Остальная часть меню работает слабо."
        ),
        action=(
            "Сократить меню до 1.5–2x от топ-N, освободившееся внимание "
            "перенаправить на разработку новых позиций под лучшие категории."
        ),
        priority=RecommendationPriority.LOW,
        category=RecommendationCategory.MENU,
        effort=RecommendationEffort.HIGH,
        confidence=CONFIDENCE_CONCENTRATION,
        estimated_uplift=None,
        payload={
            "share": float(share),
            "top": [d.model_dump(mode="json") for d in top],
            "total_earning": len(earning),
        },
    )


__all__ = [
    "Draft",
    "DishQuantiles",
    "compute_dish_quantiles",
    # per-dish rules
    "remove_dish",
    "cost_reduce",
    "price_up",
    "price_down",
    "promote_dish",
    "zero_movement",
    "slow_seller",
    "bundle_candidate",
    # orchestrator
    "dish_drafts",
    # weekday rules
    "weekday_draft",
    "weekday_dead_zone",
    # menu-level rules
    "menu_concentration",
    "WEEKDAY_NAMES",
]
