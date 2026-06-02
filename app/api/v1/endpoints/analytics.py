"""Analytics endpoints."""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import DbSession, require_member
from app.core.exceptions import NotFoundError
from app.models.restaurant import Restaurant
from app.repositories.menu_repo import MenuItemRepository
from app.schemas.analytics import (
    CategoryPerformance,
    DayPoint,
    DishDailyStat,
    DishesTopBottom,
    DishPair,
    DishPerformance,
    DishTrend,
    Heatmap,
    HourPoint,
    KpiComparison,
    KpiSummary,
    WeekdayPoint,
)
from app.services.analytics.analytics_service import AnalyticsService

SortBy = Literal["qty", "revenue", "profit", "margin_percent"]
Direction = Literal["asc", "desc"]
Granularity = Literal["day", "week"]

router = APIRouter()


def _default_range(start: date | None, end: date | None) -> tuple[date, date]:
    today = date.today()
    if not end:
        end = today
    if not start:
        start = end - timedelta(days=29)
    if start > end:
        raise ValueError("start must be <= end")
    return start, end


@router.get("/kpi", response_model=KpiSummary)
async def kpi(
    restaurant: Annotated[Restaurant, Depends(require_member)],
    session: DbSession,
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
) -> KpiSummary:
    s, e = _default_range(start, end)
    return await AnalyticsService(session).kpi(restaurant, s, e)


@router.get("/by-hour", response_model=list[HourPoint])
async def by_hour(
    restaurant: Annotated[Restaurant, Depends(require_member)],
    session: DbSession,
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
) -> list[HourPoint]:
    s, e = _default_range(start, end)
    return await AnalyticsService(session).by_hour(restaurant, s, e)


@router.get("/by-day", response_model=list[DayPoint])
async def by_day(
    restaurant: Annotated[Restaurant, Depends(require_member)],
    session: DbSession,
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
) -> list[DayPoint]:
    s, e = _default_range(start, end)
    return await AnalyticsService(session).by_day(restaurant, s, e)


@router.get("/by-weekday", response_model=list[WeekdayPoint])
async def by_weekday(
    restaurant: Annotated[Restaurant, Depends(require_member)],
    session: DbSession,
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
) -> list[WeekdayPoint]:
    s, e = _default_range(start, end)
    return await AnalyticsService(session).by_weekday(restaurant, s, e)


@router.get(
    "/dishes",
    response_model=DishesTopBottom,
    summary="Топ и анти-топ блюд по выбранной метрике",
)
async def dishes(
    restaurant: Annotated[Restaurant, Depends(require_member)],
    session: DbSession,
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    top_n: int = Query(default=10, ge=1, le=100),
    sort_by: SortBy = Query(default="profit"),
) -> DishesTopBottom:
    s, e = _default_range(start, end)
    return await AnalyticsService(session).dishes_top_bottom(
        restaurant, s, e, top_n=top_n, sort_by=sort_by
    )


@router.get(
    "/dishes/ranked",
    response_model=list[DishPerformance],
    summary="Плоский список блюд с сортировкой (qty/revenue/profit/margin%)",
)
async def dishes_ranked(
    restaurant: Annotated[Restaurant, Depends(require_member)],
    session: DbSession,
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    sort_by: SortBy = Query(default="profit"),
    direction: Direction = Query(default="desc"),
    limit: int = Query(default=50, ge=1, le=500),
) -> list[DishPerformance]:
    s, e = _default_range(start, end)
    return await AnalyticsService(session).dishes_ranked(
        restaurant, s, e, sort_by=sort_by, direction=direction, limit=limit
    )


@router.get(
    "/dishes/daily",
    response_model=list[DishDailyStat],
    summary="Плоская таблица (date × dish) с продажами и маржой по дням",
)
async def dishes_daily(
    restaurant: Annotated[Restaurant, Depends(require_member)],
    session: DbSession,
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    menu_item_id: list[uuid.UUID] | None = Query(default=None),
) -> list[DishDailyStat]:
    s, e = _default_range(start, end)
    return await AnalyticsService(session).dish_daily_stats(
        restaurant, s, e, menu_item_ids=menu_item_id
    )


@router.get(
    "/dishes/{menu_item_id}/trend",
    response_model=DishTrend,
    summary="Динамика конкретного блюда (день / неделя)",
)
async def dish_trend(
    menu_item_id: uuid.UUID,
    restaurant: Annotated[Restaurant, Depends(require_member)],
    session: DbSession,
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    granularity: Granularity = Query(default="day"),
) -> DishTrend:
    s, e = _default_range(start, end)
    item = await MenuItemRepository(session).get(menu_item_id)
    if not item or item.restaurant_id != restaurant.id:
        raise NotFoundError("Menu item not found")
    return await AnalyticsService(session).dish_trend(
        restaurant, menu_item_id, s, e, granularity=granularity
    )


@router.get(
    "/categories",
    response_model=list[CategoryPerformance],
    summary="Какой раздел меню приносит больше прибыли",
)
async def categories(
    restaurant: Annotated[Restaurant, Depends(require_member)],
    session: DbSession,
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
) -> list[CategoryPerformance]:
    s, e = _default_range(start, end)
    return await AnalyticsService(session).category_performance(restaurant, s, e)


@router.get(
    "/cross-sell",
    response_model=list[DishPair],
    summary="Что чаще всего заказывают вместе (пары блюд)",
)
async def cross_sell(
    restaurant: Annotated[Restaurant, Depends(require_member)],
    session: DbSession,
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    min_orders: int = Query(default=2, ge=1, le=100),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[DishPair]:
    s, e = _default_range(start, end)
    return await AnalyticsService(session).dish_pairs(
        restaurant, s, e, min_orders=min_orders, limit=limit
    )


@router.get(
    "/kpi/compare",
    response_model=KpiComparison,
    summary="KPI текущего периода + предыдущего равной длины + дельты %",
)
async def kpi_compare(
    restaurant: Annotated[Restaurant, Depends(require_member)],
    session: DbSession,
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
) -> KpiComparison:
    s, e = _default_range(start, end)
    return await AnalyticsService(session).kpi_compare(restaurant, s, e)


@router.get(
    "/heatmap",
    response_model=Heatmap,
    summary="Тепловая карта (день недели × час) по выручке / прибыли / заказам",
)
async def heatmap(
    restaurant: Annotated[Restaurant, Depends(require_member)],
    session: DbSession,
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    metric: Literal["revenue", "profit", "orders"] = Query(default="revenue"),
) -> Heatmap:
    s, e = _default_range(start, end)
    return await AnalyticsService(session).heatmap_weekday_hour(
        restaurant, s, e, metric=metric
    )
