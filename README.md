# AgentOps Dashboard

A Jira-like dashboard for AI agent operations, built with FastAPI, LangGraph, and the full LangChain ecosystem.

## Overview

AgentOps Dashboard orchestrates multi-agent pipelines for automated bug triage. GitHub issues are routed through a LangGraph supervisor that coordinates specialized agents (investigator, codebase search, web search, critic, writer) to produce structured triage reports with human-in-the-loop support.

**Key tech:** FastAPI · LangGraph · LangChain · LangServe · ARQ (async Redis queue) · PostgreSQL · Redis · OpenTelemetry · Prometheus

Docs: https://hardmax71.github.io/agent-ops-dashboard/

## Quickstart

### Docker (recommended)

```bash
cp .env.example .env
# Edit .env — set OPENAI_API_KEY at minimum

docker compose up -d --build
```

That's it. API on `:8000`, frontend on `:5173`.

To include LangServe agents, Prometheus, and LangFlow:

```bash
docker compose --profile full up -d --build
```

### Local development

For running api/worker outside Docker (hot reload, debugger):

```bash
uv sync --all-groups
docker compose up db redis -d     # infra only
uv run uvicorn agentops.api.main:app --reload   # terminal 1
uv run python -m agentops.worker                 # terminal 2
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
  models/       Shared typed models (JobData, WorkerContext)
  lifespan.py   App startup/shutdown (Redis, metrics)
  worker.py     ARQ worker for async job processing

agents/
  investigator/ Standalone LangServe microservice
```

**Metrics ports:** API → 8001, Worker → 8002 (Prometheus scrape targets)

## Docker Compose profiles

| Command | What you get |
|---|---|
| `docker compose up -d --build` | API, worker, frontend, PostgreSQL, Redis |
| `docker compose --profile agents up -d --build` | + 5 LangServe agent services |
| `docker compose --profile full up -d --build` | + agents, Prometheus, LangFlow |

## Project structure notes

- All PRDs in `docs/prd/`
- Roadmap: `docs/plans/roadmap-v1.md`
- No `isinstance()`, `cast()`, `type()`, or `Any` in business logic
- Redis always uses `decode_responses=True`
- No try/except in business logic — service-wide handlers only
