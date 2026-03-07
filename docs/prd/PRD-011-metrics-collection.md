---
id: PRD-011
title: Metrics Collection & Domain Events
status: DRAFT
domain: observability
depends_on: [PRD-003, PRD-004, PRD-005]
key_decisions: [domain-event-bus, prometheus-handlers, no-metrics-in-business-logic]
---

# PRD-011 — Metrics Collection & Domain Events

| Field        | Value                                                                            |
|--------------|----------------------------------------------------------------------------------|
| Document ID  | PRD-011                                                                          |
| Version      | 1.0                                                                              |
| Status       | DRAFT                                                                            |
| Date         | March 2026                                                                       |
| Parent Doc   | [PRD-001](PRD-001-master-overview.md)                                            |
| Related Docs | [PRD-003](PRD-003-langgraph-orchestration.md), [PRD-005-1](PRD-005-1-langsmith-api-spec.md) |

---

## 1. Problem Statement

Across LangGraph nodes, LCEL chains, LangServe agents, FastAPI routes, and ARQ workers,
metrics collection code (Prometheus counters, LangSmith feedback calls, DB cache writes)
naturally wants to live inside business logic. This creates three compounding problems:

**Hard to test.** Every unit test for a supervisor node or investigator chain must mock
`prometheus_client`, `langsmith.Client`, and a DB session — even when the test only cares
about routing decisions or output parsing. Mocking infrastructure in unit tests is a signal
that the architecture is wrong.

**Hard to read.** Metric calls inside a node obscure business intent:

```python
# Bad: metric call inside supervisor node
def supervisor_node(state: BugTriageState) -> dict:
    decision = pick_next_agent(state)           # business logic
    agent_calls_total.labels(decision).inc()    # metric — shouldn't be here
    return {"next_agent": decision}
```

**Hard to change.** When a Prometheus label name needs updating or LangSmith's `create_feedback`
signature changes, the change is scattered across every file that calls it. There is no single
place to find all metric recording.

**The rule:** Business code must be provably correct without knowing anything about metrics.
Metric recording must be provably complete without knowing anything about business logic.

---

## 2. Scope

This PRD covers all metric recording that requires explicit code:

| Metric category                | Sink              | Mechanism              |
|--------------------------------|-------------------|------------------------|
| Prometheus infrastructure      | `/metrics` endpoint | Prometheus counters/histograms |
| LangSmith custom feedback      | LangSmith API     | `client.create_feedback()`, annotation queue |
| In-app job statistics          | PostgreSQL        | `job_trace_summaries` table (see PRD-005-1 §4) |

**Not in scope:**

- LangSmith auto-instrumentation (zero-code via env vars; covered in PRD-005 §Integration Setup)
- Structured application logging (separate concern; use Python `logging` module directly)
- Distributed tracing beyond LangSmith (out of v1 scope)

---

## 3. Architecture: Three Layers

```
┌────────────────────────────────────────────────────────────────────┐
│  Layer 1: Business Logic                                            │
│  LangGraph nodes · LCEL chains · LangServe agents · FastAPI routes │
│  Imports ONLY from agentops.events — emits typed domain events     │
│  Zero knowledge of Prometheus, LangSmith SDK, or DB metric writes  │
└───────────────────────────┬────────────────────────────────────────┘
                            │  await event_bus.publish(SomeEvent(...))
┌───────────────────────────▼────────────────────────────────────────┐
│  Layer 2: Event Bus (agentops.metrics.bus)                          │
│  Routes events to subscribed handlers                               │
│  Handler exceptions never propagate to business logic              │
└───────────────────────────┬────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
┌───────────────┐  ┌─────────────────┐  ┌──────────────┐
│ Prometheus    │  │ LangSmith       │  │ DbCache      │
│ Handler       │  │ Feedback Handler│  │ Handler      │
│               │  │                 │  │              │
│ All Prometheus│  │ create_feedback │  │ list_runs,   │
│ counter/histo │  │ annotation queue│  │ DB upsert    │
│ gauge ops     │  │                 │  │              │
└───────────────┘  └─────────────────┘  └──────────────┘
```

---

## 4. Domain Event Catalog

