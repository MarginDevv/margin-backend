"""Reusable column mixins for ORM models."""
from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, declared_attr, mapped_column


class RestaurantMixin:
    """Adds a ``restaurant_id`` FK column pointing at ``restaurants.id``.

    The column is indexed and non-nullable with ``ON DELETE CASCADE``.
    Subclasses that need a one-to-one relationship to ``Restaurant``
    should set ``__restaurant_unique__ = True`` to emit a unique
    constraint on the column.
    """

    __restaurant_unique__: bool = False

    @declared_attr
    def restaurant_id(cls) -> Mapped[uuid.UUID]:
        return mapped_column(
            UUID(as_uuid=True),
            ForeignKey("restaurants.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
            unique=cls.__restaurant_unique__,
        )


__all__ = ["RestaurantMixin"]
