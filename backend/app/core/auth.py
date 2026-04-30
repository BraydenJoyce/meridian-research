"""FastAPI JWT authentication dependency for Supabase Auth."""
from __future__ import annotations

import uuid

import structlog
from fastapi import Depends, Header, HTTPException
from jose import JWTError, jwt
from pydantic import BaseModel

from app.core.config import Settings, get_settings

logger = structlog.get_logger()


class CurrentUser(BaseModel):
    user_id: uuid.UUID
    email: str


def _decode_unverified(token: str) -> dict:
    """Decode JWT without signature verification (dev mode only)."""
    try:
        return jwt.get_unverified_claims(token)
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc


def get_current_user(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> CurrentUser:
    """Verify Supabase JWT and return the authenticated user.

    Dev mode: when supabase_jwt_secret is empty, accepts any structurally
    valid JWT without signature verification and emits a WARNING log.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = authorization.removeprefix("Bearer ")

    if not settings.supabase_jwt_secret:
        logger.warning("supabase_jwt_secret_not_set", mode="dev — auth signature disabled")
        payload = _decode_unverified(token)
    else:
        try:
            payload = jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=["HS256"],
                audience="authenticated",
            )
        except JWTError as exc:
            raise HTTPException(status_code=401, detail="Invalid token") from exc

    try:
        user_id = uuid.UUID(str(payload.get("sub", "")))
    except (ValueError, AttributeError) as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc

    return CurrentUser(user_id=user_id, email=str(payload.get("email", "")))
