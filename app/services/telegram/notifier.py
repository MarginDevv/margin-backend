"""High-level Telegram notifier: builds digests and sends to all subscribers.

A subscriber is a user with:
  - a verified `telegram_chat_id`,
  - a membership in the restaurant where `telegram_notifications = True`.

Delivery is idempotent: a `TelegramDelivery` row with UNIQUE
(restaurant_id, user_id, kind, for_date) guards against double-sends across
retried Celery tasks.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import case, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.models.activity_event import ActivityKind, ActivitySeverity
from app.models.recommendation import (
    Recommendation,
    RecommendationPriority,
    RecommendationStatus,
)
from app.models.report import ReportPeriod
from app.models.telegram import DeliveryKind, TelegramDelivery
from app.models.user import User
from app.models.user_restaurant_role import UserRestaurantRole
from app.repositories.report_repo import ReportRepository
from app.repositories.restaurant_repo import RestaurantRepository
from app.services.activity.event_service import ActivityEventService
from app.services.telegram.client import (
    TelegramApiError,
    TelegramClient,
    TelegramRecipientError,
)
from app.services.telegram.formatter import render_daily_digest
from app.utils.datetime import now_utc

logger = get_logger("telegram.notifier")


@dataclass
class DeliveryStats:
    queued: int = 0
    sent: int = 0
    skipped_no_chat: int = 0
    skipped_already_sent: int = 0
    skipped_disabled: int = 0
    failed: int = 0


def dashboard_url(restaurant_id: uuid.UUID) -> str | None:
    base = (settings.app_base_url or "").rstrip("/")
    if not base:
        return None
    return f"{base}/r/{restaurant_id}"


async def fetch_top_recommendations(
    session: AsyncSession,
    restaurant_id: uuid.UUID,
    for_date: date,
    *,
    limit: int = 3,
) -> list[Recommendation]:
    """Return up to `limit` recommendations ordered by priority then confidence."""
    priority_rank = case(
        (Recommendation.priority == RecommendationPriority.CRITICAL, 0),
        (Recommendation.priority == RecommendationPriority.HIGH, 1),
        (Recommendation.priority == RecommendationPriority.MEDIUM, 2),
        (Recommendation.priority == RecommendationPriority.LOW, 3),
        else_=4,
    )
    stmt = (
        select(Recommendation)
        .where(
            Recommendation.restaurant_id == restaurant_id,
            Recommendation.for_date == for_date,
            Recommendation.status.in_(
                [RecommendationStatus.NEW, RecommendationStatus.SEEN]
            ),
        )
        .order_by(priority_rank, Recommendation.confidence.desc())
        .limit(limit)
    )
    return list((await session.scalars(stmt)).all())


class TelegramNotifier:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def deliver_daily_digest(
        self, restaurant_id: uuid.UUID, for_date: date
    ) -> DeliveryStats:
        stats = DeliveryStats()

        restaurant = await RestaurantRepository(self.session).get(restaurant_id)
        if not restaurant:
            raise NotFoundError("Restaurant not found")

        report = await ReportRepository(self.session).get(
            restaurant_id, ReportPeriod.DAILY, for_date
        )
        if not report:
            logger.info(
                "telegram.digest.skip_no_report",
                restaurant_id=str(restaurant_id),
                for_date=for_date.isoformat(),
            )
            return stats

        recs = await fetch_top_recommendations(
            self.session, restaurant_id, for_date, limit=3
        )

        subscribers = await self._list_subscribers(restaurant_id)
        if not subscribers:
            logger.info(
                "telegram.digest.no_subscribers",
                restaurant_id=str(restaurant_id),
            )
            return stats

        text = render_daily_digest(
            restaurant.name,
            for_date,
            report,
            recs,
            currency=restaurant.currency,
            dashboard_url=dashboard_url(restaurant_id),
        )

        events = ActivityEventService(self.session)

        async with TelegramClient() as client:
            for user, membership in subscribers:
                stats.queued += 1
                if user.telegram_chat_id is None:
                    stats.skipped_no_chat += 1
                    continue
                if not membership.telegram_notifications:
                    stats.skipped_disabled += 1
                    continue

                claimed = await self._claim_delivery(
                    restaurant_id,
                    user.id,
                    DeliveryKind.DAILY_DIGEST,
                    for_date,
                    user.telegram_chat_id,
                )
                if claimed is None:
                    stats.skipped_already_sent += 1
                    continue

                try:
                    result = await client.send_message(user.telegram_chat_id, text)
                except TelegramRecipientError as exc:
                    claimed.error = str(exc)
                    await self.session.commit()
                    stats.failed += 1
                    await events.emit(
                        restaurant_id,
                        ActivityKind.TELEGRAM_DELIVERY_FAILED,
                        title=f"Не удалось доставить дайджест {user.email}",
                        severity=ActivitySeverity.WARNING,
                        payload={"reason": str(exc)},
                    )
                    await self.session.commit()
                    continue
                except TelegramApiError as exc:
                    claimed.error = str(exc)
                    await self.session.commit()
                    stats.failed += 1
                    logger.error(
                        "telegram.send.failed",
                        user_id=str(user.id),
                        restaurant_id=str(restaurant_id),
                        error=str(exc),
                    )
                    continue

                claimed.sent_at = now_utc()
                claimed.telegram_message_id = (
                    int(result.get("message_id") or 0) or None
                )
                claimed.payload = {"report_id": str(report.id), "rec_count": len(recs)}
                stats.sent += 1
                await self.session.commit()

            if stats.sent:
                await events.emit(
                    restaurant_id,
                    ActivityKind.TELEGRAM_DELIVERY_SENT,
                    title=f"Дайджест за {for_date.isoformat()} отправлен в Telegram",
                    payload={
                        "sent": stats.sent,
                        "for_date": for_date.isoformat(),
                        "kind": DeliveryKind.DAILY_DIGEST.value,
                    },
                )
                await self.session.commit()

        return stats

    async def _claim_delivery(
        self,
        restaurant_id: uuid.UUID,
        user_id: uuid.UUID,
        kind: DeliveryKind,
        for_date: date,
        chat_id: int,
    ) -> TelegramDelivery | None:
        stmt = (
            pg_insert(TelegramDelivery)
            .values(
                restaurant_id=restaurant_id,
                user_id=user_id,
                kind=kind,
                for_date=for_date.isoformat(),
                chat_id=chat_id,
            )
            .on_conflict_do_nothing(constraint="uq_telegram_delivery")
            .returning(TelegramDelivery.id)
        )
        result = await self.session.execute(stmt)
        new_id = result.scalar_one_or_none()
        await self.session.flush()
        if not new_id:
            return None
        return await self.session.get(TelegramDelivery, new_id)

    async def _list_subscribers(
        self, restaurant_id: uuid.UUID
    ) -> list[tuple[User, UserRestaurantRole]]:
        stmt = (
            select(User, UserRestaurantRole)
            .join(UserRestaurantRole, UserRestaurantRole.user_id == User.id)
            .where(
                UserRestaurantRole.restaurant_id == restaurant_id,
                User.is_active.is_(True),
                User.telegram_chat_id.is_not(None),
                UserRestaurantRole.telegram_notifications.is_(True),
            )
        )
        return [(u, m) for u, m in (await self.session.execute(stmt)).all()]