All domain events are typed Python dataclasses in `agentops/events.py`. Business logic imports
from this module only. No handler imports are allowed in this file.

```python
# agentops/events.py
from dataclasses import dataclass

# --- Job lifecycle ---

@dataclass
class JobStarted:
    job_id: str
    repository: str
    issue_url: str

@dataclass
class JobCompleted:
    job_id: str
    duration_ms: float
    final_confidence: float
    severity: str          # "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"

@dataclass
class JobFailed:
    job_id: str
    error: str

# --- Agent lifecycle ---

@dataclass
class AgentInvoked:
    job_id: str
    agent_name: str        # "investigator" | "codebase_search" | "web_search" | "critic" | "writer"

@dataclass
class AgentCompleted:
    job_id: str
    agent_name: str
    duration_ms: float
    confidence: float

@dataclass
class AgentFailed:
    job_id: str
    agent_name: str
    error: str

@dataclass
class AgentTokensConsumed:
    job_id: str
    agent_name: str
    model: str             # "gpt-4o" | "gpt-4o-mini"
    input_tokens: int
    output_tokens: int
    cost_usd: float

# --- Cost budget ---

@dataclass
class CostBudgetExceeded:
    job_id: str
    current_cost_usd: float
    budget_usd: float

# --- Human interrupt ---

@dataclass
class HumanInterruptTriggered:
    job_id: str

@dataclass
class HumanInterruptAnswered:
    job_id: str
    wait_seconds: float

@dataclass
class HumanInterruptTimedOut:
    job_id: str

# --- User feedback ---

@dataclass
class UserFeedbackSubmitted:
    job_id: str
    langsmith_run_id: str
    positive: bool
    comment: str | None

# --- Codebase index ---

@dataclass
class IndexBuildCompleted:
    repo_url: str
    duration_ms: float
    document_count: int

@dataclass
class IndexBuildFailed:
    repo_url: str
    error: str
```

---

## 5. In-Process Event Bus

```python
# agentops/metrics/bus.py
import asyncio
import logging
from collections import defaultdict
from typing import Any, Callable, Coroutine, Type

logger = logging.getLogger(__name__)

Handler = Callable[[Any], Coroutine[Any, Any, None]]

class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[type, list[Handler]] = defaultdict(list)

    def subscribe(self, event_type: Type, handler: Handler) -> None:
        self._handlers[event_type].append(handler)

    async def publish(self, event: Any) -> None:
        for handler in self._handlers.get(type(event), []):
            try:
                await handler(event)
            except Exception:
                logger.exception(
                    "Metric handler %s failed for event %s — continuing",
                    handler.__name__,
                    type(event).__name__,
                )

# Module-level singleton — no dependency injection needed
event_bus = EventBus()
```

**Key properties:**

- Synchronous iteration over handlers; `await` each handler in sequence
- Handler exceptions are caught and logged; they never propagate to the caller
- No external dependencies (no Redis, no Celery); in-process only
- `event_bus` is the single import needed by emission points

### App Startup Registration

```python
# agentops/main.py (FastAPI app startup)
from agentops.metrics.bus import event_bus
from agentops.metrics.handlers import (
    prometheus_handler,
    langsmith_feedback_handler,
    db_cache_handler,
)
from agentops.events import (
    JobStarted, JobCompleted, JobFailed,
    AgentInvoked, AgentCompleted, AgentFailed, AgentTokensConsumed,
    CostBudgetExceeded, HumanInterruptTriggered, HumanInterruptAnswered,
    HumanInterruptTimedOut, UserFeedbackSubmitted,
    IndexBuildCompleted, IndexBuildFailed,
)

@app.on_event("startup")
async def register_metric_handlers() -> None:
    # Prometheus
    event_bus.subscribe(JobStarted,              prometheus_handler.on_job_started)
    event_bus.subscribe(JobCompleted,            prometheus_handler.on_job_completed)
    event_bus.subscribe(JobFailed,               prometheus_handler.on_job_failed)
    event_bus.subscribe(AgentInvoked,            prometheus_handler.on_agent_invoked)
    event_bus.subscribe(AgentCompleted,          prometheus_handler.on_agent_completed)
    event_bus.subscribe(AgentFailed,             prometheus_handler.on_agent_failed)
    event_bus.subscribe(AgentTokensConsumed,     prometheus_handler.on_tokens_consumed)
    event_bus.subscribe(HumanInterruptAnswered,  prometheus_handler.on_interrupt_answered)
    event_bus.subscribe(IndexBuildCompleted,     prometheus_handler.on_index_build_completed)

    # LangSmith
    event_bus.subscribe(UserFeedbackSubmitted,   langsmith_feedback_handler.on_user_feedback)

    # DB cache
    event_bus.subscribe(JobCompleted,            db_cache_handler.on_job_completed)
    event_bus.subscribe(JobFailed,               db_cache_handler.on_job_failed)
```

