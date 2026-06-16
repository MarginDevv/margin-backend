"""SMTP backend via aiosmtplib. Supports implicit TLS / STARTTLS / plaintext."""
from __future__ import annotations

from email.message import EmailMessage as MimeMessage

import aiosmtplib

from app.core.config import settings
from app.core.exceptions import DomainError
from app.core.logging import get_logger
from app.services.email.base import EmailMessage

logger = get_logger("email.smtp")


class SmtpEmailBackend:
    name = "smtp"

    def __init__(self) -> None:
        if not (settings.smtp_user and settings.smtp_password):
            raise DomainError(
                "SMTP_USER / SMTP_PASSWORD are not configured",
                code="smtp_not_configured",
            )
        self._host = settings.smtp_host
        self._port = settings.smtp_port
        self._user = settings.smtp_user
        self._password = settings.smtp_password
        self._security = settings.smtp_security

    async def send(self, message: EmailMessage) -> None:
        mime = MimeMessage()
        mime["From"] = settings.email_from
        mime["To"] = message.to
        mime["Subject"] = message.subject
        if message.reply_to:
            mime["Reply-To"] = message.reply_to
        if message.text_body:
            mime.set_content(message.text_body)
            mime.add_alternative(message.html_body, subtype="html")
        else:
            mime.set_content(message.html_body, subtype="html")

        await aiosmtplib.send(
            mime,
            hostname=self._host,
            port=self._port,
            username=self._user,
            password=self._password,
            use_tls=self._security == "tls",
            start_tls=self._security == "starttls",
        )
        logger.info("email.smtp.sent", to=message.to, subject=message.subject)
