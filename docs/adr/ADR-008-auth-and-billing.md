# ADR-008: Authentication and Billing Architecture

**Status:** Accepted  
**Date:** 2026-04-29  
**Milestone:** 5 — Auth, Billing, and Product Polish  

---

## Context

Meridian Research is graduating from a prototype with no access control to a
freemium SaaS product. Two systems need to be designed together because they
share the same user identity:

1. **Authentication** — Supabase Auth provides sign-up, login, and password
   reset. The frontend receives a JWT; the backend must validate that JWT on
   every protected endpoint.

2. **Billing** — Stripe handles payments. Users on the free tier are limited to
   3 research reports per calendar month. Pro subscribers get unlimited reports.

Designing them together avoids a situation where the tier check and the identity
check are implemented as independent systems that later need to be reconciled.

---

## Decision

Use **Supabase Auth** for identity (JWTs validated in FastAPI via python-jose)
and **Stripe** for payments (checkout sessions + webhooks). Enforce the freemium
limit in the backend at the `POST /api/research/create` endpoint by counting
`ResearchSession` rows for the current user in the current calendar month before
allowing a new session to be created.

### Why Supabase Auth (not custom auth)

- Supabase Auth ships with sign-up, login, password reset, email confirmation,
  OAuth providers, and token refresh — all production-grade.
- The JWT secret is available in the Supabase project dashboard; we can validate
  tokens in FastAPI without calling Supabase on every request (stateless).
- Avoids building and maintaining a custom auth system.

### Why Stripe (not manual billing)

- Stripe Checkout handles PCI compliance, card storage, SCA/3DS, and invoicing.
- Webhook-driven subscription lifecycle means the backend only needs to handle
  two events to cover the full freemium → Pro flow.

---

## Auth Flow

```
Browser                       FastAPI                    Supabase Auth
  |                               |                            |
  |-- POST /auth/sign-up -------->|                            |
  |   (email, password)           |-- createUser() ---------->|
  |                               |<-- { user, session } -----|
  |<-- { access_token, refresh } -|                            |
  |                               |                            |
  |-- POST /api/research/create ->|                            |
  |   Authorization: Bearer <JWT> |                            |
  |                               |-- verify_jwt(JWT) -------->|
  |                               |   (local, no network call) |
  |                               |<-- { user_id, email } -----|
  |                               |                            |
  |                               |-- tier_check() ----------->|  (DB query)
  |                               |<-- allowed / 429 ----------|
  |                               |                            |
  |<-- 200 { session_id } --------|                            |
```

The JWT verification is **local** — python-jose checks the HS256 signature
against `SUPABASE_JWT_SECRET` without making a network call. This keeps latency
low and eliminates a Supabase availability dependency on every request.

---

## JWT Middleware Design

### FastAPI dependency: `get_current_user`

```python
# backend/app/core/auth.py

class CurrentUser(BaseModel):
    user_id: uuid.UUID
    email: str

def get_current_user(
    authorization: str = Header(None),
    settings: Settings = Depends(get_settings),
) -> CurrentUser:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = authorization.removeprefix("Bearer ")

    if not settings.supabase_jwt_secret:
        # Dev mode: accept any well-formed JWT, log a warning
        logger.warning("supabase_jwt_secret not set — auth disabled (dev mode)")
        payload = _decode_unverified(token)
    else:
        try:
            payload = jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=["HS256"],
                audience="authenticated",
            )
        except JWTError:
            raise HTTPException(status_code=401, detail="Invalid token")

    return CurrentUser(user_id=payload["sub"], email=payload.get("email", ""))
```

**Key design choices:**

- **Dependency injection** — `get_current_user` is a FastAPI `Depends()` arg on
  protected route functions. It never runs on unprotected routes.
- **Dev mode** — When `SUPABASE_JWT_SECRET=""` (default in Settings), all
  structurally valid JWTs are accepted. This allows local development without
  Supabase configuration. A `WARNING` log line is emitted on every request so it
  cannot go unnoticed.
- **HS256 algorithm** — Supabase issues HS256 JWTs signed with the project's
  JWT secret. We explicitly whitelist only HS256 in `algorithms=` to prevent
  algorithm confusion attacks (e.g., "none" algorithm, RS256 confusion).
- **Audience claim** — Supabase sets `aud: "authenticated"` on user JWTs.
  Verifying this prevents tokens issued for other purposes from being accepted.

