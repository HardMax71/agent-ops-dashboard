FROM python:3.12-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl git \
    && rm -rf /var/lib/apt/lists/*

RUN pip install uv

WORKDIR /app

# Install dependencies first (layer cache)
COPY pyproject.toml uv.lock* ./
COPY agents/ agents/
RUN uv sync --no-dev --no-install-project

# Copy source + alembic
COPY src/ src/
COPY alembic/ alembic/
COPY alembic.ini .
RUN uv sync --no-dev

ENV PATH="/app/.venv/bin:$PATH"

RUN groupadd --system appuser && useradd --system --gid appuser appuser \
    && chown -R appuser:appuser /app
USER appuser

# ── API target ────────────────────────────────────────────────────────
FROM base AS api
EXPOSE 8000 8001
CMD ["sh", "-c", "alembic upgrade head && uvicorn agentops.api.main:app --host 0.0.0.0 --port 8000"]

# ── Worker target ─────────────────────────────────────────────────────
FROM base AS worker
EXPOSE 8002
CMD ["python", "-m", "agentops.worker"]
