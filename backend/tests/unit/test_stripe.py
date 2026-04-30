"""Tests for Stripe billing integration (t-040)."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from app.core.auth import CurrentUser, get_current_user
from app.core.dependencies import get_db
from app.main import app
from app.models.user_subscription import UserSubscription


def _fake_user() -> CurrentUser:
    return CurrentUser(user_id=uuid.uuid4(), email="test@example.com")


def _make_db_mock(sub: UserSubscription | None = None, usage: int = 0) -> AsyncMock:
    db = AsyncMock()
    db.get = AsyncMock(return_value=sub)
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    scalar_mock = AsyncMock(return_value=usage)
    execute_mock = AsyncMock()
    execute_mock.scalar_one_or_none = MagicMock(return_value=None)
    db.scalar = scalar_mock
    db.execute = AsyncMock(return_value=execute_mock)
    return db


@pytest.mark.asyncio
async def test_checkout_endpoint_returns_url() -> None:
    db = _make_db_mock()
    user = _fake_user()

    async def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: user

    fake_session = MagicMock()
    fake_session.url = "https://checkout.stripe.com/test_session"

    fake_settings = MagicMock()
    fake_settings.stripe_secret_key = "sk_test_123"
    fake_settings.stripe_pro_price_id = "price_test_123"
    fake_settings.stripe_webhook_secret = ""
    fake_settings.supabase_jwt_secret = ""

    with patch("stripe.checkout.Session.create", return_value=fake_session), \
         patch("app.api.billing.get_settings", return_value=fake_settings), \
         patch("app.services.stripe_service.get_settings", return_value=fake_settings):

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/billing/checkout")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert "checkout_url" in data
    assert "stripe.com" in data["checkout_url"]


@pytest.mark.asyncio
async def test_webhook_checkout_completed_upgrades_plan() -> None:
    from app.services import stripe_service

    db = _make_db_mock(sub=None)
    user_id = str(uuid.uuid4())

    fake_event = MagicMock()
    fake_event.id = "evt_test"
    fake_event.data.object = {
        "metadata": {"user_id": user_id},
        "customer": "cus_test",
        "subscription": "sub_test",
    }

    await stripe_service.handle_checkout_completed(fake_event, db)
    db.add.assert_called_once()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_webhook_subscription_deleted_downgrades_plan() -> None:
    from app.services import stripe_service

    existing_sub = MagicMock(spec=UserSubscription)
    existing_sub.plan = "pro"
    existing_sub.stripe_subscription_id = "sub_test"

    execute_result = MagicMock()
    execute_result.scalar_one_or_none = MagicMock(return_value=existing_sub)

    db = AsyncMock()
    db.execute = AsyncMock(return_value=execute_result)
    db.commit = AsyncMock()

    fake_event = MagicMock()
    fake_event.data.object = {"id": "sub_test"}

    await stripe_service.handle_subscription_deleted(fake_event, db)
    assert existing_sub.plan == "free"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_webhook_invalid_signature_returns_400() -> None:
    db = _make_db_mock()

    async def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db

    import stripe

    fake_settings = MagicMock()
    fake_settings.stripe_webhook_secret = "whsec_test"
    fake_settings.supabase_jwt_secret = ""

    with patch("stripe.Webhook.construct_event",
               side_effect=stripe.SignatureVerificationError("bad sig", "sig")), \
         patch("app.api.billing.get_settings", return_value=fake_settings):

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/billing/webhook",
                content=b'{"type": "test"}',
                headers={"stripe-signature": "invalid"},
            )

    app.dependency_overrides.clear()
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_free_tier_limit_returns_429() -> None:
    from app.services.research_service import _enforce_tier

    user_id = uuid.uuid4()

    db = AsyncMock()
    db.get = AsyncMock(return_value=None)
    db.scalar = AsyncMock(return_value=3)

    with pytest.raises(HTTPException) as exc_info:
        await _enforce_tier(user_id, db)

    assert exc_info.value.status_code == 429
    assert "Free tier limit" in exc_info.value.detail


@pytest.mark.asyncio
async def test_pro_tier_has_no_limit() -> None:
    from app.services.research_service import _enforce_tier

    user_id = uuid.uuid4()
    pro_sub = MagicMock(spec=UserSubscription)
    pro_sub.plan = "pro"

    db = AsyncMock()
    db.get = AsyncMock(return_value=pro_sub)

    # Should not raise
    await _enforce_tier(user_id, db)
