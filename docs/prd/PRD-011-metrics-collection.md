---
id: PRD-011
title: Metrics Collection — OTel + LangChain Callback
status: DRAFT
domain: observability
depends_on: [PRD-003, PRD-004, PRD-005]
key_decisions: [otel-metrics-api, langchain-callback-handler, minimal-event-bus, no-prometheus-client-in-app-code]
---

# PRD-011 — Metrics Collection: OTel + LangChain Callback

| Field        | Value                                                                            |
|--------------|----------------------------------------------------------------------------------|
| Document ID  | PRD-011                                                                          |
| Version      | 2.0                                                                              |
| Status       | DRAFT                                                                            |
| Date         | March 2026                                                                       |
| Parent Doc   | [PRD-001](PRD-001-master-overview.md)                                            |
| Related Docs | [PRD-003](PRD-003-langgraph-orchestration.md), [PRD-005-1](PRD-005-1-langsmith-api-spec.md) |

> **v2.0 revision note:** The original domain-event-bus-for-all-metrics design (v1.0) had two
> unsolved problems that made it unsuitable. This document replaces that design entirely.
> See §1 for the full analysis.

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
signature changes, the change is scattered across every file that calls it.

**The rule:** Business code must be provably correct without knowing anything about metrics.
Metric recording must be provably complete without knowing anything about business logic.

### Why the Original Event Bus Design (v1.0) Was Insufficient

The v1.0 domain-event-bus approach solved *business logic coupling* but left two problems
unsolved:

**Problem A — Handlers still import module-level prometheus_client globals.**
`prometheus_handler.py` defines `Counter("job_total", ...)` at module scope. Importing that
module registers counters in the Prometheus default registry. Any test that imports the module
(directly or transitively) triggers registration. Multiple test runs accumulate global counter
state. Tests that assert exact counter values become order-dependent. Mocking
`prometheus_client` in handler tests is still required.

**Problem B — The worker still has metric infrastructure in its hot path.**
Even though the worker emits events rather than calling Prometheus directly, it must call
`await event_bus.publish(AgentInvoked(...))` and `await event_bus.publish(AgentTokensConsumed(...))`
inside the `astream_events()` loop — for roughly 20 events per job run. This is still metric
infrastructure code inside the business execution path.

### Rejected Patterns (and Why)

| Pattern | Why it fails |
|---------|-------------|
| `xxMetrics` wrapper class | Still imports `prometheus_client`; test must mock the class; module-level counter registration problem persists |
| Base class inheritance | Code duplication across handlers; same module-level registration coupling problem |
| Lazy counter creation | Adds complexity; still requires mocking in tests that happen to trigger the lazy path |

---

## 2. Scope

This PRD covers all metric recording that requires explicit code:

| Metric category                | Sink              | Mechanism                                      |
|--------------------------------|-------------------|------------------------------------------------|
| Prometheus infrastructure      | `/metrics` endpoint | OTel Metrics API → PrometheusMetricReader    |
| LangSmith custom feedback      | LangSmith API     | `client.create_feedback()`, annotation queue   |
| In-app job statistics          | PostgreSQL        | `job_trace_summaries` table (see PRD-005-1 §4) |

**Not in scope:**

- LangSmith auto-instrumentation (zero-code via env vars; covered in PRD-005 §Integration Setup)
- Structured application logging (use Python `logging` module directly)
- Distributed tracing beyond LangSmith (out of v1 scope)

---

## 3. Architecture

### The Two-Pronged Solution

