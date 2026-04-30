"""Per-IP rate limiting via slowapi (wraps limits library)."""
from __future__ import annotations

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def _get_remote_address(request: Request) -> str:
    """Extract the client IP address, respecting X-Forwarded-For from proxies.

    Args:
        request: Incoming FastAPI request.

    Returns:
        Client IP address string.
    """
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return get_remote_address(request)


limiter = Limiter(key_func=_get_remote_address)
