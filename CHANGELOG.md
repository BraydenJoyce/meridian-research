# Changelog

All notable changes to Meridian Research are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [1.0.0-beta] - 2026-04-30

### Added

#### Core research pipeline (Milestone 1)
- FastAPI backend with async SQLAlchemy 2.0 and Supabase PostgreSQL
- `POST /api/research/create` — accepts a research question, returns `session_id`
- PlannerAgent — decomposes questions into 3–10 parallel sub-tasks using Claude
- WebSearchAgent — retrieves sources via Tavily API for each sub-task
- WriterAgent — produces a cited markdown intelligence report via Claude Sonnet
- Server-Sent Events (SSE) streaming of real-time agent trace events
- Next.js 14 (App Router) frontend with research input form and live trace stream
- `GET /health` endpoint for uptime monitoring
- Initial Alembic migration (`0001`) with `research_sessions`, `sources`, `agent_events` tables
- Docker Compose setup for local development (backend, PostgreSQL, Redis, Qdrant)
- GitHub Actions CI workflow — pytest + ruff on every push to `main`

#### Data engineering layer (Milestone 2)
- DuckDB + Polars ETL pipeline with four stages: ingest, deduplicate, score, entity extract
- MinHash LSH deduplication — reduces duplicate sources by >40% on typical datasets
- Source quality scorer — assigns relevance scores in [0.0, 1.0] with documented criteria
- Named entity extraction — identifies ORG, PERSON, PRODUCT, METRIC entities via spaCy
- Structured logging (structlog) — every pipeline stage emits `records_in/out/dropped`
- Qdrant vector store integration — sentence-transformers embeddings for all sources
- RAG cross-session retrieval — prior research surfaces as context for new queries
- Pipeline benchmark: 1,000 sources processed in < 60 seconds

#### Computer vision integration (Milestone 3)
- YOLOv8 document classifier — 8 classes: bar_chart, line_chart, pie_chart, scatter_plot, table, diagram, infographic, other
- Claude Vision chart extractor — returns structured JSON (title, series, key insight, x/y axes)
- Modal GPU inference server — cold-start < 5 seconds, ONNX export for portability
- `CvDocumentAgent` — parallel research agent that classifies and extracts chart data
- Alembic migration (`0003`) — `chart_extractions` table, `sources.source_type` column
- Model card at `docs/ml/model_card.md` — architecture, training config, limitations
- Git LFS tracking for `*.onnx` and `*.pt` model artifacts

#### Multi-agent expansion (Milestone 4)
- `NewsAgent` — fetches from NewsAPI + GNews concurrently; de-duplicates by URL
- `StructuredDataAgent` — SEC EDGAR XBRL companyfacts API; max 3 companies, 5 facts each
- `CriticAgent` — Claude fact-checks WriterAgent output; returns `quality_score` [0.0, 1.0] and `flagged_claims`
- Agent orchestrator (`research_worker.py`) — `asyncio.gather` parallelism with 120s per-agent timeout
- PDF export (`report_generator.py`) — fpdf2 + mistune markdown→PDF; `GET /api/research/{id}/export`
- Report quality scorer — word count, citation density, section count, Flesch-Kincaid grade, composite score
- Agent parallelism benchmark: 4 agents × 0.3s → **3.99x speedup** over sequential
- Alembic migrations (`0004`) — `research_sessions.critique_json`, `research_sessions.quality_score`
- ADR-007 — multi-agent parallelism design with error handling matrix and timeout budget

#### Auth, billing, and product polish (Milestone 5)
- Supabase Auth JWT middleware — `get_current_user` FastAPI dependency (HS256, audience verification)
- Dev mode — accepts any valid JWT when `SUPABASE_JWT_SECRET` is unset (logs WARNING)
- Route protection — `POST /api/research/create` and `GET /api/research/{id}/export` require auth
- Freemium tier enforcement — free users blocked after 3 reports/month (HTTP 429)
- Stripe Checkout integration — `POST /api/billing/checkout` creates checkout session
- Stripe webhook handler — `checkout.session.completed` upgrades to Pro; `customer.subscription.deleted` downgrades
- `user_subscriptions` table and `UserSubscription` ORM model
- Alembic migration (`0005`) — `user_subscriptions` table
- Next.js auth pages — `/auth/login`, `/auth/signup`, `/auth/reset-password`
- Next.js middleware — protects `/dashboard/*`, redirects unauthenticated users to login
- Dashboard page — usage meter (Progress component), report history, Upgrade to Pro button
- Report viewer — ReactMarkdown + remark-gfm; citation links open in new tab; Download PDF button
- shadcn/ui components added: Input, Label, Card, Progress
- Playwright E2E test suite — 12 tests covering auth pages, research form, dashboard, report viewer
- Lighthouse audit — HTML report at `docs/lighthouse_report.html`; viewport meta tag; ARIA improvements
- ADR-008 — auth and billing architecture (JWT flow, Stripe webhooks, freemium model)

#### Launch preparation (Milestone 6)
- Comprehensive `README.md` with architecture diagram, tech stack table, quickstart, and API reference
- Rate limiting via slowapi — per-IP limits on all public endpoints (10 req/min on create, 100/min on webhook)
- Sentry SDK integration — error monitoring initialized from `SENTRY_DSN` env var
- Enhanced `/health` endpoint — returns `db`, `redis`, and `version` status
- CORS hardening — `allowed_origins` fully configurable via `ALLOWED_ORIGINS` env var
- Google-style docstrings on all public API route handlers and service functions
- `launch_checklist.md` — all pre-launch items verified

### Security

- JWT tokens verified with HS256 algorithm and `audience="authenticated"` claim
- Stripe webhook HMAC-SHA256 signature verification via `stripe.Webhook.construct_event`
- Supabase Auth tokens stored in `httpOnly` cookies via `@supabase/ssr` (prevents XSS theft)
- CORS restricted to explicit origin allowlist — wildcard `*` never used in production
- Stripe webhook endpoint scoped to two events only (`checkout.session.completed`, `customer.subscription.deleted`)
- Rate limiting on all public endpoints — prevents abuse and brute-force
- `SUPABASE_JWT_SECRET` and `STRIPE_WEBHOOK_SECRET` injected at deploy time, never committed

### Changed

- `/health` response extended from `{status, version}` to `{status, version, db, redis}`
- `POST /api/research/create` now requires `Authorization: Bearer <JWT>` header
- `GET /api/research/{id}/export` now requires `Authorization: Bearer <JWT>` header
- `ResearchSession` model extended with `critique_json`, `quality_score`, `user_id` (used for tier enforcement)
- `Source` model extended with `source_type` (`web`, `news`, `edgar`)

[1.0.0-beta]: https://github.com/BraydenJoyce/meridian-research/releases/tag/v1.0.0-beta
