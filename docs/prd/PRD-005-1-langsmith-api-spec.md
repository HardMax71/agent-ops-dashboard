---
id: PRD-005-1
title: LangSmith API & Integration Spec
status: DRAFT
domain: observability
depends_on: [PRD-005]
parent: PRD-005
---

# PRD-005-1 — LangSmith API & Integration Spec

| Field        | Value                                                                 |
|--------------|-----------------------------------------------------------------------|
| Document ID  | PRD-005-1                                                             |
| Version      | 1.0                                                                   |
| Status       | DRAFT                                                                 |
| Date         | March 2026                                                            |
| Parent Doc   | [PRD-005](PRD-005-langsmith-observability.md)                         |
| Related Docs | [PRD-003](PRD-003-langgraph-orchestration.md), [PRD-010](PRD-010-evaluation-framework.md) |

---

## 1. Purpose & Scope

This document fills the **7 implementation gaps** in PRD-005 that make it impossible to build
the observability layer from the parent doc alone. PRD-005 describes *what* the system does;
this document specifies *how* to implement each missing piece.

| Gap | Topic                                    | Section |
|-----|------------------------------------------|---------|
| 1   | LangSmith read API never shown           | §3      |
| 2   | Cost budget alert mechanism is wrong     | §5      |
| 3   | User thumbs up/down → LangSmith missing  | §6      |
| 4   | Manual Review Queue undefined            | §7      |
| 5   | Online Evaluators / Automation Rules     | §8      |
| 6   | Deep-link URL missing `org_id`/`project_id` | §9   |
| 7   | 7-day rolling quality score storage      | §10     |

**Out of scope:** LangSmith auto-instrumentation (zero-code via env vars — already covered in
PRD-005 §Integration Setup), eval dataset management (PRD-010), Prometheus metrics (PRD-011).

---

## 2. LangSmith Client Setup

### Client Instance

Use the synchronous `langsmith.Client` for all SDK calls. There is no `AsyncClient` — all
LangSmith SDK calls are synchronous and must be wrapped in `asyncio.to_thread()` to avoid
blocking the event loop.

```python
# agentops/langsmith_client.py
from langsmith import Client

# Reads LANGSMITH_API_KEY from environment automatically
langsmith_client = Client()
```

This module-level singleton is imported by:

- The ARQ worker (`run_triage`) — for post-job trace fetch and annotation queue
- FastAPI route handler (`POST /jobs/{id}/feedback`) — for feedback submission
- `scripts/run_evals.py` — for eval result retrieval

### Required Environment Variables

```bash
LANGSMITH_API_KEY=lsv2_...          # authenticates all SDK calls
LANGSMITH_PROJECT=agentops-prod     # project name for list_runs filter
LANGSMITH_ORG_ID=<uuid>             # for deep-link URL construction (see §9)
LANGSMITH_PROJECT_ID=<uuid>         # for deep-link URL construction (see §9)
LANGSMITH_REVIEW_QUEUE_ID=<uuid>    # annotation queue for low-confidence jobs (see §7)
```

---

## 3. Run Data Fetch Spec (Gap 1)

### SDK Method

After a job completes, the ARQ worker fetches trace data from LangSmith using `client.list_runs()`.

```python
import asyncio
from langsmith import Client

async def fetch_runs_for_job(job_id: str, langsmith_client: Client) -> list:
    """Fetch all LangSmith runs tagged with this job_id."""
    runs = await asyncio.to_thread(
        lambda: list(
            langsmith_client.list_runs(
                project_name=settings.langsmith_project,
                filter=f'and(eq(metadata_key, "job_id"), eq(metadata_value, "{job_id}"))',
                run_type="chain",
                select=[
                    "id",
                    "name",
                    "execution_time",
                    "total_tokens",
                    "prompt_tokens",
                    "completion_tokens",
                    "total_cost",
                    "status",
                    "parent_run_id",
                ],
            )
        )
    )
    return runs
```

### Run Hierarchy Navigation

- **Root run**: the entry with `parent_run_id == None` — represents the full job
- **Child runs**: all entries with a `parent_run_id` — represent individual agent/node executions

```python
def split_runs(runs: list) -> tuple[object, list]:
    root = next(r for r in runs if r.parent_run_id is None)
    children = [r for r in runs if r.parent_run_id is not None]
    return root, children
```

### `JobTraceSummary` Pydantic Model

```python
from pydantic import BaseModel
from typing import Any

class AgentStat(BaseModel):
    agent_name: str
    duration_seconds: float
    tokens: int
    cost_usd: float

class JobTraceSummary(BaseModel):
    job_id: str
    total_tokens: int
    total_cost_usd: float
    duration_seconds: float
    slowest_agent: str
    slowest_agent_seconds: float
    nodes_executed: int
    agent_stats: list[AgentStat]
```

