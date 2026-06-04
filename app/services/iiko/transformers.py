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
    """Map iiko ``/api/1/nomenclature`` ``products[]`` to menu_items rows.

    iiko product fields used: id, name, productCategoryId, mainUnit,
    sellingPrice, costPrice, vat, isDeleted, seemsRemoved, type.

    Note on food cost: the ``/nomenclature`` payload is sourced from RMS
    Data Exchange, which exports ``costPrice`` already populated with the
    recipe-computed cost (RMS calculates it from the dish's assembly chart
    server-side before exporting). iikoCloud Transport API does **not**
    expose recipes directly — there is no preparation-chart endpoint —
    so ``costPrice`` is our source of truth here. Restaurants that haven't
    set up assembly charts in iikoOffice will have ``costPrice = 0``,
    which the caller should detect and surface as a data-quality warning.
    """
    products: list[dict[str, Any]] = nomenclature.get("products") or []
    category_map = {
        c.get("id"): c.get("name")
        for c in (nomenclature.get("productCategories") or [])
    }

    rows: list[dict[str, Any]] = []
    for p in products:
        # Skip non-sellable types. MODIFIER is excluded because modifiers are
        # add-ons sold as line components of a parent dish — counting them as
        # standalone menu items would double-count revenue in dashboards.
        if p.get("type") and p["type"] not in {"DISH", "GOODS"}:
            continue
        if p.get("isDeleted"):
            continue
        sale_price = _decimal(p.get("sellingPrice") or p.get("price") or 0)
        food_cost = _decimal(
            p.get("costPrice")
            or p.get("estimatedPurchasePrice")
            or 0
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


# --- /api/1/deliveries/by_revision OrderInfo -> orders / order_items ---


# Order.status only has four values in the spec; cancellation is signalled
# by ``cancelInfo`` being non-null, not by a separate status string. Map
# ``Bill`` to NEW because for analytics it's still an open ticket.
_STATUS_MAP: dict[str, OrderStatus] = {
    "New": OrderStatus.NEW,
    "Bill": OrderStatus.NEW,
    "Closed": OrderStatus.CLOSED,
    "Deleted": OrderStatus.DELETED,
}


def sales_doc_to_order(
    restaurant_id: uuid.UUID,
    order_info: dict[str, Any],
    menu_lookup: dict[str, MenuItem],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Convert one ``OrderInfo`` from /deliveries/* into (order_row, item_rows).

    The deliveries endpoints wrap every order in an ``OrderInfo`` envelope
    containing creation metadata; the actual order body sits in
    ``order_info["order"]``. Items use a ``type`` discriminator
    (``Product`` / ``Compound`` / ``Service``):

    * ``Product`` — regular menu item, one DB row per line.
    * ``Compound`` — split dish (e.g. half-half pizza). The parent line has
      ``primaryComponent`` + optional ``secondaryComponent``; each component
      carries its own ``product`` / ``price`` / ``cost`` / ``resultSum``.
      We fan out into one sub-row per component so per-dish stats correctly
      attribute revenue to each half.
    * ``Service`` — service charges (delivery fee, tip lines etc.). Skipped
      so they don't pollute per-dish aggregates.

    Combo bundles are NOT this type discriminator — they appear as ordinary
    Product items tagged with ``comboInformation``, plus a separate
    ``Order.combos[]`` header array. We let the Product items flow through
    as-is; the combo discount is already baked into each constituent line's
    ``resultSum``.

    Aggregates (``net_revenue``, ``profit`` etc.) are recomputed from
    item lines rather than read from ``order.sum`` so the numbers stay
    consistent with the per-line breakdown we persist.
    """
    order_data: dict[str, Any] = order_info.get("order") or {}

    opened_at = _parse_dt(order_data.get("whenCreated"))
    closed_at = _parse_dt(order_data.get("whenClosed"))
    status = _derive_status(order_data)

    item_rows: list[dict[str, Any]] = []
    total_gross = Decimal("0")
    total_discount = Decimal("0")
    total_net = Decimal("0")
    total_cost = Decimal("0")

    for line in order_data.get("items") or []:
        if line.get("deleted"):  # item was struck from the order
            continue

        line_type = line.get("type") or "Product"
        if line_type == "Product":
            sub_rows = [_build_item_row(line, menu_lookup)]
        elif line_type == "Compound":
            sub_rows = _expand_compound(line, menu_lookup)
        else:
            # Service charges and any future discriminator values.
            continue

        for row, gross in sub_rows:
            item_rows.append(row)
            total_gross += gross
            total_discount += row["discount_amount"]
            total_net += row["line_revenue"]
            total_cost += row["line_cost"]

    operator = order_data.get("operator") or {}

    order_row = {
        "restaurant_id": restaurant_id,
        "iiko_order_id": order_info.get("id") or order_data.get("id"),
        "iiko_order_number": (
            str(order_data["number"]) if order_data.get("number") is not None else None
        ),
        "opened_at": opened_at or closed_at,
        "closed_at": closed_at,
        "status": status,
        "guests_count": int((order_data.get("guestsInfo") or {}).get("count") or 0),
        "waiter_name": operator.get("name"),
        "gross_revenue": total_gross,
        "discount_amount": total_discount,
        "net_revenue": total_net,
        "total_food_cost": total_cost,
        "profit": total_net - total_cost,
    }
    return order_row, item_rows


def _build_item_row(
    line: dict[str, Any], menu_lookup: dict[str, MenuItem]
) -> tuple[dict[str, Any], Decimal]:
    """Map a ``ProductOrderItem`` into ``(item_row, gross_for_aggregates)``."""
    product = line.get("product") or {}
    menu_item = _lookup(menu_lookup, product.get("id"))
    return _make_row(
        product=product,
        menu_item=menu_item,
        qty=_decimal(line.get("amount") or 1),
        unit_price=_decimal(line.get("price") or 0),
        unit_food_cost=_resolve_unit_cost(line.get("cost"), menu_item),
        result_sum=line.get("resultSum"),
    )


def _expand_compound(
    line: dict[str, Any], menu_lookup: dict[str, MenuItem]
) -> list[tuple[dict[str, Any], Decimal]]:
    """Expand a ``CompoundOrderItem`` into one sub-row per component.

    Both components are priced individually; the parent line's ``amount``
    is the count of *whole* compound items. We multiply each component's
    per-unit ``price`` by that quantity, which matches how iiko bills the
    line (component prices are already split: a half-half pizza component
    holds half the menu price).
    """
    qty = _decimal(line.get("amount") or 1)
    rows: list[tuple[dict[str, Any], Decimal]] = []
    for key in ("primaryComponent", "secondaryComponent"):
        comp = line.get(key)
        if not comp:
            continue
        product = comp.get("product") or {}
        menu_item = _lookup(menu_lookup, product.get("id"))
        rows.append(
            _make_row(
                product=product,
                menu_item=menu_item,
                qty=qty,
                unit_price=_decimal(comp.get("price") or 0),
                unit_food_cost=_resolve_unit_cost(comp.get("cost"), menu_item),
                result_sum=comp.get("resultSum"),
            )
        )
    return rows


def _make_row(
    *,
    product: dict[str, Any],
    menu_item: MenuItem | None,
    qty: Decimal,
    unit_price: Decimal,
    unit_food_cost: Decimal,
    result_sum: Any,
) -> tuple[dict[str, Any], Decimal]:
    """Build an item_row dict + return the gross used for aggregates."""
    gross = unit_price * qty
    # ``resultSum`` is the line total the guest actually pays (price minus
    # discounts plus surcharges). Use it as line_revenue when present so we
    # don't have to reconstruct the discount from modifier rows.
    line_revenue = _decimal(result_sum) if result_sum is not None else gross
    line_discount = gross - line_revenue if line_revenue < gross else Decimal("0")
    line_cost = unit_food_cost * qty
    row = {
        "menu_item_id": menu_item.id if menu_item else None,
        "iiko_product_id": product.get("id"),
        "name_snapshot": (
            product.get("name")
            or (menu_item.name if menu_item else "Unknown")
        ),
        "quantity": qty,
        "unit_price": unit_price,
        "unit_food_cost": unit_food_cost,
        "discount_amount": line_discount,
        "line_revenue": line_revenue,
        "line_cost": line_cost,
        "line_profit": line_revenue - line_cost,
    }
    return row, gross


def _resolve_unit_cost(line_cost: Any, menu_item: MenuItem | None) -> Decimal:
    """Use the iiko-reported per-unit cost; fall back to the menu snapshot."""
    if line_cost is not None:
        return _decimal(line_cost)
    return menu_item.food_cost if menu_item else Decimal("0")


def _lookup(menu_lookup: dict[str, MenuItem], pid: Any) -> MenuItem | None:
    """Safe menu_lookup access — narrows ``Any | None`` from JSON payloads."""
    return menu_lookup.get(pid) if isinstance(pid, str) else None


def _derive_status(order_data: dict[str, Any]) -> OrderStatus:
    """Map iiko's split (``status`` enum + separate ``cancelInfo``) to ours.

    A non-null ``cancelInfo`` wins over the raw status string: iiko marks
    cancelled tickets with ``status=Deleted`` AND ``cancelInfo`` populated,
    but the latter is the unambiguous signal.
    """
    if order_data.get("cancelInfo"):
        return OrderStatus.CANCELED
    raw = order_data.get("status") or "New"
    return _STATUS_MAP.get(raw, OrderStatus.NEW)


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
        # iiko uses 'YYYY-MM-DD HH:MM:SS.fff' without TZ for local-terminal times.
        try:
            dt = datetime.strptime(text, "%Y-%m-%d %H:%M:%S.%f")
        except ValueError:
            try:
                dt = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
