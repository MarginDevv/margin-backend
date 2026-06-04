"""AI-generated daily recommendations for a restaurant."""
from __future__ import annotations

import enum
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Date, Integer, Numeric, String, Text
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimestampedBase
from app.models.mixins import RestaurantMixin

if TYPE_CHECKING:
    from app.models.restaurant import Restaurant


class RecommendationType(str, enum.Enum):
    PRICE_UP = "price_up"
    PRICE_DOWN = "price_down"
    COST_REDUCE = "cost_reduce"
    REMOVE_DISH = "remove_dish"
    PROMOTE_DISH = "promote_dish"
    INVENTORY_LEAK = "inventory_leak"
    STAFF_PERFORMANCE = "staff_performance"
    DAY_OF_WEEK = "day_of_week"


class RecommendationStatus(str, enum.Enum):
    NEW = "new"
    SEEN = "seen"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    APPLIED = "applied"


class RecommendationPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RecommendationCategory(str, enum.Enum):
    MENU = "menu"
    PRICING = "pricing"
    STOCK = "stock"
    PROMOTION = "promotion"
    STAFF = "staff"
    OPERATIONS = "operations"


class RecommendationEffort(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Recommendation(TimestampedBase, RestaurantMixin):
    __tablename__ = "recommendations"

    for_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    type: Mapped[RecommendationType] = mapped_column(
        SqlEnum(
            RecommendationType, name="recommendation_type",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    priority: Mapped[RecommendationPriority] = mapped_column(
        SqlEnum(
            RecommendationPriority, name="recommendation_priority",
            values_callable=lambda e: [m.value for m in e],
        ),
        default=RecommendationPriority.MEDIUM,
        nullable=False,
    )
    category: Mapped[RecommendationCategory] = mapped_column(
        SqlEnum(
            RecommendationCategory, name="recommendation_category",
            values_callable=lambda e: [m.value for m in e],
        ),
        default=RecommendationCategory.OPERATIONS,
        nullable=False,
        index=True,
    )
    effort: Mapped[RecommendationEffort] = mapped_column(
        SqlEnum(
            RecommendationEffort, name="recommendation_effort",
            values_callable=lambda e: [m.value for m in e],
        ),
        default=RecommendationEffort.MEDIUM,
        nullable=False,
    )
    status: Mapped[RecommendationStatus] = mapped_column(
        SqlEnum(
            RecommendationStatus, name="recommendation_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        default=RecommendationStatus.NEW,
        nullable=False,
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str | None] = mapped_column(Text)
    estimated_uplift: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    confidence: Mapped[int] = mapped_column(Integer, default=70, nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSONB)

    restaurant: Mapped[Restaurant] = relationship(back_populates="recommendations")
