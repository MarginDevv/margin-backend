"""Order / OrderItem repository with analytics queries."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Numeric, and_, cast, delete, extract, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import aliased

from app.models.menu_item import MenuItem
from app.models.order import Order, OrderItem
from app.repositories.base import BaseRepository


class OrderRepository(BaseRepository[Order]):
    model = Order

    async def get_by_iiko_id(
        self, restaurant_id: uuid.UUID, iiko_order_id: str
    ) -> Order | None:
        stmt = select(Order).where(
            Order.restaurant_id == restaurant_id,
            Order.iiko_order_id == iiko_order_id,
        )
        return await self.session.scalar(stmt)

    async def upsert_order(self, row: dict[str, Any]) -> uuid.UUID:
        """Upsert order header, return its id."""
        stmt = insert(Order).values(row)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_order_iiko",
            set_={
                "closed_at": stmt.excluded.closed_at,
                "status": stmt.excluded.status,
                "guests_count": stmt.excluded.guests_count,
                "waiter_name": stmt.excluded.waiter_name,
                "gross_revenue": stmt.excluded.gross_revenue,
                "discount_amount": stmt.excluded.discount_amount,
                "net_revenue": stmt.excluded.net_revenue,
                "total_food_cost": stmt.excluded.total_food_cost,
                "profit": stmt.excluded.profit,
            },
        ).returning(Order.id)
        result = await self.session.execute(stmt)
        order_id = result.scalar_one()
        return order_id

    async def replace_items(self, order_id: uuid.UUID, items: list[dict[str, Any]]) -> None:
        await self.session.execute(delete(OrderItem).where(OrderItem.order_id == order_id))
        if items:
            self.session.add_all([OrderItem(order_id=order_id, **i) for i in items])
        await self.session.flush()

    # ----- Analytics -----

    async def kpi_summary(
        self, restaurant_id: uuid.UUID, start_utc: datetime, end_utc: datetime
    ) -> dict[str, Any]:
        stmt = select(
            func.count(Order.id).label("orders_count"),
            func.coalesce(func.sum(Order.guests_count), 0).label("guests_count"),
            func.coalesce(func.sum(Order.gross_revenue), 0).label("gross_revenue"),
            func.coalesce(func.sum(Order.net_revenue), 0).label("net_revenue"),
            func.coalesce(func.sum(Order.total_food_cost), 0).label("total_food_cost"),
            func.coalesce(func.sum(Order.profit), 0).label("profit"),
        ).where(
            Order.restaurant_id == restaurant_id,
            Order.closed_at.is_not(None),
            Order.closed_at >= start_utc,
            Order.closed_at < end_utc,
        )
        row = (await self.session.execute(stmt)).one()
        return dict(row._mapping)

    async def by_hour(
        self, restaurant_id: uuid.UUID, start_utc: datetime, end_utc: datetime, tz: str
    ) -> list[dict[str, Any]]:
        local = func.timezone(tz, Order.closed_at)
        hour_col = cast(extract("hour", local), Numeric)
        stmt = (
            select(
                hour_col.label("hour"),
                func.count(Order.id).label("orders_count"),
                func.coalesce(func.sum(Order.net_revenue), 0).label("revenue"),
                func.coalesce(func.sum(Order.profit), 0).label("profit"),
            )
            .where(
                Order.restaurant_id == restaurant_id,
                Order.closed_at.is_not(None),
                Order.closed_at >= start_utc,
                Order.closed_at < end_utc,
            )
            .group_by(hour_col)
            .order_by(hour_col)
        )
        return [dict(r._mapping) for r in (await self.session.execute(stmt)).all()]

    async def by_weekday(
        self, restaurant_id: uuid.UUID, start_utc: datetime, end_utc: datetime, tz: str
    ) -> list[dict[str, Any]]:
        local = func.timezone(tz, Order.closed_at)
        # Postgres: 0=Sun..6=Sat. Convert to 0=Mon..6=Sun.
        pg_dow = extract("dow", local)
        weekday = cast(((pg_dow + 6) % 7), Numeric).label("weekday")
        stmt = (
            select(
                weekday,
                func.count(Order.id).label("orders_count"),
                func.coalesce(func.sum(Order.net_revenue), 0).label("revenue"),
                func.coalesce(func.sum(Order.profit), 0).label("profit"),
            )
            .where(
                Order.restaurant_id == restaurant_id,
                Order.closed_at.is_not(None),
                Order.closed_at >= start_utc,
                Order.closed_at < end_utc,
            )
            .group_by(weekday)
            .order_by(weekday)
        )
        return [dict(r._mapping) for r in (await self.session.execute(stmt)).all()]

    async def by_day(
        self, restaurant_id: uuid.UUID, start_utc: datetime, end_utc: datetime, tz: str
    ) -> list[dict[str, Any]]:
        day = func.date(func.timezone(tz, Order.closed_at)).label("day")
        stmt = (
            select(
                day,
                func.count(Order.id).label("orders_count"),
                func.coalesce(func.sum(Order.net_revenue), 0).label("revenue"),
                func.coalesce(func.sum(Order.profit), 0).label("profit"),
            )
            .where(
                Order.restaurant_id == restaurant_id,
                Order.closed_at.is_not(None),
                Order.closed_at >= start_utc,
                Order.closed_at < end_utc,
            )
            .group_by(day)
            .order_by(day)
        )
        return [dict(r._mapping) for r in (await self.session.execute(stmt)).all()]

    async def dish_performance(
        self,
        restaurant_id: uuid.UUID,
        start_utc: datetime,
        end_utc: datetime,
        *,
        sort_by: str = "profit",
        direction: str = "desc",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Aggregate per-dish stats for a date range.

        sort_by ∈ {qty, revenue, cost, profit, margin_percent}
        direction ∈ {asc, desc}
        """
        SORT_COLUMNS = {
            "qty": func.sum(OrderItem.quantity),
            "quantity": func.sum(OrderItem.quantity),
            "revenue": func.sum(OrderItem.line_revenue),
            "cost": func.sum(OrderItem.line_cost),
            "profit": func.sum(OrderItem.line_profit),
            # margin_percent is computed below — fall back to profit ordering and
            # re-sort in Python.
        }
        sort_expr = SORT_COLUMNS.get(sort_by, SORT_COLUMNS["profit"])
        order = sort_expr.asc() if direction == "asc" else sort_expr.desc()

        stmt = (
            select(
                OrderItem.menu_item_id,
                func.coalesce(MenuItem.name, OrderItem.name_snapshot).label("name"),
                MenuItem.category.label("category"),
                func.coalesce(func.sum(OrderItem.quantity), 0).label("quantity"),
                func.coalesce(func.sum(OrderItem.line_revenue), 0).label("revenue"),
                func.coalesce(func.sum(OrderItem.line_cost), 0).label("cost"),
                func.coalesce(func.sum(OrderItem.line_profit), 0).label("profit"),
            )
            .select_from(OrderItem)
            .join(Order, Order.id == OrderItem.order_id)
            .outerjoin(MenuItem, MenuItem.id == OrderItem.menu_item_id)
            .where(
                Order.restaurant_id == restaurant_id,
                Order.closed_at.is_not(None),
                and_(Order.closed_at >= start_utc, Order.closed_at < end_utc),
            )
            .group_by(
                OrderItem.menu_item_id,
                MenuItem.name,
                OrderItem.name_snapshot,
                MenuItem.category,
            )
            .order_by(order)
            .limit(limit if sort_by != "margin_percent" else 500)
        )
        rows: list[dict[str, Any]] = []
        for r in (await self.session.execute(stmt)).all():
            d = dict(r._mapping)
            revenue = Decimal(str(d["revenue"]))
            profit = Decimal(str(d["profit"]))
            d["margin_percent"] = (profit / revenue * Decimal("100")) if revenue else Decimal("0")
            rows.append(d)

        if sort_by == "margin_percent":
            rows.sort(
                key=lambda row: row["margin_percent"],
                reverse=(direction != "asc"),
            )
            rows = rows[:limit]
        return rows

    async def dish_daily_stats(
        self,
        restaurant_id: uuid.UUID,
        start_utc: datetime,
        end_utc: datetime,
        tz: str,
        *,
        menu_item_ids: list[uuid.UUID] | None = None,
    ) -> list[dict[str, Any]]:
        """One row per (local_date, dish). Used by dashboard heatmaps / trend tables."""
        day = func.date(func.timezone(tz, Order.closed_at)).label("day")
        stmt = (
            select(
                day,
                OrderItem.menu_item_id,
                func.coalesce(MenuItem.name, OrderItem.name_snapshot).label("name"),
                MenuItem.category.label("category"),
                func.coalesce(func.sum(OrderItem.quantity), 0).label("quantity"),
                func.coalesce(func.sum(OrderItem.line_revenue), 0).label("revenue"),
                func.coalesce(func.sum(OrderItem.line_cost), 0).label("cost"),
                func.coalesce(func.sum(OrderItem.line_profit), 0).label("profit"),
            )
            .select_from(OrderItem)
            .join(Order, Order.id == OrderItem.order_id)
            .outerjoin(MenuItem, MenuItem.id == OrderItem.menu_item_id)
            .where(
                Order.restaurant_id == restaurant_id,
                Order.closed_at.is_not(None),
                and_(Order.closed_at >= start_utc, Order.closed_at < end_utc),
            )
        )
        if menu_item_ids:
            stmt = stmt.where(OrderItem.menu_item_id.in_(menu_item_ids))
        stmt = stmt.group_by(
            day,
            OrderItem.menu_item_id,
            MenuItem.name,
            OrderItem.name_snapshot,
            MenuItem.category,
        ).order_by(day, func.sum(OrderItem.line_profit).desc())

        rows: list[dict[str, Any]] = []
        for r in (await self.session.execute(stmt)).all():
            d = dict(r._mapping)
            revenue = Decimal(str(d["revenue"]))
            profit = Decimal(str(d["profit"]))
            d["margin_percent"] = (
                profit / revenue * Decimal("100") if revenue else Decimal("0")
            )
            rows.append(d)
        return rows

    async def dish_trend(
        self,
        restaurant_id: uuid.UUID,
        menu_item_id: uuid.UUID,
        start_utc: datetime,
        end_utc: datetime,
        tz: str,
        *,
        granularity: str = "day",
    ) -> list[dict[str, Any]]:
        """Time-series for a single dish — day or ISO week buckets."""
        local = func.timezone(tz, Order.closed_at)
        bucket = (
            func.date_trunc("week", local).label("bucket")
            if granularity == "week"
            else func.date(local).label("bucket")
        )
        stmt = (
            select(
                bucket,
                func.coalesce(func.sum(OrderItem.quantity), 0).label("quantity"),
                func.coalesce(func.sum(OrderItem.line_revenue), 0).label("revenue"),
                func.coalesce(func.sum(OrderItem.line_cost), 0).label("cost"),
                func.coalesce(func.sum(OrderItem.line_profit), 0).label("profit"),
            )
            .select_from(OrderItem)
            .join(Order, Order.id == OrderItem.order_id)
            .where(
                Order.restaurant_id == restaurant_id,
                OrderItem.menu_item_id == menu_item_id,
                Order.closed_at.is_not(None),
                and_(Order.closed_at >= start_utc, Order.closed_at < end_utc),
            )
            .group_by(bucket)
            .order_by(bucket)
        )
        rows: list[dict[str, Any]] = []
        for r in (await self.session.execute(stmt)).all():
            d = dict(r._mapping)
            revenue = Decimal(str(d["revenue"]))
            profit = Decimal(str(d["profit"]))
            d["margin_percent"] = (
                profit / revenue * Decimal("100") if revenue else Decimal("0")
            )
            rows.append(d)
        return rows


    async def category_performance(
        self,
        restaurant_id: uuid.UUID,
        start_utc: datetime,
        end_utc: datetime,
    ) -> list[dict[str, Any]]:
        """Aggregate per-category for the period. Uncategorised dishes are bucketed
        under "Без категории"."""
        category_col = func.coalesce(MenuItem.category, "Без категории").label("category")
        stmt = (
            select(
                category_col,
                func.coalesce(func.sum(OrderItem.quantity), 0).label("quantity"),
                func.coalesce(func.sum(OrderItem.line_revenue), 0).label("revenue"),
                func.coalesce(func.sum(OrderItem.line_cost), 0).label("cost"),
                func.coalesce(func.sum(OrderItem.line_profit), 0).label("profit"),
                func.count(func.distinct(OrderItem.menu_item_id)).label("dishes_count"),
            )
            .select_from(OrderItem)
            .join(Order, Order.id == OrderItem.order_id)
            .outerjoin(MenuItem, MenuItem.id == OrderItem.menu_item_id)
            .where(
                Order.restaurant_id == restaurant_id,
                Order.closed_at.is_not(None),
                and_(Order.closed_at >= start_utc, Order.closed_at < end_utc),
            )
            .group_by(category_col)
            .order_by(func.sum(OrderItem.line_profit).desc())
        )
        rows: list[dict[str, Any]] = []
        for r in (await self.session.execute(stmt)).all():
            d = dict(r._mapping)
            revenue = Decimal(str(d["revenue"]))
            profit = Decimal(str(d["profit"]))
            d["margin_percent"] = (
                profit / revenue * Decimal("100") if revenue else Decimal("0")
            )
            rows.append(d)
        return rows

    async def dish_pairs(
        self,
        restaurant_id: uuid.UUID,
        start_utc: datetime,
        end_utc: datetime,
        *,
        min_orders: int = 2,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Top co-occurring dish pairs (basket analysis).

        Self-joins order_items on order_id; restricts to unique unordered
        pairs via `a.menu_item_id < b.menu_item_id`. Returns the top pairs
        by joint order count. Skips items without a menu_item_id (cant be
        matched reliably to a dish).

        `min_orders` filters out one-off coincidences.
        """
        a = aliased(OrderItem)
        b = aliased(OrderItem)
        ma = aliased(MenuItem)
        mb = aliased(MenuItem)

        co_count = func.count(func.distinct(a.order_id)).label("orders_count")
        combined_revenue = func.coalesce(
            func.sum(a.line_revenue + b.line_revenue), 0
        ).label("combined_revenue")
        combined_profit = func.coalesce(
            func.sum(a.line_profit + b.line_profit), 0
        ).label("combined_profit")

        stmt = (
            select(
                a.menu_item_id.label("item_a_id"),
                func.coalesce(ma.name, "—").label("item_a_name"),
                ma.category.label("item_a_category"),
                b.menu_item_id.label("item_b_id"),
                func.coalesce(mb.name, "—").label("item_b_name"),
                mb.category.label("item_b_category"),
                co_count,
                combined_revenue,
                combined_profit,
            )
            .select_from(a)
            .join(b, and_(b.order_id == a.order_id, b.menu_item_id > a.menu_item_id))
            .join(Order, Order.id == a.order_id)
            .outerjoin(ma, ma.id == a.menu_item_id)
            .outerjoin(mb, mb.id == b.menu_item_id)
            .where(
                Order.restaurant_id == restaurant_id,
                Order.closed_at.is_not(None),
                and_(Order.closed_at >= start_utc, Order.closed_at < end_utc),
                a.menu_item_id.is_not(None),
                b.menu_item_id.is_not(None),
            )
            .group_by(
                a.menu_item_id, b.menu_item_id,
                ma.name, mb.name, ma.category, mb.category,
            )
            .having(func.count(func.distinct(a.order_id)) >= min_orders)
            .order_by(co_count.desc())
            .limit(limit)
        )
        rows: list[dict[str, Any]] = []
        for r in (await self.session.execute(stmt)).all():
            rows.append(dict(r._mapping))
        return rows



    async def heatmap_weekday_hour(
        self,
        restaurant_id: uuid.UUID,
        start_utc: datetime,
        end_utc: datetime,
        tz: str,
    ) -> list[dict[str, Any]]:
        """Return one row per (weekday, hour) in the period."""
        local = func.timezone(tz, Order.closed_at)
        pg_dow = extract("dow", local)
        weekday = cast(((pg_dow + 6) % 7), Numeric).label("weekday")
        hour = cast(extract("hour", local), Numeric).label("hour")
        stmt = (
            select(
                weekday,
                hour,
                func.count(Order.id).label("orders_count"),
                func.coalesce(func.sum(Order.net_revenue), 0).label("revenue"),
                func.coalesce(func.sum(Order.profit), 0).label("profit"),
            )
            .where(
                Order.restaurant_id == restaurant_id,
                Order.closed_at.is_not(None),
                Order.closed_at >= start_utc,
                Order.closed_at < end_utc,
            )
            .group_by(weekday, hour)
            .order_by(weekday, hour)
        )
        return [dict(r._mapping) for r in (await self.session.execute(stmt)).all()]
