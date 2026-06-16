"""Category aggregation and dish-pair (cross-sell) queries."""
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
    from app.models import Base
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with Session() as s:
        yield s
    await engine.dispose()


async def _seed(session, restaurant_id: uuid.UUID):
    """3 orders: pizza+cola twice, pizza+beer once. Categories: Hot, Drinks."""
    from app.models.menu_item import MenuItem
    from app.models.order import Order, OrderItem, OrderStatus

    pizza = MenuItem(
        restaurant_id=restaurant_id,
        iiko_product_id="pizza",
        name="Пицца",
        category="Горячее",
        sale_price=Decimal("600"),
        food_cost=Decimal("180"),
    )
    cola = MenuItem(
        restaurant_id=restaurant_id,
        iiko_product_id="cola",
        name="Кола",
        category="Напитки",
        sale_price=Decimal("150"),
        food_cost=Decimal("30"),
    )
    beer = MenuItem(
        restaurant_id=restaurant_id,
        iiko_product_id="beer",
        name="Пиво",
        category="Напитки",
        sale_price=Decimal("250"),
        food_cost=Decimal("80"),
    )
    session.add_all([pizza, cola, beer])
    await session.flush()

    now = datetime(2026, 6, 1, 14, 0, tzinfo=UTC)
    pairs = [(pizza, cola), (pizza, cola), (pizza, beer)]
    for i, (a, b) in enumerate(pairs):
        order = Order(
            restaurant_id=restaurant_id,
            iiko_order_id=f"ord-{i}",
            opened_at=now + timedelta(hours=i),
            closed_at=now + timedelta(hours=i, minutes=30),
            status=OrderStatus.CLOSED,
            gross_revenue=Decimal("750"),
            discount_amount=Decimal("0"),
            net_revenue=Decimal("750"),
            total_food_cost=Decimal("210"),
            profit=Decimal("540"),
        )
        session.add(order)
        await session.flush()
        for item in (a, b):
            session.add(OrderItem(
                order_id=order.id,
                menu_item_id=item.id,
                iiko_product_id=item.iiko_product_id,
                name_snapshot=item.name,
                quantity=Decimal("1"),
                unit_price=item.sale_price,
                unit_food_cost=item.food_cost,
                line_revenue=item.sale_price,
                line_cost=item.food_cost,
                line_profit=item.sale_price - item.food_cost,
            ))
    await session.commit()
    return {"pizza": pizza.id, "cola": cola.id, "beer": beer.id}


@pytest.mark.asyncio
async def test_category_performance_aggregates_correctly(session) -> None:
    from app.models.restaurant import Restaurant
    from app.repositories.order_repo import OrderRepository

    restaurant = Restaurant(name="T")
    session.add(restaurant)
    await session.flush()
    await _seed(session, restaurant.id)

    repo = OrderRepository(session)
    start = datetime(2026, 6, 1, tzinfo=UTC)
    end = datetime(2026, 6, 2, tzinfo=UTC)
    rows = await repo.category_performance(restaurant.id, start, end)
    by_cat = {r["category"]: r for r in rows}

    # Горячее: 3 pizza orders × (600 revenue, 420 profit) = 1800 / 1260
    assert by_cat["Горячее"]["quantity"] == Decimal("3")
    assert by_cat["Горячее"]["revenue"] == Decimal("1800")
    assert by_cat["Горячее"]["profit"] == Decimal("1260")
    assert by_cat["Горячее"]["dishes_count"] == 1

    # Напитки: 2 cola (300 rev / 240 profit) + 1 beer (250/170) = 550 / 410
    assert by_cat["Напитки"]["quantity"] == Decimal("3")
    assert by_cat["Напитки"]["revenue"] == Decimal("550")
    assert by_cat["Напитки"]["profit"] == Decimal("410")
    assert by_cat["Напитки"]["dishes_count"] == 2


@pytest.mark.asyncio
async def test_dish_pairs_returns_pizza_cola_top(session) -> None:
    from app.models.restaurant import Restaurant
    from app.repositories.order_repo import OrderRepository

    restaurant = Restaurant(name="T")
    session.add(restaurant)
    await session.flush()
    await _seed(session, restaurant.id)

    repo = OrderRepository(session)
    start = datetime(2026, 6, 1, tzinfo=UTC)
    end = datetime(2026, 6, 2, tzinfo=UTC)
    pairs = await repo.dish_pairs(restaurant.id, start, end, min_orders=1, limit=10)

    # Should include both pizza+cola (2 orders) and pizza+beer (1 order).
    by_set = {
        frozenset((row["item_a_name"], row["item_b_name"])): row
        for row in pairs
    }
    pizza_cola = by_set[frozenset(("Пицца", "Кола"))]
    pizza_beer = by_set[frozenset(("Пицца", "Пиво"))]
    assert pizza_cola["orders_count"] == 2
    assert pizza_beer["orders_count"] == 1
    # pizza+cola top
    assert pairs[0]["orders_count"] >= pairs[1]["orders_count"]


@pytest.mark.asyncio
async def test_dish_pairs_min_orders_filter(session) -> None:
    from app.models.restaurant import Restaurant
    from app.repositories.order_repo import OrderRepository

    restaurant = Restaurant(name="T")
    session.add(restaurant)
    await session.flush()
    await _seed(session, restaurant.id)

    repo = OrderRepository(session)
    start = datetime(2026, 6, 1, tzinfo=UTC)
    end = datetime(2026, 6, 2, tzinfo=UTC)
    pairs = await repo.dish_pairs(restaurant.id, start, end, min_orders=2, limit=10)
    # Only pizza+cola has >=2 orders together.
    assert len(pairs) == 1
    assert pairs[0]["orders_count"] == 2
