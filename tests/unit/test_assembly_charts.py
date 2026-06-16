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
    pizza = by_id["pizza"]
    # Pizza chart references {dough, cheese, tomato}, but dough is NOT in this
    # payload — the lookup skips unknown ingredients (we'd undercount but not
    # crash). So: cheese (500 * 0.15) + tomato (80 * 0.1) = 75 + 8 = 83.
    # The recursive case (with dough resolved) lives in
    # test_chart_recursion_uses_nested_cost.
    assert pizza["food_cost"] == Decimal("83")


def test_chart_falls_back_to_cost_price_when_no_recipe() -> None:
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
