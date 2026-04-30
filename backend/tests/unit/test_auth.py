"""Tests for Supabase Auth JWT middleware (t-038)."""
from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException
from jose import jwt

from app.core.auth import CurrentUser, get_current_user
from app.core.config import Settings

_SECRET = "test-jwt-secret-that-is-long-enough-for-hs256"
_USER_ID = str(uuid.uuid4())
_EMAIL = "test@example.com"


def _make_token(
    sub: str = _USER_ID,
    email: str = _EMAIL,
    aud: str = "authenticated",
    secret: str = _SECRET,
) -> str:
    return jwt.encode({"sub": sub, "email": email, "aud": aud}, secret, algorithm="HS256")


def _settings_with_secret(secret: str = _SECRET) -> Settings:
    s = Settings()
    s.supabase_jwt_secret = secret
    return s


def test_valid_token_returns_current_user() -> None:
    token = _make_token()
    result = get_current_user(
        authorization=f"Bearer {token}",
        settings=_settings_with_secret(),
    )
    assert isinstance(result, CurrentUser)
    assert result.user_id == uuid.UUID(_USER_ID)
    assert result.email == _EMAIL


def test_missing_token_returns_401() -> None:
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(authorization=None, settings=_settings_with_secret())
    assert exc_info.value.status_code == 401


def test_malformed_bearer_returns_401() -> None:
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(authorization="NotBearer token", settings=_settings_with_secret())
    assert exc_info.value.status_code == 401


def test_wrong_secret_returns_401() -> None:
    token = _make_token(secret=_SECRET)
    wrong_settings = _settings_with_secret("wrong-secret-that-is-long-enough")
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(authorization=f"Bearer {token}", settings=wrong_settings)
    assert exc_info.value.status_code == 401


def test_dev_mode_accepts_unverified_token() -> None:
    """When supabase_jwt_secret is empty, any valid JWT is accepted."""
    token = _make_token(secret="any-secret")
    dev_settings = Settings()
    dev_settings.supabase_jwt_secret = ""
    result = get_current_user(authorization=f"Bearer {token}", settings=dev_settings)
    assert result.user_id == uuid.UUID(_USER_ID)
    assert result.email == _EMAIL


def test_token_with_wrong_audience_returns_401() -> None:
    token = _make_token(aud="service_role")
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(authorization=f"Bearer {token}", settings=_settings_with_secret())
    assert exc_info.value.status_code == 401
