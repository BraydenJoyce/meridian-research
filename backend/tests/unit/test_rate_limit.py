"""Tests for per-IP rate limiting (t-048)."""
from __future__ import annotations

from slowapi import Limiter

from app.core.rate_limit import limiter


def test_rate_limit_module_exists() -> None:
    from app.core import rate_limit
    assert hasattr(rate_limit, "limiter")


def test_limiter_is_configured() -> None:
    assert isinstance(limiter, Limiter)


def test_limiter_has_key_func() -> None:
    assert limiter._key_func is not None
