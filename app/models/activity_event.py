"""Activity feed: append-only log of events visible in the web dashboard."""
from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Enum as SqlEnum
from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimestampedBase

if TYPE_CHECKING:
    from app.models.restaurant import Restaurant
    from app.models.user import User


class ActivityKind(str, enum.Enum):
    IIKO_SYNC_SUCCESS = "iiko.sync.success"
    IIKO_SYNC_FAILED = "iiko.sync.failed"
    REPORT_DAILY_BUILT = "report.daily.built"
    REPORT_WEEKLY_BUILT = "report.weekly.built"
    RECOMMENDATIONS_GENERATED = "recommendations.generated"
    RECOMMENDATION_STATUS_CHANGED = "recommendation.status_changed"
    TELEGRAM_DELIVERY_SENT = "telegram.delivery.sent"
    TELEGRAM_DELIVERY_FAILED = "telegram.delivery.failed"
    TELEGRAM_LINKED = "telegram.linked"
    TELEGRAM_UNLINKED = "telegram.unlinked"
    MENU_ITEM_UPDATED = "menu.item.updated"


class ActivitySeverity(str, enum.Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class ActivityEvent(TimestampedBase):
    __tablename__ = "activity_events"

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("restaurants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    kind: Mapped[ActivityKind] = mapped_column(
        SqlEnum(ActivityKind, name="activity_kind", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        index=True,
    )
    severity: Mapped[ActivitySeverity] = mapped_column(
        SqlEnum(ActivitySeverity, name="activity_severity", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=ActivitySeverity.INFO,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    restaurant: Mapped["Restaurant"] = relationship()
    actor: Mapped["User | None"] = relationship()
