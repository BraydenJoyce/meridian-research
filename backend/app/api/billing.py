"""Stripe billing API: checkout session creation and webhook handler."""
from __future__ import annotations

import stripe
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentUser, get_current_user
from app.core.config import get_settings
from app.core.dependencies import get_db
from app.core.rate_limit import limiter
from app.services import stripe_service

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/billing", tags=["billing"])


@router.post("/checkout")
@limiter.limit("5/minute")
async def create_checkout(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Create a Stripe Checkout session for the Pro plan.

    Args:
        current_user: Authenticated user from JWT.
        db: Async database session.

    Returns:
        Dict containing ``checkout_url`` — the Stripe-hosted payment page URL.

    Raises:
        HTTPException(503): Stripe is not configured (missing STRIPE_SECRET_KEY).
    """
    settings = get_settings()
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=503, detail="Stripe not configured")

    checkout_url = await stripe_service.create_checkout_session(
        user_id=current_user.user_id,
        email=current_user.email,
        db=db,
    )
    return {"checkout_url": checkout_url}


@router.post("/webhook")
@limiter.limit("100/minute")
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Handle Stripe webhook events with HMAC-SHA256 signature verification.

    Handles ``checkout.session.completed`` (upgrades user to Pro) and
    ``customer.subscription.deleted`` (downgrades user to free tier).

    Args:
        request: Raw HTTP request (body + Stripe-Signature header).
        db: Async database session.

    Returns:
        ``{"status": "ok"}`` on success.

    Raises:
        HTTPException(400): Invalid or missing Stripe webhook signature.
    """
    settings = get_settings()
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    if settings.stripe_webhook_secret:
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, settings.stripe_webhook_secret
            )
        except stripe.SignatureVerificationError as exc:
            raise HTTPException(status_code=400, detail="Invalid webhook signature") from exc
    else:
        import json

        event = stripe.Event.construct_from(json.loads(payload), stripe.api_key)

    event_type = event.get("type", "")

    if event_type == "checkout.session.completed":
        await stripe_service.handle_checkout_completed(event, db)
    elif event_type == "customer.subscription.deleted":
        await stripe_service.handle_subscription_deleted(event, db)
    else:
        logger.debug("stripe_webhook_unhandled_event", event_type=event_type)

    return {"status": "ok"}
