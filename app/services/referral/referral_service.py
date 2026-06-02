"""Referral program logic.

Every user can have a public `referral_code`. When a new restaurant is being
registered with that code attached, we record the referrer on the restaurant.
On every paid subscription invoice we accrue a `ReferralPayout` for that
referrer (10% by default).

Code format: 8 uppercase characters from an unambiguous alphabet (no 0/O/1/I/L).
Collisions are resolved by retrying. Codes are issued lazily — `get_or_issue`
generates one only when the user first needs it.
"""
from __future__ import annotations

import secrets
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.referral import PayoutStatus, ReferralPayout
from app.models.restaurant import Restaurant
from app.models.user import User
from app.repositories.user_repo import UserRepository

logger = get_logger("referral")

_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no O/0, I/1, L
_CODE_LENGTH = 8
_DEFAULT_RATE = Decimal("0.10")


def _gen_code() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(_CODE_LENGTH))


class ReferralService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)

    # ----- codes -----

    async def get_or_issue_code(self, user: User) -> str:
        if user.referral_code:
            return user.referral_code
        for _ in range(8):
            candidate = _gen_code()
            user.referral_code = candidate
            try:
                await self.session.flush()
                await self.session.commit()
                logger.info("referral.code.issued", user_id=str(user.id), code=candidate)
                return candidate
            except IntegrityError:
                await self.session.rollback()
                # Reload user (lost in rollback) and retry.
                user_ref = await self.users.get(user.id)
                if user_ref is None:
                    raise NotFoundError("User not found") from None
                user = user_ref
                if user.referral_code:
                    return user.referral_code
        raise ConflictError("Could not allocate a unique referral code; try again")

    async def find_referrer(self, code: str) -> User | None:
        normalized = code.strip().upper()
        if not normalized:
            return None
        stmt = select(User).where(
            User.referral_code == normalized,
            User.is_active.is_(True),
        )
        return await self.session.scalar(stmt)

    async def attach_referrer(
        self, restaurant: Restaurant, code: str | None
    ) -> User | None:
        if not code:
            return None
        referrer = await self.find_referrer(code)
        if not referrer:
            raise ValidationError("Unknown referral code")
        if restaurant.referrer_user_id:
            # already attached — referral assignment is one-shot
            return None
        restaurant.referrer_user_id = referrer.id
        await self.session.flush()
        return referrer

    # ----- payouts -----

    async def accrue_for_invoice(
        self,
        restaurant_id: uuid.UUID,
        *,
        period_start: date,
        period_end: date,
        invoice_amount: Decimal,
        currency: str = "RUB",
        rate: Decimal | None = None,
    ) -> ReferralPayout | None:
        """Create a pending ReferralPayout for the restaurant's referrer.

        Returns None if the restaurant has no referrer attached.
        """
        restaurant = await self.session.get(Restaurant, restaurant_id)
        if not restaurant:
            raise NotFoundError("Restaurant not found")
        if not restaurant.referrer_user_id:
            return None
        rate = rate or _DEFAULT_RATE
        commission = (invoice_amount * rate).quantize(Decimal("0.01"))
        payout = ReferralPayout(
            referrer_user_id=restaurant.referrer_user_id,
            restaurant_id=restaurant_id,
            period_start=period_start,
            period_end=period_end,
            invoice_amount=invoice_amount,
            commission_rate=rate,
            commission_amount=commission,
            currency=currency,
            status=PayoutStatus.PENDING,
        )
        self.session.add(payout)
        await self.session.flush()
        logger.info(
            "referral.payout.accrued",
            restaurant_id=str(restaurant_id),
            referrer_id=str(restaurant.referrer_user_id),
            amount=str(commission),
        )
        return payout

    async def summary_for_referrer(self, user_id: uuid.UUID) -> dict[str, Decimal | int]:
        """Aggregate accrual for the dashboard."""
        stmt = (
            select(
                ReferralPayout.status,
                func.count(ReferralPayout.id).label("count"),
                func.coalesce(func.sum(ReferralPayout.commission_amount), 0).label("amount"),
            )
            .where(ReferralPayout.referrer_user_id == user_id)
            .group_by(ReferralPayout.status)
        )
        rows = (await self.session.execute(stmt)).all()
        bucket = {s.value: {"count": 0, "amount": Decimal("0")} for s in PayoutStatus}
        for status, count, amount in rows:
            bucket[status.value] = {"count": int(count), "amount": Decimal(str(amount))}

        # referred restaurant count
        ref_count = await self.session.scalar(
            select(func.count(Restaurant.id)).where(Restaurant.referrer_user_id == user_id)
        ) or 0

        return {
            "referred_restaurants": int(ref_count),
            "by_status": bucket,
            "total_pending": bucket["pending"]["amount"] + bucket["approved"]["amount"],
            "total_paid": bucket["paid"]["amount"],
        }


def build_referral_url(code: str) -> str:
    base = (settings.app_base_url or "").rstrip("/")
    if not base:
        return f"?ref={code}"
    return f"{base}/r?ref={code}"
