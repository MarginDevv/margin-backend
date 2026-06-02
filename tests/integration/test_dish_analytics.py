"""Integration test for dish analytics over the order repository."""
from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

os.environ.setdefault("APP_SECRET_KEY", "x" * 32)
os.environ.setdefault("JWT_SECRET_KEY", "y" * 32)
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")


@pytest.fixture
async def session():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models import Base

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with Session() as s:
        yield s
    await engine.dispose()


async def _seed_orders(session, restaurant_id: uuid.UUID):
    """Seed two orders on two consecutive days with pizza + burger items."""
    from app.models.menu_item import MenuItem
    from app.models.order import Order, OrderStatus

    pizza = MenuItem(
        restaurant_id=restaurant_id,
        iiko_product_id="pizza",
        name="Пицца",
        sale_price=Decimal("600"),
        food_cost=Decimal("180"),
    )
    burger = MenuItem(
        restaurant_id=restaurant_id,
        iiko_product_id="burger",
        name="Бургер",
        sale_price=Decimal("400"),
        food_cost=Decimal("200"),
    )
    session.add_all([pizza, burger])
    await session.flush()

    now = datetime(2026, 6, 1, 14, 0, tzinfo=UTC)
    for day_offset in (0, 1):
        order = Order(
            restaurant_id=restaurant_id,
            iiko_order_id=f"ord-{day_offset}",
            opened_at=now + timedelta(days=day_offset),
            closed_at=now + timedelta(days=day_offset, minutes=30),
            status=OrderStatus.CLOSED,
            gross_revenue=Decimal("2000"),
            discount_amount=Decimal("0"),
            net_revenue=Decimal("2000"),
            total_food_cost=Decimal("760"),
            profit=Decimal("1240"),
        )
        session.add(order)
        await session.flush()
        from app.models.order import OrderItem

        session.add(OrderItem(
            order_id=order.id,
            menu_item_id=pizza.id,
            iiko_product_id="pizza",
            name_snapshot="Пицца",
            quantity=Decimal("2"),
            unit_price=Decimal("600"),
            unit_food_cost=Decimal("180"),
            line_revenue=Decimal("1200"),
            line_cost=Decimal("360"),
            line_profit=Decimal("840"),
        ))
        session.add(OrderItem(
            order_id=order.id,
            menu_item_id=burger.id,
            iiko_product_id="burger",
            name_snapshot="Бургер",
            quantity=Decimal("2"),
            unit_price=Decimal("400"),
            unit_food_cost=Decimal("200"),
            line_revenue=Decimal("800"),
            line_cost=Decimal("400"),
            line_profit=Decimal("400"),
        ))
    await session.commit()
    return {"pizza": pizza.id, "burger": burger.id}


@pytest.mark.asyncio
async def test_dish_performance_sort_by_quantity(session) -> None:
    from app.models.restaurant import Restaurant
    from app.repositories.order_repo import OrderRepository

    restaurant = Restaurant(name="T")
    session.add(restaurant)
    await session.flush()
    await _seed_orders(session, restaurant.id)

    repo = OrderRepository(session)
    start = datetime(2026, 6, 1, tzinfo=UTC)
    end = datetime(2026, 6, 3, tzinfo=UTC)
    rows = await repo.dish_performance(restaurant.id, start, end, sort_by="qty", limit=10)
    # Both dishes have qty=4 — order between them is unspecified, but both must
    # be present.
    names = {r["name"] for r in rows}
    assert names == {"Пицца", "Бургер"}


@pytest.mark.asyncio
async def test_dish_performance_sort_by_margin_percent(session) -> None:
    from app.models.restaurant import Restaurant
    from app.repositories.order_repo import OrderRepository

    restaurant = Restaurant(name="T")
    session.add(restaurant)
    await session.flush()
    await _seed_orders(session, restaurant.id)

    repo = OrderRepository(session)
    start = datetime(2026, 6, 1, tzinfo=UTC)
    end = datetime(2026, 6, 3, tzinfo=UTC)
    rows = await repo.dish_performance(
        restaurant.id, start, end, sort_by="margin_percent", direction="desc", limit=10
    )
    # Pizza margin = 840/1200 = 70%, burger 400/800 = 50% — pizza must be first.
    assert rows[0]["name"] == "Пицца"
    assert rows[1]["name"] == "Бургер"
