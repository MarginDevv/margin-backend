"""Email verification: template render + URL builder + token consume math."""
from __future__ import annotations

import importlib
import os

import pytest

os.environ.setdefault("APP_SECRET_KEY", "x" * 32)
os.environ.setdefault("JWT_SECRET_KEY", "y" * 32)


def test_template_renders_with_and_without_name() -> None:
    from app.services.email.templates import render_verification

    html, text = render_verification(
        name="Артём", verify_url="https://app.margin.example/verify-email?token=abc", ttl_hours=24
    )
    assert "Артём" in html
    assert "https://app.margin.example/verify-email?token=abc" in html
    assert "Артём" in text
    assert "24" in text

    html2, _ = render_verification(name=None, verify_url="x", ttl_hours=24)
    # No `, ` separator when name is empty.
    assert "Привет!" in html2


def test_template_escapes_user_supplied_name() -> None:
    from app.services.email.templates import render_verification

    html, _ = render_verification(
        name="<script>alert(1)</script>", verify_url="x", ttl_hours=24
    )
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_url_builder_appends_token_with_query_separator() -> None:
    os.environ["EMAIL_VERIFY_URL"] = "https://app.margin.example/verify-email"
    from app.core import config

    importlib.reload(config)
    from app.services.email import verification_service

    importlib.reload(verification_service)

    # Build URL with no preexisting query.
    svc = verification_service.EmailVerificationService.__new__(
        verification_service.EmailVerificationService
    )
    url = svc._build_verify_url("abc")
    assert url == "https://app.margin.example/verify-email?token=abc"


def test_url_builder_uses_ampersand_when_query_present() -> None:
    os.environ["EMAIL_VERIFY_URL"] = "https://app.margin.example/auth?ref=mail"
    from app.core import config

    importlib.reload(config)
    from app.services.email import verification_service

    importlib.reload(verification_service)

    svc = verification_service.EmailVerificationService.__new__(
        verification_service.EmailVerificationService
    )
    url = svc._build_verify_url("xyz")
    assert url == "https://app.margin.example/auth?ref=mail&token=xyz"


@pytest.mark.asyncio
async def test_console_backend_logs_silently() -> None:
    from app.services.email.base import EmailMessage
    from app.services.email.console import ConsoleEmailBackend

    backend = ConsoleEmailBackend()
    # Should not raise.
    await backend.send(EmailMessage(to="a@b.c", subject="Hi", html_body="<p>x</p>"))
