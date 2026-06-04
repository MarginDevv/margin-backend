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

    # Organization ID inside iiko (one integration → primary organization).
    organization_id: Mapped[str | None] = mapped_column(String(64), index=True)

    # /api/v2/access_token credentials. All three are issued together:
    #   api_key       — generated in iikoWeb under "Integrations → API Keys".
    #   app_id        — UUID issued by the iiko Developer Portal at app creation.
    #   client_secret — secret shown only once at portal-app creation time.
    # Nullable at the DB layer to keep migration 0009 reversible; the sync
    # service raises IikoIntegrationError if any is missing at call time.
    # client_secret is stored encrypted (app.utils.crypto.encrypt_str).
    api_key: Mapped[str | None] = mapped_column(String(255))
    app_id: Mapped[str | None] = mapped_column(String(64))
    client_secret: Mapped[str | None] = mapped_column(String(512))

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
