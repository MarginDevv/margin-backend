"""Password reset templates + URL builder + service behaviour."""
from __future__ import annotations

import importlib
import os

import pytest

os.environ.setdefault("APP_SECRET_KEY", "x" * 32)
os.environ.setdefault("JWT_SECRET_KEY", "y" * 32)


def test_reset_template_with_and_without_name() -> None:
    from app.services.email.templates import render_password_reset

    html, text = render_password_reset(
        name="Артём", email="a@b.c",
        reset_url="https://app.margin.example/reset-password?token=t1",
        ttl_hours=2,
    )
    assert "Артём, на аккаунт" in html
    assert "a@b.c" in html
    assert "https://app.margin.example/reset-password?token=t1" in html
    assert "2 час" in html
    assert "Артём, на аккаунт" in text

    html2, _ = render_password_reset(
        name=None, email="x@y.z", reset_url="u", ttl_hours=2
    )
    assert "На аккаунт" in html2  # leading "Н" capitalised, no "{name}, "


def test_reset_template_escapes_user_supplied_email() -> None:
    from app.services.email.templates import render_password_reset

    html, _ = render_password_reset(
        name=None, email="<script>alert(1)</script>", reset_url="u", ttl_hours=2
    )
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_url_builder_appends_token() -> None:
    os.environ["PASSWORD_RESET_URL"] = "https://app.margin.example/reset-password"
    from app.core import config

    importlib.reload(config)
    from app.services.email import password_reset_service

    importlib.reload(password_reset_service)

    svc = password_reset_service.PasswordResetService.__new__(
        password_reset_service.PasswordResetService
    )
    url = svc._build_reset_url("abc")
    assert url == "https://app.margin.example/reset-password?token=abc"


def test_url_builder_uses_ampersand_when_query_present() -> None:
    os.environ["PASSWORD_RESET_URL"] = "https://app.margin.example/auth?step=reset"
    from app.core import config

    importlib.reload(config)
    from app.services.email import password_reset_service

    importlib.reload(password_reset_service)

    svc = password_reset_service.PasswordResetService.__new__(
        password_reset_service.PasswordResetService
    )
    url = svc._build_reset_url("xyz")
    assert url == "https://app.margin.example/auth?step=reset&token=xyz"


@pytest.mark.asyncio
async def test_invalid_token_raises_validation_error() -> None:
    from app.core.exceptions import ValidationError
    from app.models import Base
    from app.services.email.password_reset_service import PasswordResetService
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with Session() as session:
        svc = PasswordResetService(session)
        with pytest.raises(ValidationError):
            await svc.consume("nope", "new-secret-123")
    await engine.dispose()
