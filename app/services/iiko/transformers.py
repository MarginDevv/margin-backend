"""Convert iiko payloads to DB-ready dicts."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from app.models.menu_item import MenuItem
from app.models.order import OrderStatus

# --- nomenclature -> menu_items rows ---


def nomenclature_to_menu_rows(
    restaurant_id: uuid.UUID, nomenclature: dict[str, Any]
) -> list[dict[str, Any]]:
    """Map iiko nomenclature 'products' to menu_items upsert rows.

    Food cost is computed from assembly charts when available — recursively,
    so a composite dish that itself uses semi-finished products also gets the
    full ingredient cost rolled up. If a product has no chart, we fall back
    to `costPrice` / `estimatedPurchasePrice` from the nomenclature itself.
    """
    products: list[dict[str, Any]] = nomenclature.get("products") or []
    category_map = {
        c.get("id"): c.get("name")
        for c in (nomenclature.get("productCategories") or [])
    }

    # Build a lookup that helps us compute recipe-based food cost.
    cost_lookup = _build_cost_lookup(products)

    rows: list[dict[str, Any]] = []
    for p in products:
        if p.get("type") and p["type"] not in {"DISH", "GOODS", "MODIFIER"}:
            continue
        if p.get("isDeleted"):
            continue
        sale_price = _decimal(p.get("sellingPrice") or p.get("price") or 0)
        food_cost = _compute_food_cost(p, cost_lookup) or _decimal(
            p.get("costPrice") or p.get("estimatedPurchasePrice") or 0
        )
        rows.append(
            {
                "restaurant_id": restaurant_id,
                "iiko_product_id": p["id"],
                "name": p.get("name") or "Unnamed",
                "category": category_map.get(p.get("productCategoryId"))
                or p.get("groupName"),
                "unit": (p.get("mainUnit") or {}).get("name")
                if isinstance(p.get("mainUnit"), dict)
                else p.get("mainUnit"),
                "sale_price": sale_price,
                "food_cost": food_cost,
                "tax_rate": _decimal(p.get("vat") or 0) / Decimal("100"),
                "is_active": not p.get("seemsRemoved", False),
            }
        )
    return rows


# --- sales document -> orders / order_items ---


_STATUS_MAP: dict[str, OrderStatus] = {
    "Closed": OrderStatus.CLOSED,
    "New": OrderStatus.NEW,
    "Cancelled": OrderStatus.CANCELED,
    "Deleted": OrderStatus.DELETED,
}


def sales_doc_to_order(
    restaurant_id: uuid.UUID,
    doc: dict[str, Any],
    menu_lookup: dict[str, MenuItem],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Convert a single sales document to (order_row, [item_rows]).

    Per-line profit is computed as: revenue (net of discount and tax) - food_cost*qty.
    Net revenue = sum of line_revenue. Aggregates are recomputed here so that
    we don't depend on iiko-side fields being present.
    """
    opened_at = _parse_dt(doc.get("openDate"))
    closed_at = _parse_dt(doc.get("closeDate") or doc.get("closeTime"))
    status_raw = doc.get("status") or ("Closed" if closed_at else "New")
    status = _STATUS_MAP.get(status_raw, OrderStatus.NEW)

    items_raw: list[dict[str, Any]] = doc.get("items") or doc.get("productItems") or []

    item_rows: list[dict[str, Any]] = []
    total_gross = Decimal("0")
    total_discount = Decimal("0")
    total_net = Decimal("0")
    total_cost = Decimal("0")

    for line in items_raw:
        iiko_product_id = line.get("productId") or line.get("product", {}).get("id")
        menu_item = menu_lookup.get(iiko_product_id) if iiko_product_id else None
        qty = _decimal(line.get("amount") or line.get("quantity") or 1)
        unit_price = _decimal(
            line.get("price")
            or line.get("priceWithoutDiscount")
            or (menu_item.sale_price if menu_item else 0)
        )
        gross = unit_price * qty
        discount = _decimal(line.get("discountSum") or line.get("discount") or 0)
        # Tax pre-stripped: iiko `sum` is usually the line revenue net of discount.
        line_revenue = _decimal(line.get("sum") or (gross - discount))
        unit_food_cost = menu_item.food_cost if menu_item else Decimal("0")
        line_cost = unit_food_cost * qty
        line_profit = line_revenue - line_cost

        item_rows.append(
            {
                "menu_item_id": menu_item.id if menu_item else None,
                "iiko_product_id": iiko_product_id,
                "name_snapshot": (
                    line.get("productName")
                    or (menu_item.name if menu_item else "Unknown")
                ),
                "quantity": qty,
                "unit_price": unit_price,
                "unit_food_cost": unit_food_cost,
                "discount_amount": discount,
                "line_revenue": line_revenue,
                "line_cost": line_cost,
                "line_profit": line_profit,
            }
        )
        total_gross += gross
        total_discount += discount
        total_net += line_revenue
        total_cost += line_cost

    order_row = {
        "restaurant_id": restaurant_id,
        "iiko_order_id": doc.get("id") or doc.get("orderId") or doc.get("number"),
        "iiko_order_number": str(doc.get("number")) if doc.get("number") else None,
        "opened_at": opened_at or closed_at,
        "closed_at": closed_at,
        "status": status,
        "guests_count": int(doc.get("guestsCount") or doc.get("guests") or 0),
        "waiter_name": doc.get("waiterName") or doc.get("waiter", {}).get("name"),
        "gross_revenue": total_gross,
        "discount_amount": total_discount,
        "net_revenue": total_net,
        "total_food_cost": total_cost,
        "profit": total_net - total_cost,
    }
    return order_row, item_rows


