"""Top-level v1 API router."""
from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints import (
    activity,
    analytics,
    auth,
    integrations,
    menu,
    recommendations,
    reports,
    restaurants,
    telegram,
    telegram_webhook,
    users,
)

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(
    telegram.router,
    prefix="/users/me/telegram",
    tags=["telegram"],
)
api_router.include_router(restaurants.router, prefix="/restaurants", tags=["restaurants"])
api_router.include_router(
    integrations.router,
    prefix="/restaurants/{restaurant_id}/integrations/iiko",
    tags=["iiko-integration"],
)
api_router.include_router(
    menu.router,
    prefix="/restaurants/{restaurant_id}/menu",
    tags=["menu"],
)
api_router.include_router(
    analytics.router,
    prefix="/restaurants/{restaurant_id}/analytics",
    tags=["analytics"],
)
api_router.include_router(
    recommendations.router,
    prefix="/restaurants/{restaurant_id}/recommendations",
    tags=["recommendations"],
)
api_router.include_router(
    reports.router,
    prefix="/restaurants/{restaurant_id}/reports",
    tags=["reports"],
)
api_router.include_router(
    activity.router,
    prefix="/restaurants/{restaurant_id}/activity",
    tags=["activity"],
)
api_router.include_router(
    telegram_webhook.router,
    prefix="/webhooks/telegram",
    tags=["telegram-webhook"],
)
