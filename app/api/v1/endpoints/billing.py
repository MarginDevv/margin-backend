"""Billing endpoints — stubbed for v1 launch.

All routes return 404 with a marker code. Actual billing (ЮKassa/CloudPayments
subscription invoices + ReferralService.accrue_for_invoice hook) will land in a
later iteration. The router is wired so the frontend can call the endpoints
during development and detect they're not yet available — without rewiring
when they go live.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

router = APIRouter()


def _not_implemented_yet() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "code": "billing_not_implemented",
            "message": "Биллинг пока не реализован. Скоро будет.",
        },
    )


@router.get("/plans", summary="(stub) Список тарифов — пока не реализован")
async def list_plans() -> None:
    raise _not_implemented_yet()


@router.get("/subscription", summary="(stub) Подписка ресторана — пока не реализована")
async def get_subscription() -> None:
    raise _not_implemented_yet()


@router.post("/subscription", summary="(stub) Оформить / продлить подписку")
async def create_subscription() -> None:
    raise _not_implemented_yet()


@router.post("/subscription/cancel", summary="(stub) Отменить подписку")
async def cancel_subscription() -> None:
    raise _not_implemented_yet()


@router.get("/invoices", summary="(stub) История счетов")
async def list_invoices() -> None:
    raise _not_implemented_yet()


@router.post(
    "/webhooks/{provider}",
    summary="(stub) Webhook от платёжного провайдера",
    include_in_schema=False,
)
async def billing_webhook(provider: str) -> None:
    raise _not_implemented_yet()
