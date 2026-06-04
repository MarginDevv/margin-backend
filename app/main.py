"""FastAPI application entry point."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, get_logger


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    logger = get_logger("app.lifespan")
    logger.info("startup", env=settings.app_env, debug=settings.app_debug)
    yield
    logger.info("shutdown")


def create_app() -> FastAPI:
    configure_logging()
    fastapi_app = FastAPI(
        title="Margin API",
        version="0.1.0",
        description=(
            "AI-manager for restaurants. " "iikoCloud integration + analytics + recommendations."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    if settings.cors_origins:
        fastapi_app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    register_exception_handlers(fastapi_app)
    fastapi_app.include_router(api_router, prefix="/api/v1")

    @fastapi_app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "env": settings.app_env}

    return fastapi_app


app = create_app()
