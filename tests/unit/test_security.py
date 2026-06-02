"""Smoke tests for password hashing and JWT round-trip."""
from __future__ import annotations

import os

os.environ.setdefault("APP_SECRET_KEY", "x" * 32)
os.environ.setdefault("JWT_SECRET_KEY", "y" * 32)


def test_password_hash_verify_roundtrip() -> None:
    from app.core.security import hash_password, verify_password

    h = hash_password("secret-pass-123")
    assert verify_password("secret-pass-123", h)
    assert not verify_password("wrong-pass", h)


def test_jwt_roundtrip() -> None:
    from app.core.security import create_access_token, decode_token

    token = create_access_token("user-1", extra_claims={"email": "a@b.c"})
    payload = decode_token(token)
    assert payload["sub"] == "user-1"
    assert payload["type"] == "access"
    assert payload["email"] == "a@b.c"


def test_fernet_crypto_roundtrip() -> None:
    from app.utils.crypto import decrypt_str, encrypt_str

    ct = encrypt_str("api-login-secret")
    assert ct != "api-login-secret"
    assert decrypt_str(ct) == "api-login-secret"
