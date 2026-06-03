"""Async SQLAlchemy 2.0 engine, session factory and Base."""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, ClassVar

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, MappedAsDataclass

from app.core.config import settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""

    metadata_naming_convention: ClassVar[dict[str, str]] = {
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }


def _create_engine() -> AsyncEngine:
    url = settings.sqlalchemy_database_uri
    kwargs: dict[str, Any] = {"echo": settings.app_debug}
    # SQLite (used in tests) ignores pool_size/max_overflow and errors on them.
    if not url.startswith("sqlite"):
        kwargs.update(pool_pre_ping=True, pool_size=10, max_overflow=20)
    return create_async_engine(url, **kwargs)


engine: AsyncEngine = _create_engine()
AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    autoflush=False,
    class_=AsyncSession,
)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: yields an async session and rolls back on exception."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


__all__ = ["Base", "engine", "AsyncSessionLocal", "get_db", "MappedAsDataclass", "Any"]
