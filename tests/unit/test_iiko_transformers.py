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
                "type": "DISH",
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


def test_nomenclature_skips_modifiers() -> None:
    """Modifiers are line components of a parent dish; counting them as
    standalone menu items would double-count revenue in dashboards."""
    from app.services.iiko.transformers import nomenclature_to_menu_rows

    payload = {
        "productCategories": [],
        "products": [
            {"id": "p1", "name": "Dish", "type": "DISH",
             "sellingPrice": 500, "costPrice": 150},
            {"id": "p2", "name": "Extra cheese", "type": "MODIFIER",
             "sellingPrice": 50, "costPrice": 10},
            {"id": "p3", "name": "Service", "type": "SERVICE",
             "sellingPrice": 0},
        ],
    }
    rows = nomenclature_to_menu_rows(uuid.uuid4(), payload)
    names = {r["name"] for r in rows}
    assert names == {"Dish"}


# ---- sales_doc_to_order: new /api/1/deliveries/* shape ----


def _order_info(
    *,
    order_id: str = "ord-1",
    number: int = 1001,
    status: str = "Closed",
    cancel_info: dict | None = None,
    when_created: str = "2026-06-02 12:30:00.000",
    when_closed: str | None = "2026-06-02 13:00:00.000",
    guests_count: int = 2,
    operator_name: str = "Anna",
    items: list[dict] | None = None,
) -> dict:
    return {
        "id": order_id,
        "creationStatus": "Success",
        "order": {
            "id": order_id,
            "number": number,
            "status": status,
            "cancelInfo": cancel_info,
            "whenCreated": when_created,
            "whenClosed": when_closed,
            "guestsInfo": {"count": guests_count},
            "operator": {"name": operator_name},
            "items": items if items is not None else [],
            "sum": 0,
        },
    }


def _product_item(
    *,
    product_id: str = "p1",
    name: str = "Pizza",
    amount: float = 2,
    price: float = 600,
    cost: float = 200,
    result_sum: float | None = None,
    deleted: bool = False,
    item_type: str | None = "Product",
) -> dict:
    line: dict = {
        "amount": amount,
        "price": price,
        "cost": cost,
        "product": {"id": product_id, "name": name},
    }
    if item_type is not None:
        line["type"] = item_type
    if result_sum is not None:
        line["resultSum"] = result_sum
    if deleted:
        line["deleted"] = {"comment": "void"}
    return line


def test_sales_doc_computes_profit() -> None:
    from app.services.iiko.transformers import sales_doc_to_order

    restaurant_id = uuid.uuid4()
    info = _order_info(
        items=[_product_item(amount=2, price=600, cost=200, result_sum=1140)],
    )
    order_row, item_rows = sales_doc_to_order(restaurant_id, info, menu_lookup={})

    assert order_row["iiko_order_id"] == "ord-1"
    assert order_row["iiko_order_number"] == "1001"
    assert order_row["status"].value == "closed"
    assert order_row["guests_count"] == 2
    assert order_row["waiter_name"] == "Anna"

    assert len(item_rows) == 1
    line = item_rows[0]
    assert line["quantity"] == Decimal("2")
    assert line["line_revenue"] == Decimal("1140")
    assert line["line_cost"] == Decimal("400")          # cost * qty = 200 * 2
    assert line["line_profit"] == Decimal("740")
    assert line["discount_amount"] == Decimal("60")     # gross 1200 - net 1140

    # Aggregates are computed from items, not from order.sum
    assert order_row["net_revenue"] == Decimal("1140")
    assert order_row["total_food_cost"] == Decimal("400")
    assert order_row["profit"] == Decimal("740")


def test_sales_doc_maps_bill_status_to_new() -> None:
    """``Bill`` means receipt printed but not yet paid; for analytics it's
    still an open ticket, same as ``New``."""
    from app.services.iiko.transformers import sales_doc_to_order

    info = _order_info(status="Bill", when_closed=None,
                       items=[_product_item()])
    order_row, _ = sales_doc_to_order(uuid.uuid4(), info, menu_lookup={})
    assert order_row["status"].value == "new"


def test_sales_doc_uses_cancel_info_not_status_for_cancellation() -> None:
    """Order.status enum has no 'Cancelled' value; cancellation is signalled
    by cancelInfo being non-null."""
    from app.services.iiko.transformers import sales_doc_to_order

    info = _order_info(
        status="Deleted",
        cancel_info={
            "cause": {"id": "x", "name": "Customer changed mind"},
            "comment": "...",
            "whenCancelled": "2026-06-02 13:05:00.000",
        },
        items=[_product_item()],
    )
    order_row, _ = sales_doc_to_order(uuid.uuid4(), info, menu_lookup={})
    assert order_row["status"].value == "canceled"


def test_sales_doc_skips_non_product_items() -> None:
    """Combo wrappers and service items must not contribute to per-dish stats."""
    from app.services.iiko.transformers import sales_doc_to_order

    info = _order_info(items=[
        _product_item(product_id="p1", price=500, cost=150),
        {"type": "Service", "amount": 1, "price": 100, "cost": 0,
         "product": {"id": "srv", "name": "Service charge"}},
        {"type": "Compound", "amount": 1, "price": 0, "cost": 0,
         "primaryComponent": {}},
    ])
    _, item_rows = sales_doc_to_order(uuid.uuid4(), info, menu_lookup={})
    assert len(item_rows) == 1
    assert item_rows[0]["iiko_product_id"] == "p1"


def test_sales_doc_skips_voided_items() -> None:
    """``deleted`` non-null means the line was struck from the order."""
    from app.services.iiko.transformers import sales_doc_to_order

    info = _order_info(items=[
        _product_item(product_id="kept"),
        _product_item(product_id="voided", deleted=True),
    ])
    _, item_rows = sales_doc_to_order(uuid.uuid4(), info, menu_lookup={})
    assert {r["iiko_product_id"] for r in item_rows} == {"kept"}


def test_sales_doc_handles_open_order_without_close_time() -> None:
    from app.services.iiko.transformers import sales_doc_to_order

    info = _order_info(status="New", when_closed=None,
                       items=[_product_item()])
    order_row, _ = sales_doc_to_order(uuid.uuid4(), info, menu_lookup={})
    assert order_row["closed_at"] is None
    assert order_row["opened_at"] is not None
    assert order_row["status"].value == "new"


def test_sales_doc_falls_back_to_menu_cost_when_iiko_omits() -> None:
    """If iiko doesn't send 'cost' on the line (e.g. older firmware), fall
    back to the per-restaurant menu snapshot we maintain."""
    from app.models.menu_item import MenuItem
    from app.services.iiko.transformers import sales_doc_to_order

    menu_item = MenuItem(
        restaurant_id=uuid.uuid4(),
        iiko_product_id="p1",
        name="Pizza",
        sale_price=Decimal("600"),
        food_cost=Decimal("250"),
        tax_rate=Decimal("0"),
        is_active=True,
    )
    line = _product_item(product_id="p1", amount=2, price=600, cost=None,
                         result_sum=1200)
    # remove 'cost' entirely
    line.pop("cost")
    info = _order_info(items=[line])
    _, item_rows = sales_doc_to_order(uuid.uuid4(), info,
                                       menu_lookup={"p1": menu_item})
    assert item_rows[0]["unit_food_cost"] == Decimal("250")
    assert item_rows[0]["line_cost"] == Decimal("500")
