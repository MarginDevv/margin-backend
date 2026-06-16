"""Console backend — logs emails to stdout. Use in dev / tests."""
from __future__ import annotations

from app.core.logging import get_logger
from app.services.email.base import EmailMessage

logger = get_logger("email.console")


class ConsoleEmailBackend:
    name = "console"

    async def send(self, message: EmailMessage) -> None:
        logger.info(
            "email.console.sent",
            to=message.to,
            subject=message.subject,
            body_preview=message.html_body[:500],
        )
