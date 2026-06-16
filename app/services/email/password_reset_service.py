"""Issue and consume password reset tokens."""
from __future__ import annotations

import secrets
from datetime import timedelta
from urllib.parse import urlencode

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import ValidationError
from app.core.logging import get_logger
from app.core.security import hash_password
from app.models.password_reset import PasswordResetToken
from app.models.user import User
from app.services.email.base import EmailMessage
from app.services.email.factory import get_email_backend
from app.services.email.templates import render_password_reset
from app.utils.datetime import now_utc

logger = get_logger("email.password_reset")


class PasswordResetService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _build_reset_url(self, token: str) -> str:
        base = settings.password_reset_url.rstrip("/")
        sep = "&" if "?" in base else "?"
        return f"{base}{sep}{urlencode({'token': token})}"

    async def issue_and_send(self, user: User) -> PasswordResetToken:
        # Invalidate any earlier outstanding tokens — fresh request voids the old.
        await self.session.execute(
            delete(PasswordResetToken).where(
                PasswordResetToken.user_id == user.id,
                PasswordResetToken.used_at.is_(None),
            )
        )

        token = PasswordResetToken(
            user_id=user.id,
            token=secrets.token_urlsafe(32),
            expires_at=now_utc() + timedelta(hours=settings.password_reset_ttl_hours),
        )
        self.session.add(token)
        await self.session.flush()

        html_body, text_body = render_password_reset(
            name=user.full_name,
            email=user.email,
            reset_url=self._build_reset_url(token.token),
            ttl_hours=settings.password_reset_ttl_hours,
        )
        backend = get_email_backend()
        try:
            await backend.send(
                EmailMessage(
                    to=user.email,
                    subject="Margin — сброс пароля",
                    html_body=html_body,
                    text_body=text_body,
                )
            )
        except Exception as exc:
            logger.warning(
                "email.password_reset.send_failed",
                user_id=str(user.id),
                error=str(exc),
            )

        await self.session.commit()
        return token

    async def consume(self, token_str: str, new_password: str) -> User:
        token = await self.session.scalar(
            select(PasswordResetToken).where(
                PasswordResetToken.token == token_str,
                PasswordResetToken.used_at.is_(None),
                PasswordResetToken.expires_at > now_utc(),
            )
        )
        if not token:
            raise ValidationError("Password reset link is invalid or has expired")

        user = await self.session.get(User, token.user_id)
        if not user:
            raise ValidationError("User no longer exists")

        user.password_hash = hash_password(new_password)
        token.used_at = now_utc()

        # Burn ALL other outstanding reset tokens for this user — defense in depth.
        await self.session.execute(
            delete(PasswordResetToken).where(
                PasswordResetToken.user_id == user.id,
                PasswordResetToken.id != token.id,
                PasswordResetToken.used_at.is_(None),
            )
        )

        await self.session.commit()
        logger.info("email.password_reset.confirmed", user_id=str(user.id))
        return user