# --- writeoffs document -> rows ---


def writeoff_doc_to_rows(
    restaurant_id: uuid.UUID,
    doc: dict[str, Any],
    menu_lookup: dict[str, MenuItem],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Convert a single writeoff document to (header, [items])."""
    items_raw: list[dict[str, Any]] = doc.get("items") or []
    item_rows: list[dict[str, Any]] = []
    total = Decimal("0")

    for line in items_raw:
        iiko_product_id = line.get("productId")
        menu_item = menu_lookup.get(iiko_product_id) if iiko_product_id else None
        amount = _decimal(line.get("amount") or line.get("amountFactor") or 0)
        unit_cost = (
            _decimal(line.get("sum")) / amount
            if amount and line.get("sum")
            else (menu_item.food_cost if menu_item else Decimal("0"))
        )
        line_cost = _decimal(line.get("sum") or unit_cost * amount)
        total += line_cost
        item_rows.append(
            {
                "menu_item_id": menu_item.id if menu_item else None,
                "iiko_product_id": iiko_product_id,
                "name_snapshot": (
                    line.get("productName")
                    or (menu_item.name if menu_item else "Unknown")
                ),
                "amount": amount,
                "unit_cost": unit_cost,
                "line_cost": line_cost,
                "reason": line.get("writeoffReason") or doc.get("comment"),
            }
        )

    header = {
        "restaurant_id": restaurant_id,
        "iiko_document_id": doc.get("id") or doc.get("documentId") or doc.get("number"),
        "iiko_document_number": str(doc.get("number")) if doc.get("number") else None,
        "occurred_at": _parse_dt(doc.get("dateIncoming") or doc.get("documentDate")),
        "store_name": doc.get("storeName") or (doc.get("store") or {}).get("name"),
        "total_cost": total,
        "comment": doc.get("comment"),
    }
    return header, item_rows


# --- assembly chart -> food cost ---


def _build_cost_lookup(products: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Map product_id -> minimal info needed to compute recipe cost."""
    return {p["id"]: p for p in products if p.get("id")}


def _compute_food_cost(
    product: dict[str, Any],
    lookup: dict[str, dict[str, Any]],
    *,
    _seen: frozenset[str] = frozenset(),
) -> Decimal | None:
    """Recursively compute food cost from an assembly chart.

    Returns None if the product has no chart and no cost data — caller falls
    back to costPrice from the nomenclature.

    iiko nomenclature exposes recipes either as:
      product["assemblyCharts"] : [ { items: [ { productId, amountIn } ] } ]
    or as a single `assemblyChart` field. We accept both. Cycles are guarded
    by the `_seen` frozenset (mostly defensive — iiko prevents them).
    """
    product_id = product.get("id")
    if not product_id:
        return None
    if product_id in _seen:
        return None  # cycle — should never happen, but stay safe

    charts = product.get("assemblyCharts") or []
    if not charts and product.get("assemblyChart"):
        charts = [product["assemblyChart"]]
    if not charts:
        return None

    # Take the first chart — iiko returns multiple only for size variations.
    items = (charts[0] or {}).get("items") or []
    if not items:
        return None

    total = Decimal("0")
    next_seen = _seen | {product_id}
    for ing in items:
        ing_id = ing.get("productId") or (ing.get("product") or {}).get("id")
        amount = _decimal(ing.get("amountIn") or ing.get("amount") or 0)
        if amount == 0:
            continue
        ing_product = lookup.get(ing_id) if ing_id else None
        if not ing_product:
            # Unknown ingredient — skip; we'll undercount but at least not crash.
            continue
        nested = _compute_food_cost(ing_product, lookup, _seen=next_seen)
        unit_cost = (
            nested
            if nested is not None
            else _decimal(
                ing_product.get("costPrice")
                or ing_product.get("estimatedPurchasePrice")
                or 0
            )
        )
        total += unit_cost * amount

    return total if total > 0 else None


# --- helpers ---


def _decimal(value: Any) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _parse_dt(value: Any) -> datetime | None:
    from datetime import UTC

    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    text = str(value).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        # iiko sometimes uses 'YYYY-MM-DD HH:MM:SS.fff' without TZ.
        try:
            dt = datetime.strptime(text, "%Y-%m-%d %H:%M:%S.%f")
        except ValueError:
            try:
                dt = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
