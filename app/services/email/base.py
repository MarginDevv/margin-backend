"""Outbound email — provider-agnostic interface."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(slots=True)
class EmailMessage:
    to: str
    subject: str
    html_body: str
    text_body: str | None = None
    reply_to: str | None = None


class EmailBackend(Protocol):
    name: str

    async def send(self, message: EmailMessage) -> None: ...