---

## 6. Event Emission Points

Only specific components may emit domain events. The list below is exhaustive.

### ARQ Worker (`run_triage`)

The primary emission point for all job and agent lifecycle events. The worker drives the
`astream_events()` loop and maps LangGraph callback events to domain events:

```python
async def run_triage(ctx: dict, job_id: str) -> None:
    await event_bus.publish(JobStarted(
        job_id=job_id,
        repository=initial_state["repository"],
        issue_url=initial_state["issue_url"],
    ))

    agent_start_times: dict[str, float] = {}

    async for event in graph.astream_events(initial_state, config=config, version="v2"):
        name = event.get("name", "")
        kind = event.get("event", "")

        if kind == "on_chain_start" and name in AGENT_NAMES:
            agent_start_times[name] = time.monotonic()
            await event_bus.publish(AgentInvoked(job_id=job_id, agent_name=name))

        elif kind == "on_chain_end" and name in AGENT_NAMES:
            duration_ms = (time.monotonic() - agent_start_times.pop(name, 0)) * 1000
            output = event.get("data", {}).get("output", {})
            confidence = output.get("confidence", 1.0)
            await event_bus.publish(AgentCompleted(
                job_id=job_id,
                agent_name=name,
                duration_ms=duration_ms,
                confidence=confidence,
            ))

        elif kind == "on_chain_error" and name in AGENT_NAMES:
            error = str(event.get("data", {}).get("error", "unknown"))
            await event_bus.publish(AgentFailed(
                job_id=job_id, agent_name=name, error=error,
            ))

        elif kind == "on_chat_model_end":
            cost, input_tok, output_tok, model = extract_token_event(event)
            await event_bus.publish(AgentTokensConsumed(
                job_id=job_id,
                agent_name=event.get("metadata", {}).get("langgraph_node", "unknown"),
                model=model,
                input_tokens=input_tok,
                output_tokens=output_tok,
                cost_usd=cost,
            ))

    # Post-graph: emit job outcome
    final_state = await graph.aget_state(config)
    if final_state.values.get("error"):
        await event_bus.publish(JobFailed(job_id=job_id, error=final_state.values["error"]))
    else:
        await event_bus.publish(JobCompleted(
            job_id=job_id,
            duration_ms=elapsed_ms,
            final_confidence=final_state.values.get("final_confidence", 0.0),
            severity=final_state.values.get("severity", "UNKNOWN"),
        ))
```

### Human Interrupt Events

| Emission point                             | Event                     |
|--------------------------------------------|---------------------------|
| Worker: `on_interrupt` from `astream_events` | `HumanInterruptTriggered` |
| Worker: `expire_human_input` ARQ job fires   | `HumanInterruptTimedOut`  |
| `POST /jobs/{id}/answer` route handler       | `HumanInterruptAnswered`  |

```python
# In POST /jobs/{id}/answer handler
wait_seconds = (datetime.utcnow() - job.interrupted_at).total_seconds()
await event_bus.publish(HumanInterruptAnswered(
    job_id=job_id,
    wait_seconds=wait_seconds,
))
```

### Feedback Endpoint

```python
# POST /jobs/{id}/feedback
await event_bus.publish(UserFeedbackSubmitted(
    job_id=job_id,
    langsmith_run_id=job.langsmith_run_id,
    positive=body.positive,
    comment=body.comment,
))
```

### Indexer ARQ Job