```text
┌────────────────────────────────────────────────────────────────────────┐
│  LangGraph nodes · LCEL chains · LangServe agents                       │
│  Zero metric calls. Zero event_bus calls. Zero OTel imports.            │
└────────────────────────────────────────────────────────────────────────┘

ARQ Worker startup:
  config["callbacks"] = [AgentOpsMetricsCallback()]
                              │
                              │  LangGraph framework fires these automatically
                              │  for in-process node function execution only.
                              │  LLM calls happen inside LangServe (over HTTP)
                              │  and do NOT propagate callbacks back to the worker.
                              ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │  AgentOpsMetricsCallback (BaseCallbackHandler)                    │
  │  agentops/metrics/callback.py                                     │
  │                                                                   │
  │  on_chain_start  → agent_calls_total.add(1)          ✓ captured  │
  │  on_chain_end    → agent_duration_seconds.record(elapsed) ✓      │
  │  on_chain_error  → agent_errors_total.add(1)         ✓ captured  │
  │  on_llm_end      → token_usage_total / cost_usd_total            │
  │                    ✗ NOT fired — LLM runs inside LangServe        │
  │                                                                   │
  │  Records via OTel Metrics API — not prometheus_client            │
  └──────────────────────────────────────────────────────────────────┘

  Token/cost coverage gap:
  LangServe agents execute LLM calls in separate processes over HTTP.
  on_llm_end never fires in the worker. Two options to close the gap:

  Option A (recommended): Instrument each LangServe LCEL chain entrypoint
  with a thin OTel wrapper that records token_usage_total and cost_usd_total
  directly using the same agentops/metrics/setup.py MeterProvider setup.

  Option B (post-job only): Derive total tokens + cost from LangSmith traces
  via fetch_and_cache_trace_summary() (PRD-005-1 §3). This gives accurate
  per-job totals after completion but no real-time in-flight counters.

  v1 uses Option B (LangSmith post-job data already captured). Option A is
  a v1.1 concern requiring OTel setup in each LangServe service.

Explicit emission points (4 total — not in business logic):
  ┌────────────────────────────────────────────────────────────────┐
  │  Worker post-graph  → meter.add() / meter.record() (2 lines)  │
  │  POST /answer       → meter.record() (1 line)                 │
  │  POST /feedback     → event_bus.publish(UserFeedbackSubmitted) │
  │  Indexer job        → meter.add() / meter.record() (2 lines)  │
  └────────────────────────────────────────────────────────────────┘
                              │ (only feedback goes through bus)
                              ▼
  ┌──────────────────────────────────────────────────────────────┐
  │  LangSmithFeedbackHandler                                     │
  │  → create_feedback(), add_runs_to_annotation_queue()         │
  └──────────────────────────────────────────────────────────────┘

OTel MeterProvider (configured once per process at startup):
  ┌──────────────────────────────────────────────────────────────┐
  │  API process (main.py):  configure_api_metrics()             │
  │    PrometheusMetricReader → ASGI /metrics on :8001           │
  │                                                               │
  │  ARQ worker:  configure_worker_metrics(port=8002)            │
  │    PrometheusMetricReader → HTTP server thread on :8002      │
  │                                                               │
  │  Tests (conftest.py, one line):                               │
  │    metrics.set_meter_provider(NoOpMeterProvider())            │
  │    → all counter/histogram calls silently no-op              │
  │    → zero mocking, zero per-test setup                       │
  └──────────────────────────────────────────────────────────────┘
```

### Why OTel Replaces prometheus_client

The OpenTelemetry Metrics API (`opentelemetry.metrics`) is a vendor-neutral interface.
Application code calls the API; Prometheus is just one *exporter*, wired up once at startup.

- **No module-level registration.** `meter.create_counter(...)` does not register anything in
  the Prometheus default registry. It registers in the OTel SDK, which is configurable.
- **Test isolation via NoOpMeterProvider.** One line in `conftest.py` replaces all counters
  and histograms with silent no-ops. No mock patching. No registry accumulation.
- **Same `/metrics` output.** The Prometheus exporter produces identical output to
  `prometheus_client` — Grafana dashboards and alert rules are unaffected.

---

## 4. LangChain Callback Handler

