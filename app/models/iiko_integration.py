"""iikoCloud integration credentials and sync metadata per restaurant."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimestampedBase
from app.models.mixins import RestaurantMixin

if TYPE_CHECKING:
    from app.models.restaurant import Restaurant


class IikoIntegration(TimestampedBase, RestaurantMixin):
    __tablename__ = "iiko_integrations"
    __restaurant_unique__ = True

    # iikoCloud API login (apiLogin) — secret, stored as-is for now (encrypt before prod).
    api_login: Mapped[str] = mapped_column(String(255), nullable=False)
    # Organization ID inside iiko (one integration → primary organization).
    organization_id: Mapped[str | None] = mapped_column(String(64), index=True)
    # Default terminal group id used for queries.
    terminal_group_id: Mapped[str | None] = mapped_column(String(64))

    # Cached access token + its expiry.
    access_token: Mapped[str | None] = mapped_column(String(512))
    access_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sync_error: Mapped[str | None] = mapped_column(String(1024))

    restaurant: Mapped["Restaurant"] = relationship(back_populates="iiko_integration")
