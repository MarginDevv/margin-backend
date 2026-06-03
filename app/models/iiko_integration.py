"""iikoCloud integration credentials and sync metadata per restaurant."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimestampedBase

if TYPE_CHECKING:
    from app.models.restaurant import Restaurant


class IikoIntegration(TimestampedBase):
    __tablename__ = "iiko_integrations"

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("restaurants.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

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
    # Latest /api/1/nomenclature `revision` we processed; passed back as
    # ``startRevision`` to fetch only the delta on the next sync. NULL = first run.
    last_menu_revision: Mapped[int | None] = mapped_column(BigInteger)
    # Latest ``maxRevision`` returned by /api/1/deliveries/by_revision (or
    # /api/1/deliveries/by_delivery_date_and_status, both return it). Used as
    # ``startRevision`` on the next incremental orders sync. NULL = first run.
    last_orders_revision: Mapped[int | None] = mapped_column(BigInteger)

    restaurant: Mapped[Restaurant] = relationship(back_populates="iiko_integration")
