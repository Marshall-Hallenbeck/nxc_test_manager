# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

End-to-end testing manager for [NetExec](https://github.com/Pennyw0rth/NetExec/). Automates testing of NetExec pull requests against real Active Directory/Windows environments via ephemeral Docker containers.

**Core Workflow:**
1. User submits a PR number (or branch name + repo) via the web UI
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
- **Frontend**: Next.js 16 (App Router), TypeScript, TailwindCSS v4 (`@plugin` syntax, not `plugins: []`)
- **Database**: PostgreSQL 17 (tables auto-created via `Base.metadata.create_all()`)
- **Message Queue**: Redis 7 (Celery broker/backend + WebSocket pub/sub)
- **Containers**: Docker with `--network host` for target host connectivity

### Key Design Decisions
- No Alembic migrations — tables auto-created on startup
- Passwords stored in DB for re-run convenience; never exposed in API responses
- Infinite scaling via Celery worker pool (no queue limits)
- WebSocket logs use DB polling (simpler than Redis pub/sub for this use case)
- GitHub webhooks disabled by default (configurable via env vars)

## Development Commands

### Docker Compose (primary)
```bash
# Start everything (from repo root)
docker compose up -d

# Rebuild after dependency changes (pyproject.toml or package.json)
docker compose up -d --build backend celery-worker  # Python deps
docker compose up -d --build frontend               # npm deps

# Code changes: backend auto-reloads (uvicorn --reload), frontend auto-reloads (next dev)
# Celery worker needs: docker compose restart celery-worker
# .env changes: services must be RECREATED, not restarted:
docker compose up -d backend celery-worker              # recreates on a changed value
docker compose up -d --force-recreate backend celery-worker  # if in doubt
```

**`docker compose restart` will NOT apply an `.env` edit** — it reuses the existing
container along with the environment Compose baked in at creation from
`env_file: ./backend/.env`. Use `up -d`, which detects a changed *value* and recreates
the container; a comment-only edit is correctly treated as no change.

### Local (without Docker)
```bash
cd backend && poetry install && cp .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
celery -A app.tasks worker --loglevel=info --concurrency=3  # separate terminal

cd frontend && npm install && npm run dev
```

### Testing
```bash
# Backend (from repo root or backend/)
cd backend && poetry run pytest tests/

# Frontend (from repo root or frontend/)
cd frontend && npx vitest run
```

## Project Structure

```
backend/
├── app/
│   ├── main.py                  # FastAPI app with lifespan hook (table creation)
│   ├── config.py                # Pydantic Settings from .env
│   ├── database.py              # SQLAlchemy engine, session, init_db()
│   ├── mcp_server.py            # MCP tools generated from the FastAPI routes
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
│   │   ├── ai_review.py         # AI review via Claude CLI
│   │   ├── empire.py            # Empire C2 API client
│   │   ├── test_runner.py       # Test orchestration (IP/CIDR expansion)
│   │   └── notifier.py          # SMTP email notifications
│   └── tasks/
│       ├── __init__.py          # Celery app configuration
│       └── test_tasks.py        # run_pr_test task + cancel_test_run helper
├── docker/
│   └── test-runner/
│       ├── Dockerfile           # Python 3.12-slim + Poetry + git
│       └── run_tests.sh         # Clone PR, poetry install, run tests
├── docker-compose.yml           # PostgreSQL 17 + Redis 7
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
│   │   ├── ThemeProvider.tsx    # next-themes dark/light mode provider
│   │   ├── ThemeToggle.tsx      # Dark/light mode toggle button
│   │   └── LogViewer.tsx        # Terminal-style log viewer (WebSocket)
│   ├── lib/
│   │   ├── api.ts               # API client (all backend endpoints)
│   │   ├── claude.ts            # useClaudeAvailability hook
│   │   └── websocket.ts         # useTestRunLogs React hook
│   └── types/index.ts           # TypeScript interfaces
├── package.json
└── tsconfig.json
```

## API Endpoints

### REST (prefix: `/api/runs`)
- `POST /` — Submit new test run (pr_number, optional: target_hosts, username, password)
- `GET /` — List runs (query: page, status filter)
- `GET /{id}` — Run detail with results
- `POST /{id}/cancel` — Cancel queued/running run
- `POST /{id}/rerun` — Clone a run with same settings (password stays server-side)
- `DELETE /{id}` — Delete completed/cancelled run
- `GET /{id}/logs` — Fetch all log entries for a run (no query params)
- `GET /compare` — Compare two runs (query: run1, run2)

### WebSocket
- `WS /ws/test-runs/{id}/logs` — Real-time log streaming

### AI Review
- `POST /{id}/review` — trigger AI review for a completed run
- `GET /{id}/review/available` — check if Claude CLI is on PATH

### Webhooks
- `POST /webhooks/github` — GitHub PR event receiver (HMAC-SHA256 validated)

### MCP
- `POST /mcp/` — MCP streamable HTTP endpoint (see MCP Server below)

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
- Passwords are stored in the database for re-run convenience (trusted network only)
- Passwords are never exposed in API responses or URL parameters
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

### Docker Networking
- Backend/celery-worker reach Empire via Docker DNS: `EMPIRE_HOST=empire` (set in docker-compose.yml)
- Ephemeral test containers use `--network host`, so they reach Empire at `127.0.0.1:1337` (hardcoded in the `EMPIRE_HOST`/`EMPIRE_PORT` env dict in `docker_manager.py:run_test_container`)
- These are two different network contexts — don't unify them

### Settings & Configuration
- `config.py:settings` is a singleton read once at import — all modules share it
- Config reaches containers exactly one way: `env_file: ./backend/.env` in
  `docker-compose.yml`, which Compose expands into container environment variables
  **at container creation**
- **Every `.env` change therefore requires recreating the container** — a
  `docker compose restart` reuses the existing container and its environment, so the
  edit is silently ignored:
  ```bash
  docker compose up -d backend celery-worker   # recreates when a value changed
  ```
- Symptom to recognize: an updated credential in `.env` still failing with the old
  value's error (e.g. GitHub 401) after a `docker compose restart`
- There is deliberately no runtime reload. A previous `reload_settings()` +
  `./backend/.env:/app/.env` mount could never work: pydantic-settings ranks
  environment variables above the `.env` file, so the start-time env var always
  shadowed the re-read file. Both were removed rather than left as a trap.

### Quality Gate Notes
- `ruff check`: run from `backend/` directory (config is in `pyproject.toml`)
- `pyright`: run from `backend/` directory — `poetry run pyright`
- ESLint: bracket escaping in `[id]` route paths is fragile — use `npx eslint src/` to lint all frontend files
- Frontend build (`npm run build`) includes TypeScript checking

### AI Review
- Optional per-run feature: user checks "AI Review" when submitting
- `POST /{id}/review` requires a PR number — branch-only runs return 400
- `ai_review.py` shells out to the `claude` CLI (finds it on PATH)
- Stores result in `TestRun.ai_summary` / `TestRun.ai_review_status`
- Frontend renders via `react-markdown` + `@tailwindcss/typography`
- `frontend/src/lib/claude.ts` — `useClaudeAvailability` hook

### MCP Server
Lets an AI coding agent working in the NetExec repo drive this manager. Registered
with `claude mcp add --scope user --transport http nxc-test-manager http://localhost:9000/mcp/`.

- `mcp_server.py:build_mcp` calls `FastMCP.from_fastapi(app)`, so the REST API is the
  single source of truth — a new route becomes a tool with no extra code
- `build_mcp(app)` runs at the bottom of `main.py`, **after every `include_router` call**.
  Routes added later will not appear as tools
- `ROUTE_MAPS` excludes `DELETE /{id}`, `/webhooks/*`, `/`, and `/health`
- **Every route in `api/test_runs.py` sets an explicit `operation_id`** — that string is
  the agent-facing tool name. Without it FastAPI generates one from handler name + path +
  method (`create_test_run_api_runs_post`), so renaming a handler would rename the tool.
  A new route with no `operation_id` gets an unusable generated name;
  `tests/test_mcp_server.py` fails the build for both cases
- `wait_for_test_run` is hand-written, not generated. It polls the DB in a thread and
  raises on timeout rather than returning a non-terminal status
- The MCP session lifespan is chained inside `main.py:lifespan` via
  `async with mcp_app.lifespan(app)`. Without it the mount returns session errors
- nginx needs `proxy_buffering off` on `/mcp` — responses are SSE streams
- FastMCP 3 requires `starlette>=1.0.1`, which forces `fastapi>=0.133`

### Dependency Pinning
- `backend/Dockerfile` copies `poetry.lock` with **no glob**. A missing lock file fails the
  build instead of resolving fresh versions that drift from the local venv. Poetry itself
  rejects a lock that is stale relative to `pyproject.toml`, so no extra check is needed.
- Poetry is pinned in the image (`pip install poetry==2.3.2`) so resolver behaviour cannot
  change between builds.
- Project metadata lives in `[project]` (PEP 621) with `dynamic = ["dependencies"]`;
  dependencies stay in `[tool.poetry.dependencies]`. `package-mode = false` — this is an
  application, not a library. `poetry check` must report "All set!" with no warnings.
- If `poetry lock` exits 139 with no output, the keyring backend segfaulted. Fixed on this
  machine with `poetry config keyring.enabled false`.

### TailwindCSS v4 Theming
Colors are defined in three layers in `globals.css`:
1. CSS variables in `:root` / `.dark` (e.g. `--card-bg`, `--accent`)
2. `@theme inline` block maps them to Tailwind tokens (e.g. `--color-card: var(--card-bg)`)
3. Components use Tailwind classes (e.g. `bg-card`, `text-muted`, `border-input-border`)
Never use `bg-[var(--*)]` — always define a theme token.

## React Patterns

### useEffect dependency arrays with polled state

When a `useEffect` accesses properties of a polled object (e.g. `run.status` where `run` is refreshed every 5 seconds), don't add the full object to the dep array — that re-fires the effect on every poll. Instead, extract the needed properties into variables outside the effect:

```tsx
const runStatus = run?.status;
const aiEnabled = run?.ai_review_enabled;

useEffect(() => {
  if (runStatus === "completed" && aiEnabled) { ... }
}, [runStatus, aiEnabled]);
```

This satisfies `react-hooks/exhaustive-deps` without causing spurious re-runs.