### Protected vs public routes

| Route | Auth required |
|---|---|
| `POST /api/research/create` | Yes — `get_current_user` dependency |
| `GET /api/research/{id}/export` | Yes — `get_current_user` dependency |
| `GET /api/research/{id}/stream` | No — SSE stream, auth done at create time |
| `GET /health` | No — monitoring, no user data |
| `GET /api/research/{id}` | No — status polling (session_id is a UUID v4, unguessable) |

The decision to leave the stream endpoint public avoids the complexity of
attaching an Authorization header to an `EventSource` in the browser (the
`EventSource` API does not support custom headers). The session ID serves as a
bearer token for the stream — 128 bits of entropy is sufficient.

---

## Freemium Enforcement

### Tier model

| Tier | Reports/month | Price |
|---|---|---|
| Free | 3 | $0 |
| Pro | Unlimited | $29/month |

### Enforcement point

The check runs synchronously inside `POST /api/research/create`, before the
session row is created or any work is dispatched:

```python
async def create_research(
    request: ResearchRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ResearchResponse:
    await _enforce_tier(current_user, db)
    session = ResearchSession(user_id=current_user.user_id, ...)
    ...

async def _enforce_tier(user: CurrentUser, db: AsyncSession) -> None:
    sub = await db.scalar(
        select(UserSubscription).where(UserSubscription.user_id == user.user_id)
    )
    is_pro = sub is not None and sub.tier == "pro" and sub.status == "active"
    if is_pro:
        return  # unlimited

    start_of_month = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    usage = await db.scalar(
        select(func.count()).select_from(ResearchSession).where(
            ResearchSession.user_id == user.user_id,
            ResearchSession.created_at >= start_of_month,
        )
    )
    if usage >= 3:
        raise HTTPException(status_code=429, detail="Free tier limit reached (3/month). Upgrade to Pro.")
```

**Why 429 (Too Many Requests)?** It is semantically correct — the client has
exceeded a rate/quota limit. The Stripe upgrade URL is included in the response
body so the frontend can redirect immediately.

### No cached tier state

Tier status is read from the database on every request. This is intentional:
- Pro cancellations take effect immediately (no stale cache to invalidate).
- Free users who upgrade see the change on their very next request.
- The query is indexed on `user_id` and fast.

---

## Stripe Integration

### Checkout flow

```
Browser                 FastAPI                  Stripe
  |                        |                        |
  |-- POST /api/billing/checkout-session ---------->|
  |                        |-- create_checkout ------->
  |                        |<-- { url } --------------|
  |<-- { checkout_url } ---|                        |
  |                        |                        |
  |-- redirect to Stripe Checkout ----------------->|
  |<-- redirect to /dashboard?upgrade=success ------|
```

`POST /api/billing/checkout-session` (protected, requires auth) creates a Stripe
Checkout Session with:
- `mode: "subscription"`
- `price_id`: the Pro plan price ID from `Settings.stripe_pro_price_id`
- `customer_email`: from `CurrentUser.email`
- `metadata: { user_id: str(current_user.user_id) }` — carried through to the webhook
- `success_url`, `cancel_url`

### Webhook events handled

| Event | Action |
|---|---|
| `checkout.session.completed` | Upsert `UserSubscription(user_id, tier="pro", status="active", stripe_customer_id, stripe_subscription_id)` |
| `customer.subscription.deleted` | Update `UserSubscription.status = "canceled"` for matching `stripe_subscription_id` |
| `invoice.payment_failed` | Update `UserSubscription.status = "past_due"` — enforcement treats past_due as free tier |

### Webhook signature verification

```python
@router.post("/webhook")
async def stripe_webhook(request: Request, settings: Settings = Depends(get_settings)) -> dict:
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.stripe_webhook_secret
        )
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")
    ...
```

`stripe.Webhook.construct_event` verifies the HMAC-SHA256 signature in the
`Stripe-Signature` header against `STRIPE_WEBHOOK_SECRET`. This prevents replay
attacks (the timestamp is part of the signed payload) and spoofed events.

**Idempotency:** Stripe may deliver a webhook more than once. The handler uses
`INSERT ... ON CONFLICT DO UPDATE` (upsert on `stripe_subscription_id`) so
duplicate deliveries are safe.

---

## `user_subscriptions` Table Schema

