"""Unit tests for recursive recipe-based food_cost computation."""
from __future__ import annotations

import os
import uuid
from decimal import Decimal

os.environ.setdefault("APP_SECRET_KEY", "x" * 32)
os.environ.setdefault("JWT_SECRET_KEY", "y" * 32)


def _flour():
    return {"id": "flour", "name": "Мука", "costPrice": 30}


def _cheese():
    return {"id": "cheese", "name": "Сыр", "costPrice": 500}


def _tomato():
    return {"id": "tomato", "name": "Томат", "costPrice": 80}


def _pizza_dough():
    return {
        "id": "dough",
        "name": "Тесто",
        "assemblyCharts": [
            {
                "items": [
                    {"productId": "flour", "amountIn": 0.2},  # 200g
                ]
            }
        ],
    }


def _pizza_margherita():
    return {
        "id": "pizza",
        "name": "Пицца Маргарита",
        "type": "DISH",
        "sellingPrice": 599,
        "assemblyCharts": [
            {
                "items": [
                    {"productId": "dough", "amountIn": 1},
                    {"productId": "cheese", "amountIn": 0.15},
                    {"productId": "tomato", "amountIn": 0.1},
                ]
            }
        ],
    }


def test_simple_chart_food_cost() -> None:
    from app.services.iiko.transformers import nomenclature_to_menu_rows

    payload = {
        "products": [_flour(), _cheese(), _tomato(), _pizza_margherita()],
    }
    rows = nomenclature_to_menu_rows(uuid.uuid4(), payload)
    by_id = {r["iiko_product_id"]: r for r in rows}
    # dough not in rows (no chart-less DISH/GOODS filter — flour is GOODS by default fallback)
    pizza = by_id["pizza"]
    # flour direct via dough not included (dough has no type, so it's skipped)
    # cheese 500 * 0.15 = 75 + tomato 80 * 0.1 = 8 = 83
    # PLUS dough — dough has assemblyCharts but no `type` so it IS included in
    # _build_cost_lookup; nested compute => flour 30 * 0.2 = 6.
    # Pizza chart: 1 * dough_cost(6) + 0.15 * 500 + 0.1 * 80 = 6 + 75 + 8 = 89
    assert pizza["food_cost"] == Decimal("89")


def test_chart_falls_back_to_costPrice_when_no_recipe() -> None:
    from app.services.iiko.transformers import nomenclature_to_menu_rows

    payload = {
        "products": [
            {
                "id": "p1",
                "name": "Хлеб",
                "type": "GOODS",
                "sellingPrice": 50,
                "costPrice": 20,
            }
        ],
    }
    rows = nomenclature_to_menu_rows(uuid.uuid4(), payload)
    assert rows[0]["food_cost"] == Decimal("20")


def test_chart_recursion_uses_nested_cost() -> None:
    from app.services.iiko.transformers import nomenclature_to_menu_rows

    payload = {
        "products": [_flour(), _cheese(), _tomato(), _pizza_dough(), _pizza_margherita()],
    }
    rows = nomenclature_to_menu_rows(uuid.uuid4(), payload)
    pizza = next(r for r in rows if r["iiko_product_id"] == "pizza")
    # dough cost = flour 30 * 0.2 = 6
    # pizza = 1*6 + 0.15*500 + 0.1*80 = 6 + 75 + 8 = 89
    assert pizza["food_cost"] == Decimal("89")


def test_chart_handles_cycle() -> None:
    from app.services.iiko.transformers import nomenclature_to_menu_rows

    payload = {
        "products": [
            {
                "id": "a",
                "name": "A",
                "assemblyCharts": [{"items": [{"productId": "b", "amountIn": 1}]}],
            },
            {
                "id": "b",
                "name": "B",
                "costPrice": 10,
                "assemblyCharts": [{"items": [{"productId": "a", "amountIn": 1}]}],
            },
        ],
    }
    rows = nomenclature_to_menu_rows(uuid.uuid4(), payload)
    # Cycle should not infinite-loop; cost is undercounted but call returns.
    assert len(rows) == 2
