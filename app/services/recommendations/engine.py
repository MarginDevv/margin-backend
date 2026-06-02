"""Heuristic recommendation engine.

Generates concrete, actionable, profit-oriented recommendations from order-level
analytics. The engine orchestrates: fetch analytics → apply rules (see
``rules.py``) → optionally polish copy with an LLM → persist.

The rules themselves live in ``app.services.recommendations.rules`` as pure
functions so they can be unit-tested without a DB.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.models.activity_event import ActivityKind
from app.models.recommendation import Recommendation, RecommendationStatus
from app.repositories.recommendation_repo import RecommendationRepository
from app.repositories.restaurant_repo import RestaurantRepository
from app.services.activity.event_service import ActivityEventService
from app.services.analytics.analytics_service import AnalyticsService
from app.services.llm.factory import get_llm
from app.services.llm.recommendation_enhancer import RecommendationEnhancer
from app.services.recommendations.rules import (
    Draft,
    dish_drafts,
    menu_concentration,
    weekday_dead_zone,
    weekday_draft,
)

logger = get_logger("recommendations.engine")


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
        weekday_points = await self.analytics.by_weekday(
            restaurant, window_start, window_end
        )

        all_dishes = dishes.top + dishes.bottom
        drafts: list[Draft] = dish_drafts(all_dishes)

        if (mc := menu_concentration(all_dishes)) is not None:
            drafts.append(mc)

        if weekday_points:
            best = max(weekday_points, key=lambda p: p.profit)
            worst = min(weekday_points, key=lambda p: p.profit)
            if (wd := weekday_draft(best, worst)) is not None:
                drafts.append(wd)
            if (wdz := weekday_dead_zone(weekday_points)) is not None:
                drafts.append(wdz)

        # Optional: rewrite description/action via LLM for nicer narrative.
        # Safe to call always — falls back to heuristic text when LLM is off.
        llm = get_llm()
        enhancer = RecommendationEnhancer(llm)
        try:
            for d in drafts:
                desc, action = await enhancer.enhance(
                    title=d.title,
                    description=d.description,
                    action=d.action,
                    restaurant_name=restaurant.name,
                )
                d.description = desc
                d.action = action
        finally:
            await llm.aclose()

        # Clear today's NEW recs and re-insert, so re-runs are idempotent.
        await self.repo.delete_for_date(restaurant_id, for_date)

        for d in drafts:
            self.session.add(
                Recommendation(
                    restaurant_id=restaurant_id,
                    for_date=for_date,
                    type=d.type,
                    priority=d.priority,
                    category=d.category,
                    effort=d.effort,
                    status=RecommendationStatus.NEW,
                    title=d.title,
                    description=d.description,
                    action=d.action,
                    estimated_uplift=d.estimated_uplift,
                    confidence=d.confidence,
                    payload=d.payload,
                )
            )

        await ActivityEventService(self.session).emit(
            restaurant_id,
            ActivityKind.RECOMMENDATIONS_GENERATED,
            title=f"Сгенерировано {len(drafts)} рекомендаций на {for_date.isoformat()}",
            payload={"for_date": for_date.isoformat(), "count": len(drafts)},
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
