"""Webhook endpoint secret-verification."""
from __future__ import annotations

import importlib
import os

os.environ.setdefault("APP_SECRET_KEY", "x" * 32)
os.environ.setdefault("JWT_SECRET_KEY", "y" * 32)
os.environ["TELEGRAM_BOT_TOKEN"] = "1:fake"
os.environ["TELEGRAM_WEBHOOK_SECRET"] = "test-secret-123"


def _reload_settings():
    from app.core import config

    importlib.reload(config)
    # Patch downstream modules that imported `settings` directly at import time.
    from app.api.v1.endpoints import telegram_webhook

    importlib.reload(telegram_webhook)
    return telegram_webhook


def _client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    telegram_webhook = _reload_settings()
    app = FastAPI()
    app.include_router(telegram_webhook.router, prefix="/api/v1/webhooks/telegram")
    return TestClient(app)


def test_rejects_wrong_url_secret() -> None:
    client = _client()
    resp = client.post(
        "/api/v1/webhooks/telegram/wrong-secret",
        json={"update_id": 1},
        headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret-123"},
    )
    assert resp.status_code == 401


def test_rejects_wrong_header_secret() -> None:
    client = _client()
    resp = client.post(
        "/api/v1/webhooks/telegram/test-secret-123",
        json={"update_id": 1},
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
    )
    assert resp.status_code == 401


def test_rejects_missing_header_secret() -> None:
    client = _client()
    resp = client.post(
        "/api/v1/webhooks/telegram/test-secret-123",
        json={"update_id": 1},
    )
    assert resp.status_code == 401