```python
# agentops/metrics/callback.py
import time
import uuid
from typing import Any, Union
from langchain_core.callbacks import BaseCallbackHandler
from opentelemetry import metrics

MODEL_PRICING: dict[str, dict[str, float]] = {
    "gpt-4o":      {"input": 2.50 / 1_000_000, "output": 10.00 / 1_000_000},
    "gpt-4o-mini": {"input": 0.15 / 1_000_000, "output":  0.60 / 1_000_000},
}

AGENT_NAMES = {"investigator", "codebase_search", "web_search", "critic", "writer", "supervisor"}


class AgentOpsMetricsCallback(BaseCallbackHandler):
    """Records all agent/token/duration metrics via OTel Metrics API.

    Injected into the ARQ worker via config["callbacks"]. Business logic
    (nodes, chains) has zero metric calls. Worker has zero explicit metric
    calls inside the astream_events() loop.
    """

    def __init__(self, meter_provider: metrics.MeterProvider) -> None:
        meter = meter_provider.get_meter("agentops")
        self._agent_calls    = meter.create_counter(
            "agent_calls_total", description="Total agent invocations",
        )
        self._agent_duration = meter.create_histogram(
            "agent_duration_seconds", description="Per-agent execution time",
            unit="s",
        )
        self._agent_errors   = meter.create_counter(
            "agent_errors_total", description="Total agent errors",
        )
        self._token_usage    = meter.create_counter(
            "token_usage_total", description="Total tokens consumed",
        )
        self._cost_usd       = meter.create_counter(
            "cost_usd_total", description="Total LLM cost in USD",
        )
        # Track start times keyed by run_id (UUID → float)
        self._start_times: dict[str, float] = {}

    def _agent_name(self, serialized: dict, kwargs: dict) -> str | None:
        """Extract the LangGraph node name if this is a tracked agent."""
        name = (
            kwargs.get("metadata", {}).get("langgraph_node")
            or serialized.get("name", "")
        )
        return name if name in AGENT_NAMES else None

    def on_chain_start(
        self,
        serialized: dict[str, Any],
        inputs: dict[str, Any],
        *,
        run_id: uuid.UUID,
        **kwargs: Any,
    ) -> None:
        agent = self._agent_name(serialized, kwargs)
        if agent:
            self._start_times[str(run_id)] = time.perf_counter()
            self._agent_calls.add(1, {"agent": agent})

    def on_chain_end(
        self,
        outputs: dict[str, Any],
        *,
        run_id: uuid.UUID,
        **kwargs: Any,
    ) -> None:
        key = str(run_id)
        if key in self._start_times:
            elapsed = time.perf_counter() - self._start_times.pop(key)
            agent = kwargs.get("metadata", {}).get("langgraph_node", "unknown")
            self._agent_duration.record(elapsed, {"agent": agent})

    def on_chain_error(
        self,
        error: Union[Exception, KeyboardInterrupt],
        *,
        run_id: uuid.UUID,
        **kwargs: Any,
    ) -> None:
        self._start_times.pop(str(run_id), None)
        agent = kwargs.get("metadata", {}).get("langgraph_node", "unknown")
        if agent in AGENT_NAMES:
            self._agent_errors.add(1, {"agent": agent})

    def on_llm_end(self, response: Any, *, run_id: uuid.UUID, **kwargs: Any) -> None:
        usage = getattr(response, "usage_metadata", None) or {}
        model = kwargs.get("metadata", {}).get("ls_model_name", "gpt-4o-mini")
        agent = kwargs.get("metadata", {}).get("langgraph_node", "unknown")
        pricing = MODEL_PRICING.get(model, MODEL_PRICING["gpt-4o-mini"])

        input_tokens  = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        cost = input_tokens * pricing["input"] + output_tokens * pricing["output"]

        if input_tokens or output_tokens:
            self._token_usage.add(input_tokens,  {"agent": agent, "model": model, "token_type": "input"})
            self._token_usage.add(output_tokens, {"agent": agent, "model": model, "token_type": "output"})
            self._cost_usd.add(cost,             {"agent": agent, "model": model})
```

### Injection Point

```python
# agentops/worker.py — inside run_triage(), before astream_events
from agentops.metrics.callback import AgentOpsMetricsCallback

config = {
    "configurable": {"thread_id": job_id},
    "run_id": langsmith_run_id,
    "metadata": {...},
    "tags": [...],
    "callbacks": [AgentOpsMetricsCallback(metrics.get_meter_provider())],   # injected here; never in node code
}

async for event in graph.astream_events(initial_state, config=config, version="v2"):
    ...  # no metric calls here — callback handles everything
```

### Testing the Callback

```python
# tests/metrics/test_callback.py
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from agentops.metrics.callback import AgentOpsMetricsCallback
import uuid

def test_agent_duration_recorded():
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])

    cb = AgentOpsMetricsCallback(provider)
    run_id = uuid.uuid4()
    cb.on_chain_start(
        {"name": "investigator"}, {},
        run_id=run_id,
        metadata={"langgraph_node": "investigator"},
    )
    cb.on_chain_end({}, run_id=run_id, metadata={"langgraph_node": "investigator"})

    data = reader.get_metrics_data()
    metrics_by_name = {
        m.name: m
        for rm in data.resource_metrics
        for sm in rm.scope_metrics
        for m in sm.metrics
    }
    assert "agent_duration_seconds" in metrics_by_name
    # Exactly one data point recorded for "investigator"
    dp = metrics_by_name["agent_duration_seconds"].data.data_points[0]
    assert dp.attributes["agent"] == "investigator"
    assert dp.sum > 0
```

