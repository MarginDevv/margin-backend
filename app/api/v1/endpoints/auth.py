"""Auth endpoints: register, login, refresh, email verification, password reset."""
from __future__ import annotations

import contextlib

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, EmailStr, Field

from app.core.dependencies import CurrentUser, DbSession
from app.core.exceptions import NotFoundError
from app.core.rate_limit import by_ip_and_email, rate_limit
from app.repositories.user_repo import UserRepository
from app.schemas.auth import LoginRequest, RefreshRequest, RegisterRequest, TokenPair
from app.services.auth_service import AuthService
from app.services.email.password_reset_service import PasswordResetService
from app.services.email.verification_service import EmailVerificationService

router = APIRouter()


class VerifyEmailRequest(BaseModel):
    token: str


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class EmailVerificationStatus(BaseModel):
    is_email_verified: bool
    email: EmailStr


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


# --- Registration / login / refresh ---


@router.post(
    "/register",
    response_model=TokenPair,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new owner and their first restaurant",
    dependencies=[Depends(rate_limit("auth.register", 5, 60))],
)
async def register(payload: RegisterRequest, session: DbSession) -> TokenPair:
    _, _, tokens = await AuthService(session).register(payload)
    return tokens


@router.post(
    "/login",
    response_model=TokenPair,
    summary="Login with email and password",
    dependencies=[
        Depends(rate_limit("auth.login", 5, 60, key_func=by_ip_and_email())),
    ],
)
async def login(payload: LoginRequest, session: DbSession) -> TokenPair:
    _, tokens = await AuthService(session).login(payload.email, payload.password)
    return tokens


@router.post("/refresh", response_model=TokenPair, summary="Exchange refresh token for a new pair")
async def refresh(payload: RefreshRequest, session: DbSession) -> TokenPair:
    return await AuthService(session).refresh(payload.refresh_token)


# --- Email verification ---


@router.post(
    "/verify-email",
    response_model=EmailVerificationStatus,
    summary="Подтвердить email по токену из письма",
    dependencies=[Depends(rate_limit("auth.verify_email", 10, 60))],
)
async def verify_email(
    payload: VerifyEmailRequest, session: DbSession
) -> EmailVerificationStatus:
    user = await EmailVerificationService(session).consume(payload.token)
    return EmailVerificationStatus(
        is_email_verified=user.is_email_verified, email=user.email
    )


@router.post(
    "/resend-verification",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Перевыслать письмо подтверждения (по email)",
    dependencies=[
        Depends(rate_limit("auth.resend_verify", 2, 300, key_func=by_ip_and_email())),
    ],
)
async def resend_verification(
    payload: ResendVerificationRequest, session: DbSession
) -> dict[str, str]:
    """Always returns 202 — we don't leak whether the email is registered."""
    user = await UserRepository(session).get_by_email(payload.email.lower())
    if user and not user.is_email_verified:
        with contextlib.suppress(Exception):
            await EmailVerificationService(session).issue_and_send(user)
    return {"status": "queued"}


@router.get(
    "/me/email-status",
    response_model=EmailVerificationStatus,
    summary="Статус подтверждения email текущего пользователя",
)
async def email_status(user: CurrentUser) -> EmailVerificationStatus:
    return EmailVerificationStatus(
        is_email_verified=user.is_email_verified, email=user.email
    )


@router.post(
    "/me/resend-verification",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Перевыслать письмо подтверждения авторизованному пользователю",
    dependencies=[Depends(rate_limit("auth.resend_verify_self", 2, 300))],
)
async def resend_verification_authed(
    user: CurrentUser, session: DbSession
) -> dict[str, str]:
    if user.is_email_verified:
        raise NotFoundError("Email is already verified")
    await EmailVerificationService(session).issue_and_send(user)
    return {"status": "queued"}


# --- Password reset ---


@router.post(
    "/password/forgot",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Запросить письмо со ссылкой для сброса пароля",
    dependencies=[
        Depends(rate_limit("auth.forgot", 3, 300, key_func=by_ip_and_email())),
    ],
)
async def forgot_password(
    payload: ForgotPasswordRequest, session: DbSession
) -> dict[str, str]:
    """Always returns 202 — we don't leak whether the email is registered."""
    user = await UserRepository(session).get_by_email(payload.email.lower())
    if user and user.is_active:
        with contextlib.suppress(Exception):
            await PasswordResetService(session).issue_and_send(user)
    return {"status": "queued"}


@router.post(
    "/password/reset",
    status_code=status.HTTP_200_OK,
    summary="Установить новый пароль по токену из письма",
    dependencies=[Depends(rate_limit("auth.reset", 5, 60))],
)
async def reset_password(
    payload: ResetPasswordRequest, session: DbSession
) -> dict[str, str]:
    await PasswordResetService(session).consume(payload.token, payload.new_password)
    return {"status": "ok"}
