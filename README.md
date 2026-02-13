# NetExec E2E Testing Manager

Web-based end-to-end testing manager for [NetExec](https://github.com/Pennyw0rth/NetExec/) pull requests. Automates PR testing against real Active Directory/Windows environments via ephemeral Docker containers.

## Quick Start (Docker)

The easiest way to run everything:

```bash
# Optional: configure target hosts, credentials, etc.
cp backend/.env.example backend/.env
# Edit backend/.env as needed

# Start the full stack
docker compose up -d
```

This starts PostgreSQL, Redis, the backend API, a Celery worker, the frontend, and an nginx reverse proxy. Only nginx is exposed on the host — all other services are internal to the Docker network. Open http://localhost:9000 to use the UI.

To stop everything:

```bash
docker compose down
```

## Development Setup

For local development without Docker (for the app itself):

### Prerequisites

- Python 3.12+, Poetry
- Node.js 22+, npm
- Docker (still needed for PostgreSQL, Redis, and test runner containers)

### 1. Start infrastructure

```bash
cd backend
docker compose up -d   # PostgreSQL + Redis
```

### 2. Configure environment

```bash
cd backend
cp .env.example .env
# Edit .env with your target hosts, credentials, etc.
```

### 3. Start the backend

```bash
cd backend
poetry install
poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 4. Start the Celery worker (separate terminal)

```bash
cd backend
poetry run celery -A app.tasks worker --loglevel=info --concurrency=3
```

### 5. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

### 6. Open the UI

Visit http://localhost:3333 (dev) or http://localhost:9000 (Docker), enter a PR number, and submit a test run.

## How It Works

1. You submit a PR number via the web UI
2. A Celery task spins up an ephemeral Docker container
3. The container clones NetExec, checks out the PR, installs with Poetry
4. Runs `python tests/e2e_tests.py -t <target> -u <username> -p <password>`
5. Logs stream in real-time via WebSocket
6. Results are saved to PostgreSQL and viewable in the UI
7. Email notification is sent on completion (if SMTP configured)

## Features

- **PR Testing**: Submit any NetExec PR number for automated e2e testing
- **Real-time Logs**: Live log streaming via WebSocket while tests run
- **Flexible Targets**: Single IP, comma-separated IPs, CIDR subnets, or mixed
- **Concurrent Runs**: Unlimited parallel test runs via Celery worker pool
- **Cancellation**: Cancel queued or running tests at any time
- **Test History**: Browse, filter, and paginate past test runs
- **Comparison**: Side-by-side comparison of any two test runs
- **GitHub Webhooks**: Auto-test PRs on open/push (disabled by default)
- **Email Notifications**: SMTP notifications on test completion

## Running Tests

```bash
# Backend
cd backend
poetry run pytest tests/ -v
poetry run ruff check app/

# Frontend
cd frontend
npm run build
npm test
```

## API Documentation

With the backend running, visit:
- Swagger UI: http://localhost:9000/docs (Docker) or http://localhost:8888/docs (dev)
- ReDoc: http://localhost:9000/redoc (Docker) or http://localhost:8888/redoc (dev)

## Configuration

All settings via environment variables in `backend/.env`. See [backend/.env.example](backend/.env.example) for all options including:

- Database and Redis connection strings
- Default target hosts and credentials
- SMTP notification settings
- Container timeout and memory limits
- GitHub webhook configuration