No mocking needed. The callback is tested by calling its methods directly.

---

## 5. OTel MeterProvider Setup

The API process and the ARQ worker are separate OS processes with separate memory spaces.
Each must expose its own `/metrics` endpoint — they cannot share a single
`prometheus_client` registry across process boundaries.

- **API process** (`main.py`): mounts `/metrics` as an ASGI sub-app on port 8001.
- **ARQ worker** (`worker.py`): starts a lightweight HTTP server thread on port 8002 at
  startup. Prometheus scrapes both ports.

```python
# agentops/metrics/setup.py
from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from prometheus_client import start_http_server  # only import in this file


def configure_api_metrics(port: int = 8001) -> None:
    """Configure OTel metrics for the FastAPI process.

    Starts a prometheus_client HTTP server thread on *port* (default 8001),
    separate from the uvicorn port (8000). This is symmetric with the worker
    approach and avoids mixing Prometheus scrape traffic with API traffic.
    """
    reader = PrometheusMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    metrics.set_meter_provider(provider)
    start_http_server(port)


def configure_worker_metrics(port: int = 8002) -> None:
    """Configure OTel metrics for the ARQ worker process.

    Starts a prometheus_client HTTP server thread on *port* so Prometheus can
    scrape worker metrics (job_total, job_duration_seconds, jobs_active,
    agent_calls_total, …) independently from the API process.
    """
    reader = PrometheusMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    metrics.set_meter_provider(provider)
    start_http_server(port)
```

```python
# agentops/main.py
from agentops.metrics.setup import configure_api_metrics

configure_api_metrics(port=8001)
# No app.mount("/metrics") needed — start_http_server() binds its own port.
```

```python
# agentops/worker.py  (ARQ startup hook)
from agentops.metrics.setup import configure_worker_metrics

async def startup(ctx: dict) -> None:
    configure_worker_metrics(port=8002)
    ...
```

### Test Isolation (one line in conftest.py)

```python
# tests/conftest.py
from opentelemetry import metrics
from opentelemetry.metrics import NoOpMeterProvider

# NoOpMeterProvider (API package) returns true no-op instruments —
# .add() and .record() calls silently succeed with zero state accumulation.
# MeterProvider() (SDK package) with no readers is NOT equivalent: it creates
# real SDK instruments that aggregate state in-process even without an exporter.
metrics.set_meter_provider(NoOpMeterProvider())
```

This single line applies to **all** test files — no per-test setup, no mock patching.
Tests that need to assert metric values use `InMemoryMetricReader` as shown in §4.

---

## 6. Minimal Event Bus (UserFeedbackSubmitted only)

The event bus is kept for exactly one use case: routing `UserFeedbackSubmitted` to
`LangSmithFeedbackHandler`. This is justified because the handler has real branching logic
(4 conditions: positive/negative rating, confidence threshold, annotation queue call), making
direct calls awkward in a route handler. For all other emission points, direct OTel calls
(1–3 lines each) are simpler and clearer.

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
                    "Handler %s failed for %s — continuing",
                    handler.__name__,
                    type(event).__name__,
                )

```

```python
# agentops/deps/events.py
from typing import Annotated
from fastapi import Depends, Request
from agentops.metrics.bus import EventBus

async def get_event_bus(request: Request) -> EventBus:
    """Return the EventBus from app.state."""
    return request.app.state.event_bus

EventBusDep = Annotated[EventBus, Depends(get_event_bus)]

# In lifespan (agentops/lifespan.py):
bus = EventBus()
bus.subscribe(UserFeedbackSubmitted, handle_user_feedback_handler)
app.state.event_bus = bus
```

### Domain Event (single event type uses the bus)

```python
# agentops/events.py
from dataclasses import dataclass

@dataclass
class UserFeedbackSubmitted:
    job_id: str
    langsmith_run_id: str
    positive: bool
    comment: str | None
