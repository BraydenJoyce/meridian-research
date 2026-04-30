"""Stripe billing API: checkout session creation and webhook handler."""
from __future__ import annotations

import stripe
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentUser, get_current_user
from app.core.config import get_settings
from app.core.dependencies import get_db
from app.services import stripe_service

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/billing", tags=["billing"])


@router.post("/checkout")
async def create_checkout(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Create a Stripe Checkout session and return the redirect URL."""
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
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Handle Stripe webhook events with signature verification."""
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
