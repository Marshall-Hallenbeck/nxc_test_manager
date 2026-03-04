# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

End-to-end testing manager for [NetExec](https://github.com/Pennyw0rth/NetExec/). Automates testing of NetExec pull requests against real Active Directory/Windows environments via ephemeral Docker containers.

**Core Workflow:**
1. User submits a PR number via the web UI
2. Backend fetches PR metadata from GitHub API
3. Celery task spins up an ephemeral Docker container
4. Container clones NetExec, checks out the PR, installs via Poetry
5. Runs `python tests/e2e_tests.py -t <target> -u <username> -p <password>` against each target
6. Logs stream in real-time via WebSocket; results saved to PostgreSQL
7. Email notification sent on completion

## Architecture

```
Frontend (Next.js :3000) ──HTTP/WS──▶ Backend (FastAPI :8000) ──▶ PostgreSQL (:5432)
                                       │                           Redis (:6379)
                                       ├── Celery Workers
                                       └── Docker SDK ──▶ Ephemeral Test Containers
```

### Stack
- **Backend**: FastAPI, SQLAlchemy, Celery, Docker SDK for Python
- **Frontend**: Next.js 16 (App Router), TypeScript, TailwindCSS
- **Database**: PostgreSQL 17 (tables auto-created via `Base.metadata.create_all()`)
- **Message Queue**: Redis 7 (Celery broker/backend + WebSocket pub/sub)
- **Containers**: Docker with `--network host` for target host connectivity

### Key Design Decisions
- No Alembic migrations — tables auto-created on startup
- Passwords never stored in database — passed ephemerally to containers
- Infinite scaling via Celery worker pool (no queue limits)
- WebSocket logs use DB polling (simpler than Redis pub/sub for this use case)
- GitHub webhooks disabled by default (configurable via env vars)

## Development Commands

### Infrastructure
```bash
# Start PostgreSQL and Redis
cd backend && docker-compose up -d

# Build the test runner image
docker build -t netexec-test-runner backend/docker/test-runner/
```

### Backend
```bash
cd backend

# Install dependencies
poetry install

# Copy and configure environment
cp .env.example .env

# Run the FastAPI server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run Celery worker (separate terminal)
celery -A app.tasks worker --loglevel=info --concurrency=3
```

### Frontend
```bash
cd frontend

# Install dependencies
npm install

# Run development server
npm run dev

# Build for production
npm run build
```

## Project Structure

```
backend/
├── app/
│   ├── main.py                  # FastAPI app with lifespan hook (table creation)
│   ├── config.py                # Pydantic Settings from .env
│   ├── database.py              # SQLAlchemy engine, session, init_db()
│   ├── api/
│   │   ├── test_runs.py         # REST endpoints (CRUD, cancel, compare, logs)
│   │   ├── websocket.py         # WS /ws/test-runs/{id}/logs (DB polling)
│   │   └── webhooks.py          # POST /webhooks/github (HMAC-SHA256 validated)
│   ├── models/
│   │   ├── test_run.py          # TestRun (status, celery_task_id, container_id)
│   │   ├── test_result.py       # TestResult (per-test, per-target outcomes)
│   │   └── test_log.py          # TestLog (streaming log lines)
│   ├── schemas/
│   │   └── test_run.py          # Pydantic request/response schemas
│   ├── services/
│   │   ├── github.py            # GitHub API (PR details via httpx)
│   │   ├── docker_manager.py    # Container lifecycle (Docker SDK)
│   │   ├── test_runner.py       # Test orchestration (IP/CIDR expansion)
│   │   └── notifier.py          # SMTP email notifications
│   └── tasks/
│       ├── __init__.py          # Celery app configuration
│       └── test_tasks.py        # run_pr_test task + cancel_test_run helper
├── docker/
│   └── test-runner/
│       ├── Dockerfile           # Python 3.12-slim + Poetry + git
│       └── run_tests.sh         # Clone PR, poetry install, run tests
├── docker-compose.yml           # PostgreSQL 16 + Redis 7
├── .env.example                 # Configuration template
└── pyproject.toml               # Python dependencies

frontend/
├── src/
│   ├── app/
│   │   ├── layout.tsx           # Root layout with nav bar
│   │   ├── page.tsx             # PR submission form (home page)
│   │   ├── runs/
│   │   │   ├── page.tsx         # Test runs list (filtered, paginated)
│   │   │   └── [id]/page.tsx    # Run detail + live logs + cancel
│   │   └── compare/page.tsx     # Side-by-side run comparison
│   ├── components/
│   │   ├── StatusBadge.tsx      # Color-coded status badges
│   │   └── LogViewer.tsx        # Terminal-style log viewer (WebSocket)
│   ├── lib/
│   │   ├── api.ts               # API client (all backend endpoints)
│   │   └── websocket.ts         # useTestRunLogs React hook
│   └── types/index.ts           # TypeScript interfaces
├── package.json
└── tsconfig.json
```

## API Endpoints

### REST (prefix: `/api/test-runs`)
- `POST /` — Submit new test run (pr_number, optional: target_hosts, username, password)
- `GET /` — List runs (query: page, status filter)
- `GET /{id}` — Run detail with results
- `POST /{id}/cancel` — Cancel queued/running run
- `DELETE /{id}` — Delete completed/cancelled run
- `GET /{id}/logs` — Fetch log entries (query: after timestamp)
- `GET /compare` — Compare two runs (query: run1, run2)

### WebSocket
- `WS /ws/test-runs/{id}/logs` — Real-time log streaming

### Webhooks
- `POST /webhooks/github` — GitHub PR event receiver (HMAC-SHA256 validated)

## Configuration

All config via environment variables (see `backend/.env.example`):
- `DATABASE_URL` — PostgreSQL connection string
- `REDIS_URL` — Redis connection string
- `GITHUB_TOKEN` — GitHub API token (required)
- `DEFAULT_TARGET_HOSTS` — Default target(s): single IP, comma-separated, CIDR, or mixed
- `DEFAULT_TARGET_USERNAME` / `DEFAULT_TARGET_PASSWORD` — Default credentials
- `SMTP_*` — Email notification settings
- `CONTAINER_TIMEOUT` — Test timeout in seconds (default: 1800)
- `CONTAINER_MEMORY_LIMIT` — Memory limit per container (default: 2g)
- `WEBHOOK_ENABLED` — Enable GitHub webhooks (default: false)
- `WEBHOOK_SECRET` — HMAC-SHA256 secret for webhook validation

## Important Notes

### Security
- Passwords are NEVER stored in the database
- Credentials are passed as environment variables to ephemeral containers
- Web UI has no authentication (intended for trusted network use only)
- `.env` file should have restricted permissions (`chmod 600`)

### Target Host Input
Supports flexible target specification:
- Single IP: `192.168.33.96`
- Comma-separated: `192.168.33.96,192.168.33.97`
- CIDR subnet: `192.168.33.0/24`
- Mixed: `192.168.33.0/24,192.168.33.50`

### Test Run Statuses
`queued` → `running` → `completed` | `failed` | `cancelled`

### Cancellation
- Revokes Celery task
- Stops and removes Docker container
- Updates database status to `cancelled`
