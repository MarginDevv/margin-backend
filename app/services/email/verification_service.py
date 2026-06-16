"""Issue, send and consume email verification tokens."""
from __future__ import annotations

import secrets
from datetime import timedelta
from urllib.parse import urlencode

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.email_token import EmailVerificationToken
from app.models.user import User
from app.services.email.base import EmailMessage
from app.services.email.factory import get_email_backend
from app.services.email.templates import render_verification
from app.utils.datetime import now_utc

logger = get_logger("email.verification")


class EmailVerificationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _build_verify_url(self, token: str) -> str:
        base = settings.email_verify_url.rstrip("/")
        sep = "&" if "?" in base else "?"
        return f"{base}{sep}{urlencode({'token': token})}"

    async def issue_and_send(self, user: User) -> EmailVerificationToken:
        if user.is_email_verified:
            raise ConflictError("Email is already verified")

        # Invalidate any earlier outstanding tokens for this user.
        await self.session.execute(
            delete(EmailVerificationToken).where(
                EmailVerificationToken.user_id == user.id,
                EmailVerificationToken.used_at.is_(None),
            )
        )

        token = EmailVerificationToken(
            user_id=user.id,
            token=secrets.token_urlsafe(32),
            expires_at=now_utc() + timedelta(hours=settings.email_verify_ttl_hours),
        )
        self.session.add(token)
        await self.session.flush()

        html_body, text_body = render_verification(
            name=user.full_name,
            verify_url=self._build_verify_url(token.token),
            ttl_hours=settings.email_verify_ttl_hours,
        )
        backend = get_email_backend()
        try:
            await backend.send(
                EmailMessage(
                    to=user.email,
                    subject="Margin — подтвердите ваш email",
                    html_body=html_body,
                    text_body=text_body,
                )
            )
        except Exception as exc:
            # Failing to send the email shouldn't break registration — the user
            # can request a resend later. Log and keep the token alive.
            logger.warning(
                "email.verification.send_failed",
                user_id=str(user.id),
                error=str(exc),
            )

        await self.session.commit()
        return token

    async def consume(self, token_str: str) -> User:
        from sqlalchemy import select

        token = await self.session.scalar(
            select(EmailVerificationToken).where(
                EmailVerificationToken.token == token_str,
                EmailVerificationToken.used_at.is_(None),
                EmailVerificationToken.expires_at > now_utc(),
            )
        )
        if not token:
            raise ValidationError("Verification link is invalid or has expired")

        user = await self.session.get(User, token.user_id)
        if not user:
            raise NotFoundError("User no longer exists")

        user.is_email_verified = True
        token.used_at = now_utc()
        await self.session.commit()
        logger.info("email.verification.confirmed", user_id=str(user.id))
        return user