```

> **Why no JobCompleted/JobFailed bus events?** The `DbCacheHandler` still needs to run after
> job completion, but it is called directly from the ARQ post-job hook rather than via the bus.
> The bus overhead (subscription, exception wrapping) is unnecessary for a single call site.
> Direct call: `await fetch_and_cache_trace_summary(job_id, langsmith_run_id, db, client)`.

---

## 7. Domain Event Catalog

All conceptual domain events are documented here. The implementation mechanism for each is
noted — only `UserFeedbackSubmitted` is a live Python dataclass routed through the event bus.
The others are handled automatically by `AgentOpsMetricsCallback` or via direct OTel calls.

| Event | Implementation | Handled by |
|---|---|---|
| `JobStarted` | Direct OTel | Worker pre-graph: `jobs_active.add(1)` |
| `JobCompleted` | Direct OTel | Worker post-graph: `job_total.add(1)`, `job_duration.record()` |
| `JobFailed` | Direct OTel | Worker post-graph: `job_total.add(1, {"status": "failed"})` |
| `AgentInvoked` | Callback | `on_chain_start` → `agent_calls_total.add(1)` |
| `AgentCompleted` | Callback | `on_chain_end` → `agent_duration_seconds.record()` |
| `AgentFailed` | Callback | `on_chain_error` → `agent_errors_total.add(1)` |
| `AgentTokensConsumed` | Callback | `on_llm_end` → `token_usage_total.add()`, `cost_usd_total.add()` |
| `CostBudgetExceeded` | State field | Worker reads `cost_budget_exceeded` from state (see PRD-005-1 §5) |
| `HumanInterruptTriggered` | Implicit | No metric recorded; logged only |
| `HumanInterruptAnswered` | Direct OTel | `POST /answer`: `human_wait_seconds.record()` |
| `HumanInterruptTimedOut` | Implicit | No metric recorded; logged only |
| `UserFeedbackSubmitted` | **Event bus** | `LangSmithFeedbackHandler`: `create_feedback()`, annotation queue |
| `IndexBuildCompleted` | Direct OTel | Indexer job: `index_build_duration_seconds.record()` |
| `IndexBuildFailed` | Direct OTel | Indexer job: `index_build_duration_seconds.record({"status": "failed"})` |

### Dataclass Definitions

Only `UserFeedbackSubmitted` requires a dataclass (it is passed through the event bus):

```python
# agentops/events.py
from dataclasses import dataclass

@dataclass
class UserFeedbackSubmitted:
    job_id: str
    langsmith_run_id: str
    positive: bool
    comment: str | None
```

All other events in the table above are implicit — the metric is recorded directly at the
point the event conceptually occurs, with no intermediate dataclass.

---

## 8. Explicit Metric Emission Points

Only 4 explicit emission points remain in the codebase. All others are handled automatically
by `AgentOpsMetricsCallback`.

### ARQ Worker — Post-Graph (job lifecycle metrics)

```python
# agentops/worker.py — instruments created in on_startup, accessed via ctx

async def on_startup(ctx: dict) -> None:
    """Initialize all worker-scoped resources into ctx."""
    settings = get_settings()
    ctx["redis"] = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    ctx["db_engine"] = create_async_engine(settings.database_url)
    ctx["langsmith"] = Client()
    configure_worker_metrics(port=8002)
    meter = otel_metrics.get_meter("agentops")
    ctx["job_total"]      = meter.create_counter("job_total", description="Total jobs processed")
    ctx["job_duration"]   = meter.create_histogram("job_duration_seconds", description="End-to-end job duration", unit="s")
    ctx["jobs_active"]    = meter.create_up_down_counter("jobs_active", description="Jobs currently running")
    ctx["index_duration"] = meter.create_histogram("index_build_duration_seconds", description="Codebase index build time", unit="s")

async def run_triage(ctx: dict, job_id: str) -> None:
    jobs_active: UpDownCounter = ctx["jobs_active"]
    job_total: Counter = ctx["job_total"]
    job_duration: Histogram = ctx["job_duration"]
    jobs_active.add(1)
    start = time.perf_counter()
    try:
        async for event in graph.astream_events(initial_state, config=config, version="v2"):
            pass  # callback handles all in-loop metrics

        final_state = await graph.aget_state(config)
        elapsed = time.perf_counter() - start

        if final_state.values.get("error"):
            job_total.add(1, {"status": "failed"})
            # post-job hook: add_to_review_queue_if_needed(), etc.
        else:
            job_total.add(1, {"status": "completed"})
            job_duration.record(elapsed)
            await fetch_and_cache_trace_summary(...)
            await add_to_review_queue_if_needed(...)
    finally:
        jobs_active.add(-1)
