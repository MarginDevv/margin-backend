"""Bridge between sync Celery tasks and async services."""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import AsyncSessionLocal

T = TypeVar("T")


def run_async(coro: Awaitable[T]) -> T:
    """Execute a coroutine synchronously inside a Celery task."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Inside an existing loop (rare for Celery) — spin a new one.
            new_loop = asyncio.new_event_loop()
            try:
                return new_loop.run_until_complete(coro)  # type: ignore[arg-type]
            finally:
                new_loop.close()
    except RuntimeError:
        pass
    return asyncio.run(coro)  # type: ignore[arg-type]


async def with_session(fn: Callable[[AsyncSession], Awaitable[T]]) -> T:
    """Open a session, run fn, close session, propagate exceptions."""
    async with AsyncSessionLocal() as session:
        return await fn(session)
