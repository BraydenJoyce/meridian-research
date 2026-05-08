# Meridian Research

**Autonomous market intelligence powered by a multi-agent AI pipeline.**

Submit a business research question. A team of AI agents plans, researches across 50+ sources, processes results through a DuckDB/Polars ETL pipeline, indexes findings in a RAG system, and delivers a cited intelligence report — in under 3 minutes.

[![CI](https://github.com/BraydenJoyce/meridian-research/actions/workflows/ci.yml/badge.svg)](https://github.com/BraydenJoyce/meridian-research/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue)](https://python.org)
[![Next.js 14](https://img.shields.io/badge/Next.js-14-black)](https://nextjs.org)

---

## Features

- **Multi-agent research pipeline** — Web Search, Computer Vision, News, and SEC EDGAR agents run in parallel; a Critic agent fact-checks the output
- **DuckDB/Polars ETL** — MinHash deduplication, source quality scoring, named entity extraction
- **RAG cross-session memory** — Qdrant vector store surfaces relevant prior research as context
- **YOLOv8 document classifier** — identifies charts and extracts structured data via Claude Vision
- **Real-time streaming** — Server-Sent Events stream the agent trace to the frontend as it runs
- **PDF export** — download any report as a formatted PDF
- **Freemium billing** — Supabase Auth + Stripe (3 reports/month free, unlimited Pro at $29/month)
- **Responsive dashboard** — report history, usage meter, subscription management

---

## Architecture

```
Browser (Next.js 14)
    │
    │  POST /api/research/create   GET /api/research/{id}/stream (SSE)
    ▼
FastAPI Backend (Railway)
    │
    ├── PlannerAgent ─────────────── decomposes question into sub-tasks
    │
    ├── asyncio.gather ──────────── parallel research phase (120s budget each)
    │   ├── WebSearchAgent          Tavily API → 50+ sources per sub-task
    │   ├── CvDocumentAgent         YOLOv8 classifier → Claude Vision chart extractor
    │   ├── NewsAgent               NewsAPI + GNews (concurrent)
    │   └── StructuredDataAgent     SEC EDGAR XBRL companyfacts
    │
    ├── ETL Pipeline (DuckDB + Polars)
    │   ├── Ingest → Deduplicate (MinHash LSH) → Score → Entity Extract
    │   └── Qdrant upsert (sentence-transformers embeddings)
    │
    ├── WriterAgent ─────────────── Claude Sonnet → cited markdown report
    ├── CriticAgent ─────────────── fact-checks claims, returns quality_score
    │
    └── ReportGenerator             fpdf2 → PDF export
    │
    ├── Supabase PostgreSQL ─────── research_sessions, sources, user_subscriptions
    ├── Redis ───────────────────── session queue (asyncio worker)
    └── Qdrant ──────────────────── vector store (cross-session RAG)

ML Layer (Modal GPU)
    └── YOLOv8 classifier + ONNX runtime inference server
```

---

## Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| Backend framework | Python 3.12, FastAPI, uvicorn | API server, async request handling |
| ORM | SQLAlchemy 2.0 async, Alembic | Database models, migrations |
| Validation | Pydantic v2 | Request/response schemas |
| HTTP client | async httpx | Agent web requests |
| Task queue | Redis + asyncio | Research session queue |
| Analytical DB | DuckDB 0.10 | ETL pipeline queries |
| DataFrame | Polars | Fast columnar data processing |
| Vector store | Qdrant | Semantic search, RAG context |
| ML framework | ultralytics YOLOv8, ONNX runtime | Document classification |
| GPU inference | Modal | Serverless GPU for YOLOv8 |
| Frontend | Next.js 14 (App Router), TypeScript 5 | Web application |
| Styling | Tailwind CSS, shadcn/ui | Component library |
| Streaming | Server-Sent Events (SSE) | Real-time agent trace |
| Auth | Supabase Auth (JWT HS256) | Sign-up, login, password reset |
| Primary DB | Supabase PostgreSQL | All relational data |
| Payments | Stripe (Checkout + webhooks) | Freemium billing |
| Hosting | Vercel (frontend), Railway (backend) | Production deployment |
| ML hosting | Modal | Serverless GPU inference |
| CI/CD | GitHub Actions | Test + lint on every push |
| Testing | pytest, pytest-asyncio, Playwright | Backend + E2E tests |
| Linting | ruff, mypy, eslint | Code quality |

---

## Quickstart

### Prerequisites

- Python 3.12+
- Node.js 20+
- Docker + Docker Compose
- [Supabase](https://supabase.com) project (free tier works)
- [Stripe](https://stripe.com) account (test mode)
- [Anthropic API key](https://console.anthropic.com)
- [Tavily API key](https://tavily.com)

### 1. Clone the repository

```bash
git clone https://github.com/BraydenJoyce/meridian-research.git
cd meridian-research
```

### 2. Backend setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Copy and fill in environment variables
cp .env.example .env
# Edit .env with your API keys (see Environment Variables section)

# Run database migrations
alembic upgrade head

# Start the backend
uvicorn app.main:app --reload --port 8000
```

### 3. Frontend setup

```bash
cd frontend
npm install

# Copy and fill in environment variables
cp .env.local.example .env.local
# Edit .env.local with Supabase URL and anon key

npm run dev
```

### 4. Start all services with Docker Compose

```bash
# From repo root
docker compose -f devops/docker-compose.yml up --build
```

This starts: FastAPI backend, Next.js frontend, PostgreSQL (local), Redis, Qdrant.

### 5. Run tests

```bash
# Backend
cd backend
python -m pytest tests/ -v

# Frontend unit tests
cd frontend
npx vitest run

# Frontend E2E (requires dev server running)
npx playwright test
```

---

## Environment Variables

### Backend (`backend/.env`)

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | PostgreSQL connection string (asyncpg format) |
| `REDIS_URL` | Yes | Redis connection string |
| `QDRANT_URL` | Yes | Qdrant instance URL |
| `ANTHROPIC_API_KEY` | Yes | Anthropic API key for Claude |
| `TAVILY_API_KEY` | Yes | Tavily web search API key |
| `SUPABASE_JWT_SECRET` | Yes | Supabase project JWT secret (Settings → API) |
| `STRIPE_SECRET_KEY` | Yes | Stripe secret key (`sk_live_...` or `sk_test_...`) |
| `STRIPE_WEBHOOK_SECRET` | Yes | Stripe webhook signing secret (`whsec_...`) |
| `STRIPE_PRO_PRICE_ID` | Yes | Stripe Price ID for the Pro plan |
| `SENTRY_DSN` | No | Sentry DSN for error monitoring |
| `NEWSAPI_KEY` | No | NewsAPI.org key (NewsAgent enrichment) |
| `GNEWS_KEY` | No | GNews API key (NewsAgent enrichment) |
| `MODAL_API_SECRET` | No | Modal API secret (CV agent GPU inference) |
| `ALLOWED_ORIGINS` | No | Comma-separated CORS origins (defaults to localhost:3000) |

### Frontend (`frontend/.env.local`)

| Variable | Required | Description |
|---|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | Yes | Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Yes | Supabase anon/public key |
| `NEXT_PUBLIC_API_URL` | No | Backend URL (defaults to `http://localhost:8000`) |

---

## Deployment

### Backend → Railway

1. Create a new Railway project and connect this repository
2. Set all backend environment variables in Railway → Variables
3. Railway auto-detects `devops/Dockerfile.backend`
4. Run migrations: `railway run alembic upgrade head`

### Frontend → Vercel

1. Import this repository in Vercel
2. Set `Root Directory` to `frontend`
3. Set `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY` in Vercel → Environment Variables
4. Vercel auto-deploys on every push to `main`

### ML inference → Modal

```bash
pip install modal
modal deploy ml/inference/modal_app.py
```

---

## API Reference

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/health` | None | Service health check (db, redis, version) |
| `POST` | `/api/research/create` | JWT | Start a new research session |
| `GET` | `/api/research/{id}/stream` | None | SSE stream of agent trace events |
| `GET` | `/api/research/{id}/export` | JWT | Download report as PDF |
| `POST` | `/api/billing/checkout` | JWT | Create Stripe Checkout session |
| `POST` | `/api/billing/webhook` | None (Stripe sig) | Handle Stripe webhook events |

Full interactive API docs available at `/docs` (FastAPI Swagger UI) when the backend is running.

### Research session lifecycle

```
POST /api/research/create  →  { session_id, stream_url }
                                      │
                              GET /stream (SSE)
                                      │
                    agent_started → source_fetched → report_chunk → done
```

---

## Project Structure

```
meridian-research/
├── backend/
│   ├── app/
│   │   ├── api/          # FastAPI route handlers
│   │   ├── agents/       # Research agent implementations
│   │   ├── core/         # Auth, config, middleware, rate limiting
│   │   ├── models/       # SQLAlchemy ORM models
│   │   ├── pipeline/     # DuckDB/Polars ETL pipeline
│   │   ├── schemas/      # Pydantic request/response schemas
│   │   └── services/     # Business logic layer
│   ├── alembic/          # Database migrations
│   └── tests/            # pytest test suite
├── frontend/
│   ├── app/              # Next.js App Router pages
│   ├── components/       # Shared React components (shadcn/ui)
│   ├── lib/              # Supabase client, utilities
│   └── tests/            # Vitest unit tests + Playwright E2E
├── ml/
│   ├── train/            # YOLOv8 training scripts
│   ├── inference/        # Modal deployment + ONNX inference
│   └── models/           # Model checkpoints (gitignored)
├── docs/
│   ├── adr/              # Architecture Decision Records (ADR-001 to ADR-008)
│   └── ml/               # Model card
└── devops/
    ├── Dockerfile.backend
    ├── Dockerfile.ml
    └── docker-compose.yml
```

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Make your changes and add tests
4. Ensure all checks pass: `python -m pytest tests/ && python -m ruff check .`
5. Push and open a pull request against `main`

Please follow the existing code style (ruff enforced) and add tests for any new functionality.

---

## License

MIT — see [LICENSE](LICENSE) for details.