---

## 4. Job Trace Summary — DB Table & Cache Strategy (Gap 1, continued)

### DB Table

```sql
CREATE TABLE job_trace_summaries (
    job_id               TEXT PRIMARY KEY REFERENCES jobs(id),
    fetched_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    total_tokens         INTEGER NOT NULL,
    total_cost_usd       NUMERIC(10, 6) NOT NULL,
    duration_seconds     NUMERIC(10, 3) NOT NULL,
    slowest_agent        TEXT NOT NULL,
    slowest_agent_seconds NUMERIC(10, 3) NOT NULL,
    nodes_executed       INTEGER NOT NULL,
    agent_stats          JSONB NOT NULL,   -- list of AgentStat objects
    status               TEXT NOT NULL DEFAULT 'completed'  -- 'completed' | 'failed'
);
```

### Fetch & Cache Trigger

1. Worker publishes `job.done` (or `job.failed`) to Redis pub/sub when the graph finishes
2. An ARQ post-job hook (or background FastAPI task listening on pub/sub) calls
   `fetch_and_cache_trace_summary(job_id, langsmith_run_id)`
3. The cache is written once; `GET /jobs/{id}/summary` reads from it, never calls LangSmith live

```python
async def fetch_and_cache_trace_summary(
    job_id: str,
    langsmith_run_id: str,
    db: AsyncSession,
    langsmith_client: Client,
) -> None:
    runs = await fetch_runs_for_job(job_id, langsmith_client)
    root, children = split_runs(runs)

    agent_stats = [
        AgentStat(
            agent_name=r.name,
            duration_seconds=r.execution_time or 0.0,
            tokens=(r.total_tokens or 0),
            cost_usd=float(r.total_cost or 0),
        )
        for r in children
    ]
    slowest = max(agent_stats, key=lambda s: s.duration_seconds, default=None)

    summary = JobTraceSummary(
        job_id=job_id,
        total_tokens=root.total_tokens or 0,
        total_cost_usd=float(root.total_cost or 0),
        duration_seconds=root.execution_time or 0.0,
        slowest_agent=slowest.agent_name if slowest else "—",
        slowest_agent_seconds=slowest.duration_seconds if slowest else 0.0,
        nodes_executed=len(children),
        agent_stats=agent_stats,
    )

    await db.merge(JobTraceSummaryRow(**summary.model_dump()))
    await db.commit()
```

---

## 5. In-Flight Cost Tracking (Gap 2)

### Why "tracked via LangSmith's API" is Wrong

LangSmith's API only exposes **completed** run data. There is no streaming cost endpoint for
in-flight jobs. Polling `client.list_runs()` during execution returns nothing until the run
finishes. The cost budget alert in PRD-005 §"Cost Budget Alerts" cannot be implemented that way.

### Correct Approach: `astream_events` Token Accumulation

The ARQ worker already iterates `graph.astream_events()`. Each `on_chat_model_end` event
contains `response_metadata.token_usage`. Apply the model pricing table to accumulate cost:

```python
# Model pricing table (USD per token)
MODEL_PRICING: dict[str, dict[str, float]] = {
    "gpt-4o": {
        "input":  2.50 / 1_000_000,
        "output": 10.00 / 1_000_000,
    },
    "gpt-4o-mini": {
        "input":  0.15 / 1_000_000,
        "output": 0.60 / 1_000_000,
    },
}

def extract_cost_from_event(event: dict) -> float:
    """Extract incremental cost from an on_chat_model_end event."""
    if event["event"] != "on_chat_model_end":
        return 0.0
    usage = event.get("data", {}).get("output", {}).get("usage_metadata", {})
    model = event.get("metadata", {}).get("ls_model_name", "gpt-4o-mini")
    pricing = MODEL_PRICING.get(model, MODEL_PRICING["gpt-4o-mini"])
    input_cost  = usage.get("input_tokens", 0)  * pricing["input"]
    output_cost = usage.get("output_tokens", 0) * pricing["output"]
    return input_cost + output_cost
```

### New `BugTriageState` Fields (note for PRD-003)

Three fields must be added to `BugTriageState` in PRD-003:

```python
running_cost_usd: float = Field(default=0.0)
    # Accumulated cost of all LLM calls so far in this job

max_cost_usd: float = Field(default=0.20)
    # Per-job cost limit; read from user Settings at job creation

cost_budget_exceeded: bool = Field(default=False)
    # Set True when running_cost_usd >= max_cost_usd; supervisor routes to writer
```

### Supervisor Budget Check

```python
# In supervisor node routing logic
if state["cost_budget_exceeded"]:
    return "writer"  # wrap up immediately
```

### Worker Loop Integration

