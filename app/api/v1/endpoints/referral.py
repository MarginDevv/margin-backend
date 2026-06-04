"""Referral program endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.core.dependencies import CurrentUser, DbSession
from app.models.referral import PayoutStatus
from app.repositories.referral_repo import ReferralPayoutRepository
from app.schemas.referral import ReferralPayoutRead, ReferralProfile
from app.services.referral.referral_service import ReferralService, build_referral_url

router = APIRouter()


@router.get("", response_model=ReferralProfile, summary="Мой реферальный профиль и сводка")
async def my_referral(user: CurrentUser, session: DbSession) -> ReferralProfile:
    service = ReferralService(session)
    code = await service.get_or_issue_code(user)
    summary = await service.summary_for_referrer(user.id)
    return ReferralProfile(
        code=code,
        share_url=build_referral_url(code),
        referred_restaurants=summary["referred_restaurants"],
        total_pending=summary["total_pending"],
        total_paid=summary["total_paid"],
        by_status=summary["by_status"],
    )


@router.get("/payouts", response_model=list[ReferralPayoutRead])
async def list_payouts(
    user: CurrentUser,
    session: DbSession,
    status: Annotated[list[PayoutStatus] | None, Query()] = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[ReferralPayoutRead]:
    rows = await ReferralPayoutRepository(session).list_for_referrer(
        user.id, statuses=status, limit=limit, offset=offset
    )
    return [ReferralPayoutRead.model_validate(r) for r in rows]
