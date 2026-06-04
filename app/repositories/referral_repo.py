"""Referral payouts repository."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.models.referral import PayoutStatus, ReferralPayout
from app.repositories.base import BaseRepository


class ReferralPayoutRepository(BaseRepository[ReferralPayout]):
    model = ReferralPayout

    async def list_for_referrer(
        self,
        referrer_user_id: uuid.UUID,
        *,
        statuses: list[PayoutStatus] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ReferralPayout]:
        stmt = select(ReferralPayout).where(ReferralPayout.referrer_user_id == referrer_user_id)
        if statuses:
            stmt = stmt.where(ReferralPayout.status.in_(statuses))
        stmt = stmt.order_by(ReferralPayout.created_at.desc()).limit(limit).offset(offset)
        return list((await self.session.scalars(stmt)).all())
