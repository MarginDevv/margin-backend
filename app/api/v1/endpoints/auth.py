"""Auth endpoints: register, login, refresh."""
from __future__ import annotations

from fastapi import APIRouter, status

from app.core.dependencies import DbSession
from app.schemas.auth import LoginRequest, RefreshRequest, RegisterRequest, TokenPair
from app.services.auth_service import AuthService

router = APIRouter()


@router.post(
    "/register",
    response_model=TokenPair,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new owner and their first restaurant",
)
async def register(payload: RegisterRequest, session: DbSession) -> TokenPair:
    _, _, tokens = await AuthService(session).register(payload)
    return tokens


@router.post("/login", response_model=TokenPair, summary="Login with email and password")
async def login(payload: LoginRequest, session: DbSession) -> TokenPair:
    _, tokens = await AuthService(session).login(payload.email, payload.password)
    return tokens


@router.post("/refresh", response_model=TokenPair, summary="Exchange refresh token for a new pair")
async def refresh(payload: RefreshRequest, session: DbSession) -> TokenPair:
    return await AuthService(session).refresh(payload.refresh_token)