```python
# In index_repository ARQ job
await event_bus.publish(IndexBuildCompleted(
    repo_url=repo_url,
    duration_ms=elapsed_ms,
    document_count=doc_count,
))
# or on failure:
await event_bus.publish(IndexBuildFailed(repo_url=repo_url, error=str(exc)))
```

### NOT Emission Points

The following layers must **never** call `event_bus.publish()` or any metric function:

- LangGraph nodes (supervisor, investigator, codebase_search, web_search, critic, writer, human_input)
- LCEL chains inside LangServe agents
- LangServe agent entrypoints
- FastAPI route handlers (except answer and feedback endpoints listed above)

---

## 7. `PrometheusHandler`

All Prometheus metric definitions live in a single class. No metric is defined anywhere else.

```python
# agentops/metrics/handlers/prometheus_handler.py
from prometheus_client import Counter, Histogram, Gauge
from agentops.events import (
    JobStarted, JobCompleted, JobFailed,
    AgentInvoked, AgentCompleted, AgentFailed, AgentTokensConsumed,
    HumanInterruptAnswered, IndexBuildCompleted,
)

# --- Metric definitions ---

job_duration_seconds = Histogram(
    "job_duration_seconds",
    "End-to-end job duration",
    buckets=[10, 30, 60, 120, 300, 600],
)
job_total = Counter(
    "job_total",
    "Total jobs processed",
    ["status"],              # "completed" | "failed"
)
jobs_active = Gauge(
    "jobs_active",
    "Number of jobs currently running",
)
agent_calls_total = Counter(
    "agent_calls_total",
    "Total agent invocations",
    ["agent"],
)
agent_duration_seconds = Histogram(
    "agent_duration_seconds",
    "Per-agent execution time",
    ["agent"],
    buckets=[0.5, 1, 2, 5, 10, 30, 60],
)
agent_errors_total = Counter(
    "agent_errors_total",
    "Total agent errors",
    ["agent"],
)
token_usage_total = Counter(
    "token_usage_total",
    "Total tokens consumed",
    ["agent", "model", "token_type"],   # token_type: "input" | "output"
)
cost_usd_total = Counter(
    "cost_usd_total",
    "Total LLM cost in USD",
    ["agent", "model"],
)
human_wait_seconds = Histogram(
    "human_wait_seconds",
    "Time between human interrupt and answer",
    buckets=[10, 30, 60, 120, 300, 600, 1800],
)
index_build_duration_seconds = Histogram(
    "index_build_duration_seconds",
    "Codebase index build time",
    buckets=[5, 15, 30, 60, 120, 300],
)

# --- Handlers ---

async def on_job_started(event: JobStarted) -> None:
    jobs_active.inc()

async def on_job_completed(event: JobCompleted) -> None:
    jobs_active.dec()
    job_total.labels(status="completed").inc()
    job_duration_seconds.observe(event.duration_ms / 1000)

async def on_job_failed(event: JobFailed) -> None:
    jobs_active.dec()
    job_total.labels(status="failed").inc()

async def on_agent_invoked(event: AgentInvoked) -> None:
    agent_calls_total.labels(agent=event.agent_name).inc()

async def on_agent_completed(event: AgentCompleted) -> None:
    agent_duration_seconds.labels(agent=event.agent_name).observe(event.duration_ms / 1000)

async def on_agent_failed(event: AgentFailed) -> None:
    agent_errors_total.labels(agent=event.agent_name).inc()

async def on_tokens_consumed(event: AgentTokensConsumed) -> None:
    token_usage_total.labels(
        agent=event.agent_name, model=event.model, token_type="input"
    ).inc(event.input_tokens)
    token_usage_total.labels(
        agent=event.agent_name, model=event.model, token_type="output"
    ).inc(event.output_tokens)
    cost_usd_total.labels(agent=event.agent_name, model=event.model).inc(event.cost_usd)

async def on_interrupt_answered(event: HumanInterruptAnswered) -> None:
    human_wait_seconds.observe(event.wait_seconds)

async def on_index_build_completed(event: IndexBuildCompleted) -> None:
    index_build_duration_seconds.observe(event.duration_ms / 1000)
```

---

## 8. `LangSmithFeedbackHandler`

