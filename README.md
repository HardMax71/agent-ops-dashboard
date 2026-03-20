<div align="center">

# AgentOps Dashboard

[![CI](https://img.shields.io/github/actions/workflow/status/HardMax71/agent-ops-dashboard/ci.yml?label=CI&logo=github)](https://github.com/HardMax71/agent-ops-dashboard/actions/workflows/ci.yml)
[![Evals](https://img.shields.io/github/actions/workflow/status/HardMax71/agent-ops-dashboard/eval.yml?label=Evals&logo=github)](https://github.com/HardMax71/agent-ops-dashboard/actions/workflows/eval.yml)
[![Docs](https://img.shields.io/github/actions/workflow/status/HardMax71/agent-ops-dashboard/docs.yml?label=Docs&logo=github)](https://hardmax71.github.io/agent-ops-dashboard/)
[![License](https://img.shields.io/github/license/HardMax71/agent-ops-dashboard)](LICENSE)

[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-1C3C3C?logo=langchain&logoColor=white)](https://langchain-ai.github.io/langgraph/)
[![React](https://img.shields.io/badge/React-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Redis-DC382D?logo=redis&logoColor=white)](https://redis.io/)
[![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![Prometheus](https://img.shields.io/badge/Prometheus-E6522C?logo=prometheus&logoColor=white)](https://prometheus.io/)

</div>

## Overview

AgentOps Dashboard orchestrates multi-agent pipelines for automated bug triage. GitHub issues are routed through a LangGraph supervisor that coordinates specialized agents (investigator, codebase search, web search, critic, writer) to produce structured triage reports with human-in-the-loop support.

## Quickstart

### Docker (recommended)

```bash
cp .env.example .env
# Edit .env — set OPENAI_API_KEY at minimum

docker compose up -d --build
```

API on `:8000`, frontend on `:5173`.

### Local development

```bash
uv sync --all-groups
docker compose up db redis -d
uv run uvicorn agentops.api.main:app --reload   # terminal 1
uv run arq agentops.worker.WorkerSettings        # terminal 2
```

### Tests

```bash
uv run pytest tests/unit/ -v
```
