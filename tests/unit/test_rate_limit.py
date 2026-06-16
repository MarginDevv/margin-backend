"""Rate-limit dependency — key derivation and fail-open behaviour."""
from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("APP_SECRET_KEY", "x" * 32)
os.environ.setdefault("JWT_SECRET_KEY", "y" * 32)


def _fake_request(*, ip: str = "1.2.3.4", forwarded: str | None = None, body: dict | None = None):
    headers = {}
    if forwarded:
        headers["x-forwarded-for"] = forwarded

    async def _json():
        return body or {}

    return SimpleNamespace(
        headers=headers,
        client=SimpleNamespace(host=ip, port=12345),
        scope={"client": (ip, 12345)},
        json=_json,
    )


def test_default_key_uses_peer_ip_when_no_forwarded() -> None:
    from app.core.rate_limit import _default_key

    req = _fake_request(ip="10.0.0.1")
    assert _default_key(req) == "10.0.0.1"


def test_default_key_prefers_first_x_forwarded_for() -> None:
    from app.core.rate_limit import _default_key

    req = _fake_request(ip="10.0.0.1", forwarded="203.0.113.1, 10.0.0.2")
    assert _default_key(req) == "203.0.113.1"


@pytest.mark.asyncio
async def test_by_ip_and_email_combines() -> None:
    from app.core.rate_limit import by_ip_and_email

    key_func = by_ip_and_email("email")
    req = _fake_request(ip="9.9.9.9", body={"email": "  USER@Example.COM  "})
    key = await key_func(req)
    assert key == "9.9.9.9|user@example.com"


@pytest.mark.asyncio
async def test_rate_limit_is_fail_open_when_redis_unavailable() -> None:
    """If Redis is down we should NOT lock everyone out — log and let through."""
    import app.core.rate_limit as rl

    class _FailingRedis:
        def pipeline(self):
            class _P:
                def zremrangebyscore(self, *a, **k): return self
                def zcard(self, *a, **k): return self
                def zadd(self, *a, **k): return self
                def expire(self, *a, **k): return self
                async def execute(self):
                    raise RuntimeError("connection refused")
            return _P()

    rl._redis = _FailingRedis()
    try:
        dep = rl.rate_limit("test.bucket", 1, 60)
        # Two calls in a row; both must succeed without raising.
        await dep(_fake_request())
        await dep(_fake_request())
    finally:
        rl._redis = None
