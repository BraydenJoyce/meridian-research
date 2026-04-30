"""Stripe payment integration service (ADR-008)."""
from __future__ import annotations

import uuid

import stripe
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.user_subscription import UserSubscription

logger = structlog.get_logger(__name__)

FREE_TIER_LIMIT = 3


async def create_checkout_session(
    user_id: uuid.UUID,
    email: str,
    db: AsyncSession,
) -> str:
    """Create a Stripe Checkout session for the Pro plan and return the URL."""
    settings = get_settings()
    stripe.api_key = settings.stripe_secret_key

    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": settings.stripe_pro_price_id, "quantity": 1}],
        customer_email=email,
        metadata={"user_id": str(user_id)},
        success_url="http://localhost:3000/dashboard?upgrade=success",
        cancel_url="http://localhost:3000/dashboard",
    )
    return str(session.url)


async def handle_checkout_completed(event: stripe.Event, db: AsyncSession) -> None:
    """Upsert user_subscriptions to pro on successful checkout."""
    checkout_session = event.data.object
    user_id_str = (checkout_session.get("metadata") or {}).get("user_id")
    if not user_id_str:
        logger.warning("stripe_webhook_missing_user_id", event_id=event.id)
        return

    user_id = uuid.UUID(user_id_str)
    customer_id = checkout_session.get("customer")
    subscription_id = checkout_session.get("subscription")

    existing = await db.get(UserSubscription, user_id)
    if existing:
        existing.plan = "pro"
        existing.stripe_customer_id = customer_id
        existing.stripe_subscription_id = subscription_id
    else:
        db.add(
            UserSubscription(
                user_id=user_id,
                plan="pro",
                stripe_customer_id=customer_id,
                stripe_subscription_id=subscription_id,
            )
        )
    await db.commit()
    logger.info("stripe_checkout_completed", user_id=user_id_str)


async def handle_subscription_deleted(event: stripe.Event, db: AsyncSession) -> None:
    """Downgrade user to free tier when subscription is canceled."""
    subscription = event.data.object
    subscription_id = subscription.get("id")

    from sqlalchemy import select

    result = await db.execute(
        select(UserSubscription).where(
            UserSubscription.stripe_subscription_id == subscription_id
        )
    )
    sub = result.scalar_one_or_none()
    if sub:
        sub.plan = "free"
        await db.commit()
        logger.info("stripe_subscription_deleted", subscription_id=subscription_id)
    else:
        logger.warning(
            "stripe_subscription_not_found", subscription_id=subscription_id
        )
