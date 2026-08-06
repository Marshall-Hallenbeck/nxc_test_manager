FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install poetry==2.3.2

WORKDIR /app

# No glob on poetry.lock: a missing lock file must fail the build, not silently
# resolve fresh versions that drift from the local environment. `poetry install`
# also refuses a lock file that is stale relative to pyproject.toml.
COPY pyproject.toml poetry.lock ./
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --no-root

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
