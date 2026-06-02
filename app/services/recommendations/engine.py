"""Heuristic recommendation engine.

Generates concrete, actionable, profit-oriented recommendations from order-level
analytics — no LLM required for v1. The engine is purposely deterministic and
explainable: every recommendation carries a `payload` with the input figures
so an owner can audit why we suggested it.

Rules implemented:

1. PROMOTE_DISH — high-margin dish in top quartile by profit. Bump visibility.
2. PRICE_UP    — dish with strong demand (qty in top 25%) and below-average margin %.
3. PRICE_DOWN  — dish with high margin % but very low demand (bottom quartile by qty).
4. REMOVE_DISH — items with negative or near-zero profit in the period.
5. COST_REDUCE — high-volume dishes whose food_cost share > 45%.
6. DAY_OF_WEEK — recommend reinforcing best day and addressing worst day.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.models.recommendation import (
    Recommendation,
    RecommendationPriority,
    RecommendationStatus,
    RecommendationType,
)
from app.repositories.recommendation_repo import RecommendationRepository
from app.repositories.restaurant_repo import RestaurantRepository
from app.services.analytics.analytics_service import AnalyticsService

logger = get_logger("recommendations.engine")

WEEKDAY_NAMES = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]


@dataclass
class Draft:
    type: RecommendationType
    title: str
    description: str
    action: str
    priority: RecommendationPriority
    confidence: int
    estimated_uplift: Decimal | None
    payload: dict[str, Any]


class RecommendationEngine:
    """Compute and persist recommendations for a single restaurant/day."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = RecommendationRepository(session)
        self.analytics = AnalyticsService(session)

    async def generate_for(self, restaurant_id: uuid.UUID, for_date: date) -> int:
        restaurant = await RestaurantRepository(self.session).get(restaurant_id)
        if not restaurant:
            raise NotFoundError("Restaurant not found")

        window_end = for_date
        window_start = for_date - timedelta(days=27)  # 4 weeks for stable signals

        kpi = await self.analytics.kpi(restaurant, window_start, window_end)
        dishes = await self.analytics.dishes_top_bottom(
            restaurant, window_start, window_end, top_n=100
        )
        best, worst = await self.analytics.best_worst_weekday(
            restaurant, window_start, window_end
        )

        drafts: list[Draft] = []
        drafts += self._dish_drafts(dishes.top + dishes.bottom)
        if best and worst and best.profit > worst.profit:
            drafts.append(self._weekday_draft(best, worst))

        # Clear today's NEW recs and re-insert, so re-runs are idempotent.
        await self.repo.delete_for_date(restaurant_id, for_date)

        for d in drafts:
            self.session.add(
                Recommendation(
                    restaurant_id=restaurant_id,
                    for_date=for_date,
                    type=d.type,
                    priority=d.priority,
                    status=RecommendationStatus.NEW,
                    title=d.title,
                    description=d.description,
                    action=d.action,
                    estimated_uplift=d.estimated_uplift,
                    confidence=d.confidence,
                    payload=d.payload,
                )
            )

        await self.session.commit()
        logger.info(
            "recommendations.generated",
            restaurant_id=str(restaurant_id),
            for_date=for_date.isoformat(),
            count=len(drafts),
            kpi_profit=str(kpi.profit),
        )
        return len(drafts)

    # ----- Heuristics -----

    @staticmethod
    def _dish_drafts(dishes: list[Any]) -> list[Draft]:
        drafts: list[Draft] = []
        if not dishes:
            return drafts

        qtys = sorted([d.quantity for d in dishes])
        margins = [d.margin_percent for d in dishes if d.revenue > 0]
        if not qtys or not margins:
            return drafts

        q3_qty = qtys[int(len(qtys) * 0.75)]
        q1_qty = qtys[int(len(qtys) * 0.25)]
        avg_margin = sum(margins) / Decimal(len(margins))

        for d in dishes:
            # 4. REMOVE_DISH — chronic loss-maker.
            if d.revenue > 0 and d.profit <= Decimal("0"):
                drafts.append(
                    Draft(
                        type=RecommendationType.REMOVE_DISH,
                        title=f"Убрать из меню: {d.name}",
                        description=(
                            f"За последние 4 недели «{d.name}» дало выручку {d.revenue:.2f} "
                            f"и прибыль {d.profit:.2f}. Это убыточная позиция."
                        ),
                        action="Убрать из меню или пересмотреть рецептуру/цену.",
                        priority=RecommendationPriority.HIGH,
                        confidence=80,
                        estimated_uplift=-d.profit,
                        payload={"dish": d.model_dump(mode="json")},
                    )
                )
                continue

            # 5. COST_REDUCE — high food-cost share at scale.
            if d.revenue > 0 and d.quantity >= q3_qty:
                cost_share = d.cost / d.revenue if d.revenue else Decimal("0")
                if cost_share > Decimal("0.45"):
                    drafts.append(
                        Draft(
                            type=RecommendationType.COST_REDUCE,
                            title=f"Снизить себестоимость: {d.name}",
                            description=(
                                f"Food-cost share по «{d.name}» = {cost_share * 100:.1f}% "
                                f"при объёме продаж {d.quantity:.0f} шт. Это выше нормы 45%."
                            ),
                            action="Пересогласовать закупочные цены ингредиентов или уменьшить порцию на 5–10%.",
                            priority=RecommendationPriority.HIGH,
                            confidence=75,
                            estimated_uplift=(cost_share - Decimal("0.40")) * d.revenue,
                            payload={"dish": d.model_dump(mode="json"), "cost_share": float(cost_share)},
                        )
                    )

            # 2. PRICE_UP — top demand, below-avg margin.
            if d.quantity >= q3_qty and d.margin_percent < avg_margin - Decimal("5"):
                uplift = d.revenue * Decimal("0.05")
                drafts.append(
                    Draft(
                        type=RecommendationType.PRICE_UP,
                        title=f"Поднять цену: {d.name}",
                        description=(
                            f"«{d.name}» хорошо покупают ({d.quantity:.0f} шт.), но маржа {d.margin_percent:.1f}% "
                            f"ниже средней по меню ({avg_margin:.1f}%)."
                        ),
                        action="Повысить цену на 5–7% — спрос вероятно сохранится.",
                        priority=RecommendationPriority.MEDIUM,
                        confidence=70,
                        estimated_uplift=uplift,
                        payload={"dish": d.model_dump(mode="json"), "avg_margin": float(avg_margin)},
                    )
                )

            # 3. PRICE_DOWN — high margin but low demand.
            if d.quantity <= q1_qty and d.margin_percent > avg_margin + Decimal("10"):
                drafts.append(
                    Draft(
                        type=RecommendationType.PRICE_DOWN,
                        title=f"Снизить цену или акция: {d.name}",
                        description=(
                            f"«{d.name}» имеет высокую маржу {d.margin_percent:.1f}%, "
                            f"но продаётся редко ({d.quantity:.0f} шт.). Цена может отпугивать."
                        ),
                        action="Снизить цену на 8–10% или запустить таргетированную акцию на 2 недели.",
                        priority=RecommendationPriority.LOW,
                        confidence=60,
                        estimated_uplift=None,
                        payload={"dish": d.model_dump(mode="json")},
                    )
                )

            # 1. PROMOTE_DISH — top profit contributors.
            if d.profit > Decimal("0") and d.quantity >= q3_qty and d.margin_percent >= avg_margin:
                drafts.append(
                    Draft(
                        type=RecommendationType.PROMOTE_DISH,
                        title=f"Продвигать: {d.name}",
                        description=(
                            f"«{d.name}» — топ по прибыли (+{d.profit:.2f}) и маржа {d.margin_percent:.1f}%."
                        ),
                        action="Поднять в меню, добавить в spotlight, обучить персонал предлагать.",
                        priority=RecommendationPriority.MEDIUM,
                        confidence=80,
                        estimated_uplift=d.profit * Decimal("0.15"),
                        payload={"dish": d.model_dump(mode="json")},
                    )
                )

        return drafts

    @staticmethod
    def _weekday_draft(best, worst) -> Draft:
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
            confidence=75,
            estimated_uplift=delta * Decimal("0.10"),
            payload={
                "best": best.model_dump(mode="json"),
                "worst": worst.model_dump(mode="json"),
            },
        )