Subscribes to `UserFeedbackSubmitted`. All LangSmith SDK calls are here. Zero business logic.

```python
# agentops/metrics/handlers/langsmith_feedback_handler.py
import asyncio
import uuid
from langsmith import Client
from agentops.events import UserFeedbackSubmitted
from agentops.langsmith_client import langsmith_client
from agentops.config import settings

async def on_user_feedback(event: UserFeedbackSubmitted) -> None:
    run_id = uuid.UUID(event.langsmith_run_id)

    await asyncio.to_thread(
        langsmith_client.create_feedback,
        run_id=run_id,
        key="user_rating",
        score=1.0 if event.positive else -1.0,
        comment=event.comment,
    )

    if not event.positive:
        await asyncio.to_thread(
            langsmith_client.create_feedback,
            run_id=run_id,
            key="needs_review",
            score=0,
            comment="Negative user rating — added to review queue",
        )

        # Also add to annotation queue if confidence was low (check job state from DB)
        # Note: confidence check is done in the post-job hook (PRD-005-1 §7)
        # Here we only handle the feedback-triggered case
        await asyncio.to_thread(
            langsmith_client.add_runs_to_annotation_queue,
            queue_id=settings.langsmith_review_queue_id,
            run_ids=[run_id],
        )
```

**Imports:** `langsmith.Client`, `asyncio`, `uuid`. Nothing from business logic modules.

---

## 9. `DbCacheHandler`

Subscribes to `JobCompleted` and `JobFailed`. Triggers the LangSmith trace fetch and DB write.

```python
# agentops/metrics/handlers/db_cache_handler.py
from agentops.events import JobCompleted, JobFailed
from agentops.langsmith_client import langsmith_client
from agentops.db import async_session_factory
from agentops.observability.trace_cache import fetch_and_cache_trace_summary

async def on_job_completed(event: JobCompleted) -> None:
    async with async_session_factory() as db:
        # job record must already have langsmith_run_id written by worker
        from agentops.models import Job
        job = await db.get(Job, event.job_id)
        if job and job.langsmith_run_id:
            await fetch_and_cache_trace_summary(
                job_id=event.job_id,
                langsmith_run_id=job.langsmith_run_id,
                db=db,
                langsmith_client=langsmith_client,
            )

async def on_job_failed(event: JobFailed) -> None:
    async with async_session_factory() as db:
        # Write stub row so /jobs/{id}/summary returns a consistent response
        from agentops.models import JobTraceSummaryRow
        await db.merge(JobTraceSummaryRow(
            job_id=event.job_id,
            status="failed",
            total_tokens=0,
            total_cost_usd=0,
            duration_seconds=0,
            slowest_agent="—",
            slowest_agent_seconds=0,
            nodes_executed=0,
            agent_stats=[],
        ))
        await db.commit()
```

---

## 10. Prometheus `/metrics` Endpoint

```python
# agentops/main.py
import prometheus_client
from starlette.routing import Mount

# Mount at /metrics — internal network only (see docker-compose note below)
app.mount("/metrics", prometheus_client.make_asgi_app())
```

**Network access:** `/metrics` is not exposed through the public nginx reverse proxy. In
docker-compose, the API service exposes port `8001` (metrics) on `127.0.0.1` only, accessible
to Prometheus scraper on the internal `monitoring` network.

```yaml
# docker-compose.yml (relevant excerpt)
services:
  api:
    ports:
      - "8000:8000"      # public — proxied through nginx
      - "127.0.0.1:8001:8001"  # metrics — internal only
  prometheus:
    networks:
      - monitoring
    extra_hosts:
      - "host.docker.internal:host-gateway"
```

---

## 11. FastAPI Metrics Middleware

HTTP-level metrics (request count, latency) are recorded in ASGI middleware, **not** in route
handlers. Route handlers are metric-free.