```python
running_cost = 0.0
async for event in graph.astream_events(initial_state, config=config, version="v2"):
    cost_delta = extract_cost_from_event(event)
    if cost_delta > 0:
        running_cost += cost_delta
        if running_cost >= state["max_cost_usd"] and not state["cost_budget_exceeded"]:
            # Update state via checkpointer so supervisor sees it on next hop
            await graph.aupdate_state(
                config,
                {"running_cost_usd": running_cost, "cost_budget_exceeded": True},
            )
    # ... other event handling
```

---

## 6. User Feedback API (Gap 3)

### Endpoint

```
POST /jobs/{job_id}/feedback
```

**Request body:**

```python
class FeedbackRequest(BaseModel):
    positive: bool
    comment: str | None = None
```

### Handler

```python
@router.post("/jobs/{job_id}/feedback", status_code=204)
async def submit_feedback(
    job_id: str,
    body: FeedbackRequest,
    db: AsyncSession = Depends(get_db),
):
    job = await db.get(Job, job_id)
    if not job or not job.langsmith_run_id:
        raise HTTPException(404, "Job not found or not traced")

    await event_bus.publish(UserFeedbackSubmitted(
        job_id=job_id,
        langsmith_run_id=job.langsmith_run_id,
        positive=body.positive,
        comment=body.comment,
    ))
    return Response(status_code=204)
```

The actual LangSmith SDK calls are made in `LangSmithFeedbackHandler` (see PRD-011 §8),
keeping the route handler metric-free.

### LangSmith SDK Calls (in handler)

```python
import uuid
from langsmith import Client

async def handle_user_feedback(event: UserFeedbackSubmitted, client: Client) -> None:
    run_id = uuid.UUID(event.langsmith_run_id)

    await asyncio.to_thread(
        client.create_feedback,
        run_id=run_id,
        key="user_rating",
        score=1.0 if event.positive else -1.0,
        comment=event.comment,
    )

    if not event.positive:
        await asyncio.to_thread(
            client.create_feedback,
            run_id=run_id,
            key="needs_review",
            score=0,
            comment="Negative user rating — added to review queue",
        )
```

### Feedback Schema

| Key            | Score values  | Meaning                            |
|----------------|---------------|------------------------------------|
| `user_rating`  | `1.0` / `-1.0` | Thumbs up / thumbs down           |
| `needs_review` | `0`           | Flagged for manual inspection      |
| `quality_score`| `1.0`–`5.0`  | LLM-as-judge eval score (PRD-010)  |

These key names are referenced by LangSmith automation rule filters (see §8).

### UI Wiring

Thumbs up/down buttons in the Output Panel (PRD-002, Zone 3) call `POST /jobs/{id}/feedback`.
The button state is disabled after submission to prevent double-posting.

---

## 7. Manual Review Queue (Gap 4)

### LangSmith Feature

LangSmith's **Annotation Queue** feature allows runs to be queued for human review via the
LangSmith UI: `Project → Annotation Queues → Create Queue`.

The queue ID is stored as an env var so it can differ between environments:

```bash
LANGSMITH_REVIEW_QUEUE_ID=<uuid-from-langsmith-ui>
```

### Trigger Conditions

Evaluated in the ARQ post-job hook after graph execution completes:

| Condition                              | Trigger                                        |
|----------------------------------------|------------------------------------------------|
| `final_confidence < 0.5`               | Checked against `state["final_confidence"]`    |
| Any agent errored and was skipped      | Checked against `state["findings"]` error flag |
| User submitted negative feedback       | Handled in feedback endpoint (see §6)          |

### SDK Call

```python
async def add_to_review_queue_if_needed(
    state: BugTriageState,
    langsmith_run_id: str,
    client: Client,
) -> None:
    needs_review = (
        state.get("final_confidence", 1.0) < 0.5
        or any(f.get("error") for f in state.get("findings", []))
    )
    if not needs_review:
        return

    await asyncio.to_thread(
        client.add_runs_to_annotation_queue,
        queue_id=settings.langsmith_review_queue_id,
        run_ids=[uuid.UUID(langsmith_run_id)],
    )
```

This is called from the ARQ post-job hook after `fetch_and_cache_trace_summary()`.

---

## 8. Online Evaluators & Automation Rules (Gap 5)

Automation rules are **configured in the LangSmith UI**, not in Python code. The backend only
provides a webhook receiver endpoint that LangSmith calls when a rule fires.

### Rule Configuration Table

