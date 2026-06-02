"""Writeoff document → DB rows."""
from __future__ import annotations

import os
import uuid
from decimal import Decimal

os.environ.setdefault("APP_SECRET_KEY", "x" * 32)
os.environ.setdefault("JWT_SECRET_KEY", "y" * 32)


def test_writeoff_doc_basics() -> None:
    from app.services.iiko.transformers import writeoff_doc_to_rows

    rid = uuid.uuid4()
    doc = {
        "id": "w-001",
        "number": "WR-1",
        "dateIncoming": "2026-06-01 23:45:00.000",
        "storeName": "Главный склад",
        "comment": "Списание просрочки",
        "items": [
            {
                "productId": "milk",
                "productName": "Молоко",
                "amount": 5,
                "sum": 250,
                "writeoffReason": "Истёк срок",
            },
            {
                "productId": "bread",
                "productName": "Хлеб",
                "amount": 10,
                "sum": 200,
            },
        ],
    }
    header, items = writeoff_doc_to_rows(rid, doc, menu_lookup={})

    assert header["restaurant_id"] == rid
    assert header["iiko_document_id"] == "w-001"
    assert header["store_name"] == "Главный склад"
    assert header["total_cost"] == Decimal("450")
    assert header["occurred_at"] is not None

    assert len(items) == 2
    assert items[0]["amount"] == Decimal("5")
    assert items[0]["line_cost"] == Decimal("250")
    assert items[0]["unit_cost"] == Decimal("50")
    assert items[0]["reason"] == "Истёк срок"
    # Bread has no writeoffReason; falls back to document-level comment.
    assert items[1]["reason"] == "Списание просрочки"


def test_writeoff_skips_zero_amount_safely() -> None:
    from app.services.iiko.transformers import writeoff_doc_to_rows

    doc = {
        "id": "w-002",
        "number": "WR-2",
        "items": [
            {"productId": "x", "productName": "X", "amount": 0, "sum": 0},
        ],
    }
    header, items = writeoff_doc_to_rows(uuid.uuid4(), doc, menu_lookup={})
    assert header["total_cost"] == Decimal("0")
    assert items[0]["amount"] == Decimal("0")
    assert items[0]["line_cost"] == Decimal("0")