```python
# agentops/middleware/metrics.py
import time
import re
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from prometheus_client import Counter, Histogram

http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status_code"],
)
http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency",
    ["method", "path"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

# Normalize dynamic path segments to avoid high-cardinality label explosion
_PATH_PATTERNS = [
    (re.compile(r"/jobs/[^/]+"), "/jobs/{job_id}"),
    (re.compile(r"/repos/[^/]+"), "/repos/{repo_id}"),
]

def normalize_path(path: str) -> str:
    for pattern, replacement in _PATH_PATTERNS:
        path = pattern.sub(replacement, path)
    return path

class PrometheusMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start
        path = normalize_path(request.url.path)
        http_requests_total.labels(
            method=request.method,
            path=path,
            status_code=str(response.status_code),
        ).inc()
        http_request_duration_seconds.labels(
            method=request.method,
            path=path,
        ).observe(duration)
        return response
```

Register in `main.py`:

```python
from agentops.middleware.metrics import PrometheusMiddleware
app.add_middleware(PrometheusMiddleware)
```

---

## 12. Strict Rules

| Layer | Allowed | Forbidden |
|---|---|---|
| LangGraph nodes | Business logic, state reads/writes, `httpx` calls | Prometheus, LangSmith SDK, DB metric writes, `event_bus` |
| LCEL chains | Prompts, LLM calls, output parsers | Any metric call |
| LangServe agents | Chain invocation, error handling | Any metric call |
| FastAPI route handlers | Request validation, DB reads, response assembly | Prometheus, LangSmith SDK |
| ASGI middleware | HTTP metric recording via Prometheus | Business logic |
| ARQ worker `run_triage` | Graph execution, Redis pub/sub, domain event emission | Direct Prometheus/LangSmith calls |
| ARQ worker other jobs | Job-specific logic, domain event emission | Direct Prometheus/LangSmith calls |
| EventBus handlers | Metric recording (Prometheus, LangSmith, DB) | Business logic, graph state reads |

**Enforcement:** In code review, any PR that adds a `prometheus_client` import or `langsmith`
import outside of `agentops/metrics/` is blocked. Enforce with a `ruff` rule or pre-commit
grep check:

```bash
# .pre-commit-config.yaml addition
- repo: local
  hooks:
    - id: no-metrics-in-business-logic
      name: No metrics imports outside agentops/metrics/
      language: pygrep
      entry: "from prometheus_client|import prometheus_client|from langsmith import Client"
      files: "^agentops/(?!metrics/).*\\.py$"
      exclude: "^agentops/langsmith_client\\.py$"
```

---

## 13. Testing Strategy

### Business Logic Tests (no metric mocking needed)

```python
# tests/nodes/test_supervisor.py
from unittest.mock import AsyncMock, patch
from agentops.metrics.bus import EventBus

async def test_supervisor_routes_to_writer_when_budget_exceeded():
    # Patch event_bus to a no-op — no metric mocking needed
    with patch("agentops.worker.event_bus", new=EventBus()):
        state = make_state(cost_budget_exceeded=True)
        result = supervisor_node(state)
        assert result["next_agent"] == "writer"
```

### Handler Tests (inject synthetic events)

```python
# tests/metrics/test_prometheus_handler.py
from agentops.metrics.handlers import prometheus_handler
from agentops.events import AgentCompleted
import prometheus_client

async def test_agent_duration_recorded():
    before = prometheus_client.REGISTRY.get_sample_value(
        "agent_duration_seconds_sum", {"agent": "investigator"}
    ) or 0.0
    await prometheus_handler.on_agent_completed(
        AgentCompleted(job_id="j1", agent_name="investigator", duration_ms=1500.0, confidence=0.8)
    )
    after = prometheus_client.REGISTRY.get_sample_value(
        "agent_duration_seconds_sum", {"agent": "investigator"}
    )
    assert after - before == pytest.approx(1.5)
```

### Integration Tests (real event bus)

```python
# tests/integration/test_event_pipeline.py
async def test_job_completion_records_all_metrics(real_event_bus):
    await real_event_bus.publish(JobCompleted(
        job_id="j1", duration_ms=30000.0, final_confidence=0.85, severity="HIGH"
    ))
    # Assert Prometheus counter incremented
    assert get_counter("job_total", {"status": "completed"}) == 1
    # Assert DB cache row written (via DbCacheHandler)
    ...
```

**Key invariant:** No test file ever needs to simultaneously mock both business logic and metrics.
Business logic tests are metric-free. Handler tests are business-logic-free.