```

### POST /answer — Human Interrupt Answered

```python
# agentops/routes/jobs.py
from opentelemetry import metrics as otel_metrics

@router.post("/jobs/{job_id}/answer", status_code=204)
async def submit_answer(job_id: str, body: AnswerRequest, db: DbSessionDep) -> None:
    job = await db.get(Job, job_id)
    # ... business logic: resume graph, update DB ...
    wait_seconds = (datetime.utcnow() - job.interrupted_at).total_seconds()
    # OTel get_meter / create_histogram are idempotent — SDK returns cached instrument.
    otel_metrics.get_meter("agentops").create_histogram(
        "human_wait_seconds", description="Human interrupt wait time", unit="s",
    ).record(wait_seconds)
```

### POST /feedback — UserFeedbackSubmitted (bus event)

```python
# agentops/routes/jobs.py
from agentops.metrics.bus import event_bus
from agentops.events import UserFeedbackSubmitted

@router.post("/jobs/{job_id}/feedback", status_code=204)
async def submit_feedback(job_id: str, body: FeedbackRequest, db: AsyncSession = Depends(get_db)):
    job = await db.get(Job, job_id)
    if not job or not job.langsmith_run_id:
        raise HTTPException(404, "Job not found or not traced")
    await event_bus.publish(UserFeedbackSubmitted(
        job_id=job_id,
        langsmith_run_id=job.langsmith_run_id,
        positive=body.positive,
        comment=body.comment,
    ))
    # LangSmithFeedbackHandler does the SDK calls — route handler is metric-free
```

### Indexer ARQ Job

```python
# agentops/worker.py or agentops/indexer.py

async def index_repository(ctx: dict, repo_url: str) -> None:
    index_duration: Histogram = ctx["index_duration"]
    start = time.perf_counter()
    try:
        doc_count = await build_index(repo_url)
        index_duration.record(time.perf_counter() - start, {"status": "completed"})
    except Exception as exc:
        index_duration.record(time.perf_counter() - start, {"status": "failed"})
        raise
```

### NOT Emission Points

The following layers must **never** call `event_bus.publish()`, any OTel metric call, or any
`prometheus_client` call:

- LangGraph nodes (supervisor, investigator, codebase_search, web_search, critic, writer, human_input)
- LCEL chains inside LangServe agents
- LangServe agent entrypoints
- FastAPI route handlers (except the four explicit emission points above)

---

## 9. `LangSmithFeedbackHandler`

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
        await asyncio.to_thread(
            langsmith_client.add_runs_to_annotation_queue,
            queue_id=settings.langsmith_review_queue_id,
            run_ids=[run_id],
        )
```

**Imports:** `langsmith.Client`, `asyncio`, `uuid`. Nothing from business logic modules.
This is the **only** place in the codebase that imports `langsmith.Client` outside of
`agentops/langsmith_client.py`.

---

## 10. `DbCacheHandler`

Called directly from the ARQ post-job hook (not via event bus — see §6). Triggers the
LangSmith trace fetch and DB write.

```python
# agentops/observability/trace_cache.py
from agentops.langsmith_client import langsmith_client
from agentops.db import async_session_factory
from agentops.observability.trace_fetch import fetch_and_cache_trace_summary

async def handle_job_completed(job_id: str, langsmith_run_id: str) -> None:
    async with async_session_factory() as db:
        await fetch_and_cache_trace_summary(
            job_id=job_id,
            langsmith_run_id=langsmith_run_id,
            db=db,
            langsmith_client=langsmith_client,
        )

async def handle_job_failed(job_id: str) -> None:
    async with async_session_factory() as db:
        from agentops.models import JobTraceSummaryRow
        await db.merge(JobTraceSummaryRow(
            job_id=job_id,
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

See [PRD-005-1 §4](PRD-005-1-langsmith-api-spec.md#4-job-trace-summary--db-table--cache-strategy-gap-1-continued)
for `fetch_and_cache_trace_summary()` implementation and DB table schema.

---

## 11. Prometheus `/metrics` Endpoint

Two scrape targets — one per process:

| Process | Port | How served |
|---------|------|------------|
| API (`main.py`) | 8001 | `prometheus_client.start_http_server(8001)` thread (via `configure_api_metrics`) |
| ARQ worker | 8002 | `prometheus_client.start_http_server(8002)` thread (via `configure_worker_metrics`) |

**Network access:** Neither port is exposed through the public nginx reverse proxy. Both are
bound to `127.0.0.1` and accessible to the Prometheus scraper on the internal `monitoring`
network only.

```yaml
# docker-compose.yml (relevant excerpt)
services:
  api:
    ports:
      - "8000:8000"            # public — proxied through nginx
      - "127.0.0.1:8001:8001"  # API metrics — internal only
  worker:
    ports:
      - "127.0.0.1:8002:8002"  # worker metrics — internal only
  prometheus:
    networks:
      - monitoring
    extra_hosts:
      - "host.docker.internal:host-gateway"
