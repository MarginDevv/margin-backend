"""Reusable column mixins for ORM models."""
from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column


class RestaurantMixin:
    """Adds a ``restaurant_id`` FK column pointing at ``restaurants.id``.

    The column is indexed and non-nullable with ``ON DELETE CASCADE``.
    Use for the common many-to-one case (``Restaurant`` has many of these).

    Models that need a 1:1 relationship to ``Restaurant`` (e.g. ``Subscription``,
    ``IikoIntegration``) should declare ``restaurant_id`` inline with
    ``unique=True`` instead of using this mixin.
    """

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("restaurants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


__all__ = ["RestaurantMixin"]
