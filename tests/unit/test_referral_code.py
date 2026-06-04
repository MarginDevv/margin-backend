"""Referral code generator: alphabet and length."""

from __future__ import annotations

import os
import re

os.environ.setdefault("APP_SECRET_KEY", "x" * 32)
os.environ.setdefault("JWT_SECRET_KEY", "y" * 32)


def test_code_format() -> None:
    from app.services.referral.referral_service import _gen_code

    code = _gen_code()
    assert re.fullmatch(r"[A-Z2-9]{8}", code)
    assert "0" not in code and "O" not in code
    assert "1" not in code and "I" not in code and "L" not in code


def test_codes_are_random() -> None:
    from app.services.referral.referral_service import _gen_code

    seen = {_gen_code() for _ in range(50)}
    assert len(seen) > 40  # vanishingly small chance of >10 collisions in 50


def test_build_referral_url_with_base() -> None:
    import importlib

    os.environ["APP_BASE_URL"] = "https://app.margin.example"
    from app.core import config

    importlib.reload(config)
    from app.services.referral import referral_service

    importlib.reload(referral_service)
    assert referral_service.build_referral_url("ABCDEFGH") == (
        "https://app.margin.example/r?ref=ABCDEFGH"
    )
