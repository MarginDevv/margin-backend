"""Billing stub returns 404 with a marker code."""
from __future__ import annotations

import os

os.environ.setdefault("APP_SECRET_KEY", "x" * 32)
os.environ.setdefault("JWT_SECRET_KEY", "y" * 32)


def _client():
    from app.api.v1.endpoints import billing
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(billing.router, prefix="/api/v1/billing")
    return TestClient(app)


def test_plans_returns_404() -> None:
    client = _client()
    resp = client.get("/api/v1/billing/plans")
    assert resp.status_code == 404
    body = resp.json()
    assert body["detail"]["code"] == "billing_not_implemented"


def test_subscription_get_returns_404() -> None:
    client = _client()
    resp = client.get("/api/v1/billing/subscription")
    assert resp.status_code == 404


def test_subscription_post_returns_404() -> None:
    client = _client()
    resp = client.post("/api/v1/billing/subscription")
    assert resp.status_code == 404


def test_invoices_returns_404() -> None:
    client = _client()
    resp = client.get("/api/v1/billing/invoices")
    assert resp.status_code == 404


def test_webhook_returns_404() -> None:
    client = _client()
    resp = client.post("/api/v1/billing/webhooks/yookassa")
    assert resp.status_code == 404
