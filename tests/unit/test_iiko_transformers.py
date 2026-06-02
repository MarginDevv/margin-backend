"""Unit tests for iiko payload transformers."""
from __future__ import annotations

import os
import uuid
from decimal import Decimal

os.environ.setdefault("APP_SECRET_KEY", "x" * 32)
os.environ.setdefault("JWT_SECRET_KEY", "y" * 32)


def test_nomenclature_maps_products() -> None:
    from app.services.iiko.transformers import nomenclature_to_menu_rows

    restaurant_id = uuid.uuid4()
    payload = {
        "productCategories": [{"id": "cat1", "name": "Hot dishes"}],
        "products": [
            {
                "id": "p1",
                "name": "Pizza Margherita",
                "productCategoryId": "cat1",
                "sellingPrice": 599,
                "costPrice": 180,
                "vat": 20,
                "isDeleted": False,
            },
            {
                "id": "p2",
                "name": "Removed",
                "isDeleted": True,
            },
        ],
    }
    rows = nomenclature_to_menu_rows(restaurant_id, payload)
    assert len(rows) == 1
    row = rows[0]
    assert row["iiko_product_id"] == "p1"
    assert row["category"] == "Hot dishes"
    assert row["sale_price"] == Decimal("599")
    assert row["food_cost"] == Decimal("180")
    assert row["tax_rate"] == Decimal("0.20")


def test_sales_doc_computes_profit() -> None:
    from app.services.iiko.transformers import sales_doc_to_order

    restaurant_id = uuid.uuid4()
    doc = {
        "id": "ord-1",
        "number": "1001",
        "openDate": "2026-06-02 12:30:00.000",
        "closeDate": "2026-06-02 13:00:00.000",
        "status": "Closed",
        "guestsCount": 2,
        "items": [
            {"productId": "p1", "productName": "Pizza", "amount": 2, "price": 600, "sum": 1140, "discountSum": 60},
        ],
    }
    order_row, item_rows = sales_doc_to_order(restaurant_id, doc, menu_lookup={})
    assert order_row["iiko_order_id"] == "ord-1"
    assert order_row["status"].value == "closed"
    assert len(item_rows) == 1
    line = item_rows[0]
    assert line["quantity"] == Decimal("2")
    assert line["line_revenue"] == Decimal("1140")
    assert order_row["net_revenue"] == Decimal("1140")
    assert order_row["profit"] == Decimal("1140")  # no menu lookup, food_cost = 0