```

```yaml
# prometheus.yml scrape config
scrape_configs:
  - job_name: agentops-api
    static_configs:
      - targets: ["host.docker.internal:8001"]
  - job_name: agentops-worker
    static_configs:
      - targets: ["host.docker.internal:8002"]
```

---

## 12. FastAPI Metrics Middleware

HTTP-level metrics (request count, latency) are recorded in ASGI middleware via the OTel
Metrics API — **not** `prometheus_client` directly, and **not** in route handlers.

```python
# agentops/middleware/metrics.py
import re
import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from opentelemetry import metrics

_meter = metrics.get_meter("agentops")
_http_requests  = _meter.create_counter(
    "http_requests_total", description="Total HTTP requests",
)
_http_duration  = _meter.create_histogram(
    "http_request_duration_seconds", description="HTTP request latency", unit="s",
)

_PATH_PATTERNS = [
    (re.compile(r"/jobs/[^/]+"), "/jobs/{job_id}"),
    (re.compile(r"/repos/[^/]+"), "/repos/{repo_id}"),
]

def normalize_path(path: str) -> str:
    for pattern, replacement in _PATH_PATTERNS:
        path = pattern.sub(replacement, path)
    return path

class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - start
        path = normalize_path(request.url.path)
        attrs = {"method": request.method, "path": path, "status_code": str(response.status_code)}
        _http_requests.add(1, attrs)
        _http_duration.record(elapsed, {"method": request.method, "path": path})
        return response
```

Register in `main.py`:

```python
from agentops.middleware.metrics import MetricsMiddleware
app.add_middleware(MetricsMiddleware)
```

---

## 13. Strict Rules

| Layer | Metric mechanism | Forbidden |
|---|---|---|
| LangGraph nodes | None — zero metric calls | Any metric call, `event_bus`, OTel |
| LCEL chains | None | Any metric call |
| LangServe agents | None | Any metric call |
| ARQ worker (in loop) | None — callback fires automatically | Explicit metric calls inside loop |
| ARQ worker (post-graph) | `meter.add()` / `meter.record()` directly | `prometheus_client` |
| LangChain callback | OTel Metrics API | `prometheus_client`, `event_bus` |
| `POST /feedback` handler | `event_bus.publish(UserFeedbackSubmitted)` | `prometheus_client`, `langsmith` |
| `POST /answer` handler | `meter.record()` (1 line) | `prometheus_client`, `event_bus` |
| `LangSmithFeedbackHandler` | LangSmith SDK calls | Business logic, OTel |
| ASGI middleware | OTel Metrics API | `prometheus_client` |
| `main.py` / `conftest.py` | `MeterProvider` configuration | Metric recording |

**Enforcement:** In code review, any PR that adds a `prometheus_client` import or `langsmith`
import outside of `agentops/metrics/` and `agentops/langsmith_client.py` is blocked.

```bash
# .pre-commit-config.yaml addition
- repo: local
  hooks:
    - id: no-metrics-in-business-logic
      name: No prometheus_client imports outside agentops/metrics/ or main.py
      language: pygrep
      entry: "from prometheus_client|import prometheus_client"
      files: "^agentops/(?!metrics/|main\\.py).*\\.py$"
    - id: no-langsmith-in-business-logic
      name: No langsmith.Client imports outside designated modules
      language: pygrep
      entry: "from langsmith import Client|import langsmith"
      files: "^agentops/(?!metrics/|langsmith_client).*\\.py$"