| Rule name          | LangSmith filter condition                           | Trigger threshold            | Action                  | LangSmith UI path                              |
|--------------------|------------------------------------------------------|------------------------------|-------------------------|------------------------------------------------|
| Quality degradation | `eq(feedback_key, "user_rating")`                   | 7-day rolling avg < 3.5      | Webhook → Slack         | Project → Automations → Create Rule            |
| High cost job       | `gt(total_cost, 0.20)`                              | Per-run (immediate)          | Webhook → Slack + email | Project → Automations → Create Rule            |
| Error spike         | `eq(error, true)`                                   | > 10% of runs in last hour   | Webhook → PagerDuty     | Project → Automations → Create Rule            |
| Slow job            | `gt(execution_time, 300)`                           | Per-run (immediate)          | Feedback tag: `"slow"`  | Project → Automations → Create Rule            |

*The 7-day rolling average for quality degradation uses LangSmith's native feedback aggregation,
not the `daily_eval_results` table (which serves the Analytics page — see §10).*

### Webhook Receiver

LangSmith POSTs to a configurable URL when a rule fires. The backend exposes:

```
POST /internal/langsmith-alert
```

This endpoint is **not** publicly documented and is protected by a shared secret in the
`X-LangSmith-Signature` header (configured in LangSmith UI under the rule's webhook settings).

```python
@router.post("/internal/langsmith-alert")
async def langsmith_alert_receiver(
    request: Request,
    x_langsmith_signature: str = Header(None),
):
    if x_langsmith_signature != settings.langsmith_webhook_secret:
        raise HTTPException(403, "Invalid signature")

    payload = await request.json()
    rule_name = payload.get("rule_name", "")

    if "quality" in rule_name:
        await notify_slack(f"Quality degradation alert: {payload}")
    elif "cost" in rule_name:
        await notify_slack(f"High cost job alert: {payload}")
    elif "error" in rule_name:
        await notify_pagerduty(payload)
    # "slow" rule tags the run directly in LangSmith; no webhook action needed

    return {"ok": True}
```

Add `LANGSMITH_WEBHOOK_SECRET` to the env var list.

---

## 9. Deep-Link URL Construction (Gap 6)

### Source of `org_id` and `project_id`

These values are **static per environment** and are read from env vars at startup:

- `LANGSMITH_ORG_ID` — found in LangSmith UI: `Settings → Organization → Organization ID`
- `LANGSMITH_PROJECT_ID` — found in the LangSmith project URL:
  `https://smith.langchain.com/o/{org_id}/projects/p/{project_id}`

### Helper Function

```python
# agentops/langsmith_client.py

def langsmith_trace_url(run_id: str) -> str:
    """Construct a deep-link URL to a specific LangSmith run."""
    return (
        f"https://smith.langchain.com/o/{settings.langsmith_org_id}"
        f"/projects/p/{settings.langsmith_project_id}/r/{run_id}"
    )
```

### Usage

Called once when the job completes. The URL is stored in the `jobs` table alongside
`langsmith_run_id`:

```sql
-- jobs table additions
langsmith_run_id  TEXT,
langsmith_url     TEXT   -- populated on job completion; NULL while running
```

```python
# In post-job hook
job.langsmith_url = langsmith_trace_url(str(langsmith_run_id))
await db.commit()
```

The "View in LangSmith" button in the UI reads `job.langsmith_url` from `GET /jobs/{id}`.

---

## 10. Daily Eval Score Storage (Gap 7)

### DB Table

```sql
CREATE TABLE daily_eval_results (
    date            DATE PRIMARY KEY,
    avg_score       NUMERIC(4, 2) NOT NULL,   -- LLM-as-judge score: 1.0–5.0
    sample_size     INTEGER NOT NULL,
    experiment_id   TEXT NOT NULL              -- LangSmith experiment ID for drill-down
);
```

### Writer

`scripts/run_evals.py` writes a row after each eval run:

```python
await db.execute(
    """
    INSERT INTO daily_eval_results (date, avg_score, sample_size, experiment_id)
    VALUES (:date, :avg_score, :sample_size, :experiment_id)
    ON CONFLICT (date) DO UPDATE
        SET avg_score = EXCLUDED.avg_score,
            sample_size = EXCLUDED.sample_size,
            experiment_id = EXCLUDED.experiment_id
    """,
    {
        "date": today,
        "avg_score": results.avg_score,
        "sample_size": results.sample_size,
        "experiment_id": results.experiment_id,
    },
)
```

### Rolling Average Query

```sql
SELECT ROUND(AVG(avg_score)::numeric, 2) AS rolling_avg_7d
FROM daily_eval_results
WHERE date >= NOW() - INTERVAL '7 days';
```

### API Exposure

`GET /metrics/quality` (Analytics page, v1.1) returns:

```json
{
  "rolling_avg_7d": 4.12,
  "latest_date": "2026-03-06",
  "sample_size": 47
}
```

Note: LangSmith's automation rule for quality degradation uses LangSmith's **own** internal
feedback aggregation. The `daily_eval_results` table is for the in-app Analytics page only.
