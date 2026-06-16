"""Pick the email backend based on EMAIL_BACKEND setting."""
from __future__ import annotations

from app.core.config import settings
from app.services.email.base import EmailBackend


def get_email_backend() -> EmailBackend:
    if settings.email_backend == "smtp":
        from app.services.email.smtp import SmtpEmailBackend

        return SmtpEmailBackend()
    from app.services.email.console import ConsoleEmailBackend

    return ConsoleEmailBackend()
