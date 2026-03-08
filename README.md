# AgentOps Dashboard

A Jira-like dashboard for AI agent operations, built with FastAPI, LangGraph, and the full LangChain ecosystem.

## Overview

AgentOps Dashboard orchestrates multi-agent pipelines for automated bug triage. GitHub issues are routed through a LangGraph supervisor that coordinates specialized agents (investigator, codebase search, web search, critic, writer) to produce structured triage reports with human-in-the-loop support.

**Key tech:** FastAPI · LangGraph · LangChain · LangServe · ARQ (async Redis queue) · PostgreSQL · Redis · OpenTelemetry · Prometheus

Docs: https://hardmax71.github.io/agent-ops-dashboard/

## Quickstart

### Prerequisites

- Python 3.12
- [uv](https://docs.astral.sh/uv/) package manager
- Docker & Docker Compose

### Local development

```bash
# Clone and enter the repo
git clone https://github.com/hardmax71/agent-ops-dashboard
cd agent-ops-dashboard

# Copy and fill in env
cp .env.example .env
# Edit .env — at minimum set OPENAI_API_KEY

# Install dependencies
uv sync --all-groups

# Start infrastructure
docker compose up db redis -d

# Run the API
uv run uvicorn agentops.api.main:app --reload

# Run the worker (separate terminal)
uv run python -m agentops.worker
```

### Running tests

```bash
uv run pytest tests/unit/ -v
```

### Linting

```bash
uv run ruff check .
uv run ruff format .
```

## Architecture

```text
src/agentops/
  api/          FastAPI app, routers, dependency injection
  auth/         JWT + GitHub OAuth, security middleware
  config.py     Pydantic settings (env-driven)
  graph/        LangGraph state, nodes, supervisor routing
  metrics/      OpenTelemetry + Prometheus setup
  lifespan.py   App startup/shutdown (Redis, metrics)
  worker.py     ARQ worker for async job processing

agents/
  investigator/ Standalone LangServe microservice
```

**Metrics ports:** API → 8001, Worker → 8002 (Prometheus scrape targets)

## Project structure notes

- All PRDs in `docs/prd/`
- Roadmap: `docs/plans/roadmap-v1.md`
- No `isinstance()`, `cast()`, `type()`, or `Any` in business logic
- Redis always uses `decode_responses=True`
- No try/except in business logic — service-wide handlers only