```sql
CREATE TABLE user_subscriptions (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                UUID NOT NULL UNIQUE,   -- one subscription per user
    tier                   TEXT NOT NULL DEFAULT 'free',   -- 'free' | 'pro'
    status                 TEXT NOT NULL DEFAULT 'active', -- 'active' | 'canceled' | 'past_due'
    stripe_customer_id     TEXT,
    stripe_subscription_id TEXT UNIQUE,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_user_subscriptions_user_id ON user_subscriptions(user_id);
```

**SQLAlchemy ORM model** will be added to `backend/app/models/user_subscription.py`.

**Alembic migration** (t-039) will generate `versions/xxxx_add_user_subscriptions.py`
and also add the pending columns from prior milestones:
- `sources.source_type TEXT`
- `research_sessions.critique_json JSONB`
- `research_sessions.quality_score NUMERIC(4,3)`

---

## Security Considerations

### Token storage (frontend)

JWTs must be stored in `httpOnly` cookies, not `localStorage`. Supabase Auth's
`@supabase/ssr` package handles this for Next.js and sets `Secure; SameSite=Lax`
attributes automatically. This protects against XSS token theft.

### CORS

The FastAPI CORS middleware must whitelist only the Vercel production domain and
`localhost:3000` for local development. Wildcard `*` origins are never acceptable
for credentialed requests.

### JWT secret rotation

`SUPABASE_JWT_SECRET` is an environment variable injected by Railway at deploy
time. It is never committed to source control. If the secret is rotated in
Supabase, Railway's env var must be updated and the backend redeployed before
existing tokens expire (Supabase tokens have a 1-hour expiry by default).

### Stripe webhook secret

`STRIPE_WEBHOOK_SECRET` is scoped per-endpoint in the Stripe dashboard. The
webhook endpoint is configured to accept only the two events listed above — all
others are silently rejected at the Stripe level before they reach the backend.

---

## Consequences

### Positive

- No custom auth code to maintain — Supabase handles sign-up, email
  confirmation, password hashing, and refresh token rotation.
- JWT validation is local (no Supabase network hop per request).
- Stripe handles PCI compliance — we never touch card numbers.
- Freemium enforcement is a single DB query that cannot be bypassed by the client.

### Negative / risks

- **Supabase lock-in**: migrating away from Supabase Auth later would require
  issuing new tokens to all users or bridging the old tokens.
- **Stripe dependency**: payment and tier status require Stripe to be operational.
  A Stripe outage blocks new Pro upgrades but does not affect existing Pro users
  (tier status is cached in `user_subscriptions`).
- **Dev mode footgun**: the `supabase_jwt_secret=""` dev bypass is a footgun if
  a dev environment is accidentally exposed to the internet. The `WARNING` log
  line mitigates this but does not prevent it. Consider requiring a non-empty
  secret in staging environments via a startup assertion.

---

## Alternatives Considered

### Auth0 / Clerk

Rejected. Supabase Auth is already in the stack for the primary database.
Adding a second auth vendor adds cost and a second token format to reason about.

### Rolling custom JWT auth

Rejected. Custom auth is a security liability. Supabase Auth has handled the
subtle failure modes (timing-safe comparison, bcrypt cost, refresh token
rotation) for us.

### Storing tier in the JWT

Rejected. JWT claims are not updated when a user upgrades. Storing tier in the
JWT would mean Pro users wait up to 1 hour for their upgrade to take effect.
Reading tier from `user_subscriptions` at request time gives instant effect.

### Quota enforcement via Redis counter

Rejected for now. A DB query is simple, correct, and fast enough for the current
scale. Redis counters would introduce consistency risks (counter drift if Redis
flushes) and additional operational complexity. Revisit at 10k+ users/month.

---

## Implementation Plan (Milestone 5 tasks)

| Task | Description |
|---|---|
| t-038 | `backend/app/core/auth.py` — `get_current_user` dependency, protect routes |
| t-039 | Alembic migrations — `user_subscriptions`, `source_type`, `critique_json`, `quality_score` |
| t-040 | `backend/app/api/billing.py` — Stripe checkout session + webhook handler |
| t-041 | Next.js auth pages — sign-up, login, reset-password |
| t-042 | Dashboard — report history, usage meter, subscription management |
| t-043 | Playwright E2E tests — full sign-up → report → upgrade flow |
| t-044 | Lighthouse audit + mobile responsiveness |