```

---

## 14. Complete Metric Catalog

All metrics produced by this system, with their source:

| Metric name                    | Type      | Labels                              | Source                        |
|--------------------------------|-----------|-------------------------------------|-------------------------------|
| `agent_calls_total`            | Counter   | `agent`                             | `AgentOpsMetricsCallback`     |
| `agent_duration_seconds`       | Histogram | `agent`                             | `AgentOpsMetricsCallback`     |
| `agent_errors_total`           | Counter   | `agent`                             | `AgentOpsMetricsCallback`     |
| `token_usage_total`            | Counter   | `agent`, `model`, `token_type`      | LangServe-side instrumentation (v1.1); LangSmith post-job in v1 |
| `cost_usd_total`               | Counter   | `agent`, `model`                    | LangServe-side instrumentation (v1.1); LangSmith post-job in v1 |
| `job_total`                    | Counter   | `status`                            | Worker post-graph             |
| `job_duration_seconds`         | Histogram | —                                   | Worker post-graph             |
| `jobs_active`                  | UpDownCounter | —                               | Worker post-graph             |
| `human_wait_seconds`           | Histogram | —                                   | `POST /answer` handler        |
| `index_build_duration_seconds` | Histogram | `status`                            | Indexer ARQ job               |
| `http_requests_total`          | Counter   | `method`, `path`, `status_code`     | ASGI middleware               |
| `http_request_duration_seconds`| Histogram | `method`, `path`                    | ASGI middleware               |

---

## 15. Testing Strategy

### Node and Chain Tests (zero metric involvement)

```python
# tests/nodes/test_supervisor.py
# No event_bus, no OTel, no mocking needed.
# conftest.py already set NoOpMeterProvider — all OTel calls are safe no-ops.

async def test_supervisor_routes_to_writer_when_budget_exceeded():
    state = make_state(cost_budget_exceeded=True)
    result = supervisor_node(state)
    assert result["next_agent"] == "writer"
```

Not passing `AgentOpsMetricsCallback` in config → zero metric involvement.
`conftest.py` NoOpMeterProvider → any accidental OTel call silently succeeds.

### Callback Tests (InMemoryMetricReader, no mocking)

```python
# tests/metrics/test_callback.py
# See §4 for full example. Pattern:
# 1. Create InMemoryMetricReader + MeterProvider
# 2. Call callback methods directly (on_chain_start, on_chain_end, etc.)
# 3. Assert data points via reader.get_metrics_data()
```

No mocking. No patching. Pure unit test on the callback class.

### Worker Integration Tests (callback + InMemoryMetricReader)

```python
# tests/integration/test_worker_metrics.py
async def test_job_completion_increments_job_total():
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    otel_metrics.set_meter_provider(provider)

    # Run worker with real callback
    await run_triage(ctx=mock_ctx, job_id="j1")

    data = reader.get_metrics_data()
    job_total = find_metric(data, "job_total")
    assert sum(dp.value for dp in job_total.data.data_points
               if dp.attributes.get("status") == "completed") == 1
```

### Feedback Handler Tests (only mock needed in the system)

```python
# tests/metrics/test_langsmith_feedback_handler.py
from unittest.mock import AsyncMock, patch
from agentops.metrics.handlers.langsmith_feedback_handler import on_user_feedback
from agentops.events import UserFeedbackSubmitted

async def test_negative_feedback_calls_needs_review():
    event = UserFeedbackSubmitted(
        job_id="j1", langsmith_run_id=str(uuid.uuid4()),
        positive=False, comment="Wrong answer",
    )
    with patch("agentops.metrics.handlers.langsmith_feedback_handler.langsmith_client") as mock_client:
        await on_user_feedback(event)

    calls = mock_client.create_feedback.call_args_list
    keys = [c.kwargs["key"] for c in calls]
    assert "user_rating" in keys
    assert "needs_review" in keys
    mock_client.add_runs_to_annotation_queue.assert_called_once()
```

This is the **only** test in the system that needs to mock an external SDK.

### Global Rule

`conftest.py` sets `MeterProvider()` (empty, no exporters) at module level:
- All `create_counter` / `create_histogram` calls return no-op instruments
- All `.add()` and `.record()` calls silently succeed
- No Prometheus registry accumulation between test runs
- Tests that need to assert values opt in to `InMemoryMetricReader` explicitly
