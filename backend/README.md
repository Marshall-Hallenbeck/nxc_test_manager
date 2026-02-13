# NetExec Test Manager - Backend

Backend API for the NetExec E2E Testing Manager, built with FastAPI.

## Setup

### Prerequisites
- Python 3.12+
- Poetry
- Docker and Docker Compose

### Installation

1. Install dependencies:
```bash
poetry install
```

2. Copy the example environment file:
```bash
cp .env.example .env
```

3. Edit `.env` with your configuration (database, Redis, credentials, etc.)

4. Start PostgreSQL and Redis:
```bash
docker-compose up -d
```

### Running the API

Development server:
```bash
poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Or use Poetry scripts:
```bash
poetry run python -m uvicorn app.main:app --reload
```

### Running Celery Worker

```bash
poetry run celery -A app.tasks worker --loglevel=info --concurrency=3
```

For more workers (increase concurrency):
```bash
poetry run celery -A app.tasks worker --loglevel=info --concurrency=10
```

## API Documentation

Once the server is running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Project Structure

```
backend/
├── app/
│   ├── main.py              # FastAPI application
│   ├── config.py            # Configuration
│   ├── database.py          # Database setup
│   ├── models/              # SQLAlchemy models
│   ├── schemas/             # Pydantic schemas
│   ├── api/                 # API routes
│   ├── services/            # Business logic
│   └── tasks/               # Celery tasks
├── docker/                  # Dockerfiles
├── tests/                   # Tests
├── docker-compose.yml       # Dev environment
└── pyproject.toml           # Dependencies
```

## Testing

Run tests:
```bash
poetry run pytest
```

With coverage:
```bash
poetry run pytest --cov=app tests/
```

## Development

Format code:
```bash
poetry run black app/
```

Lint code:
```bash
poetry run ruff check app/
```
