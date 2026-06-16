"""Redis-backed sliding-window rate limiter.

Each call records a UNIX-millisecond timestamp in a Redis sorted set, then
counts how many timestamps fall inside the sliding window. When the count
exceeds the configured limit, the dependency raises HTTP 429.

The same Redis client is shared across requests (lazy module-level singleton).

Usage:
    from fastapi import Depends
    from app.core.rate_limit import rate_limit

    @router.post(..., dependencies=[Depends(rate_limit("login", 5, 60))])
    async def login(...): ...

Keys are scoped to (bucket, client identifier). The default identifier is the
caller's IP. Pass a custom `key_func` to scope by something else (e.g. by
email for password-reset endpoints).
"""
from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

import redis.asyncio as aioredis
from fastapi import HTTPException, Request, status

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("rate_limit")

_redis: aioredis.Redis | None = None


def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_uri, decode_responses=True)
    return _redis


def _default_key(request: Request) -> str:
    # X-Forwarded-For first (proxied), fall back to peer.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    if request.client:
        return request.client.host
    return "anonymous"


def rate_limit(
    bucket: str,
    limit: int,
    window_seconds: int,
    *,
    key_func: Callable[[Request], str] | Callable[[Request], Awaitable[str]] | None = None,
):
    """FastAPI dependency factory.

    `bucket`: namespace, e.g. "auth.login".
    `limit`: max calls per window.
    `window_seconds`: window size.
    """

    async def _dep(request: Request) -> None:
        raw = key_func(request) if key_func else _default_key(request)
        if hasattr(raw, "__await__"):
            raw = await raw  # type: ignore[misc]
        key = f"ratelimit:{bucket}:{raw}"
        now_ms = int(time.time() * 1000)
        window_start_ms = now_ms - window_seconds * 1000

        redis = _get_redis()
        try:
            pipe = redis.pipeline()
            pipe.zremrangebyscore(key, 0, window_start_ms)
            pipe.zcard(key)
            pipe.zadd(key, {f"{now_ms}-{request.scope.get('client', ('', 0))[1]}": now_ms})
            pipe.expire(key, window_seconds + 5)
            _, count, _, _ = await pipe.execute()
        except Exception as exc:
            # Fail-open: if Redis is down we don't lock everyone out. Logged
            # so it shows up in alerts.
            logger.error("rate_limit.redis_unavailable", error=str(exc), bucket=bucket)
            return

        if count >= limit:
            retry_after = max(1, window_seconds)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "code": "rate_limited",
                    "message": "Слишком много запросов. Попробуй позже.",
                },
                headers={"Retry-After": str(retry_after)},
            )

    return _dep


def by_ip_and_email(field: str = "email"):
    """Key function that combines IP with a body field (e.g. email).

    The form-field is read on the fly from the request body — the body has
    already been parsed by FastAPI by the time the dependency fires.
    """

    async def _key(request: Request) -> str:
        ip = _default_key(request)
        try:
            body = await request.json()
            value = (body.get(field) or "").lower().strip()
        except Exception:
            value = ""
        return f"{ip}|{value}"

    return _key
