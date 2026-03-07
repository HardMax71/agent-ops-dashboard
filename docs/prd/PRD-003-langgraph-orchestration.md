---
id: PRD-003
title: LangGraph Orchestration & Human-in-the-Loop
status: DRAFT
domain: backend/orchestration
depends_on: [PRD-001, PRD-002]
key_decisions: [bug-triage-state-schema, interrupt-hitl, arq-worker-separation, redis-pubsub-fanout, postgres-checkpointing, human-input-timeout]
---

# PRD-003 — LangGraph Orchestration & Human-in-the-Loop

| Field        | Value                                             |
|--------------|---------------------------------------------------|
| Document ID  | PRD-003                                           |
| Version      | 1.0                                               |
| Status       | DRAFT                                             |
| Date         | March 2026                                        |
| Parent Doc   | [PRD-001](PRD-001-master-overview.md)             |
| Related Docs | [PRD-002](PRD-002-frontend-ux.md) (Frontend), [PRD-004](PRD-004-agent-layer.md) (LangChain/LangServe) |

---

## Overview

This document specifies the LangGraph orchestration layer of AgentOps Dashboard — the system's brain. It covers how the
supervisor coordinates worker agents, how shared state flows through the graph, how human interrupts are handled, and
how job state is persisted across sessions.

LangGraph is used here in its intended role: **low-level orchestration of long-running, stateful, multi-agent workflows
**. It is deliberately not used for simple linear chains (those live in LangChain/LCEL at the LangServe layer — see
[PRD-004](PRD-004-agent-layer.md)).

---

## LangGraph Fundamentals Used

| Concept           | Usage in This Product                                                                                                                     |
|-------------------|-------------------------------------------------------------------------------------------------------------------------------------------|
| `StateGraph`      | The main graph class; holds the shared `BugTriageState` across all nodes                                                                  |
| Nodes             | Each agent and decision point is a node: `supervisor`, `investigator`, `codebase_search`, `web_search`, `critic`, `human_input`, `writer` |
| Conditional edges | Supervisor's output determines which worker runs next via `add_conditional_edges`                                                         |
| `interrupt()`     | Pauses graph execution mid-node to await human input; resumes via `Command(resume=answer)`                                                |
| Checkpointer      | `SqliteSaver` (dev) / `PostgresSaver` (prod) — persists full graph state so jobs survive restarts                                         |
| Thread ID         | Each triage job maps to a LangGraph thread; jobs are fully isolated                                                                       |
| Streaming         | `graph.astream_events()` runs inside the ARQ worker; the API server is a pure Redis Pub/Sub consumer                                      |
| ARQ               | Async Redis Queue — distributed job execution, cross-worker `Job.abort()`, built-in status tracking (QUEUED / IN_PROGRESS / COMPLETE / FAILED) |
| Redis Pub/Sub     | Event fanout channel (`jobs:{id}:events`) — worker publishes events, SSE endpoint subscribes; supports multiple simultaneous subscribers  |

---

## Shared State Schema

The `BugTriageState` TypedDict is the central data structure. Every node reads from and writes to this state. It is
persisted at every checkpoint.

```python
from __future__ import annotations

from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages


class AgentFinding(TypedDict):
    agent_name: str
    summary: str
    details: str
    confidence: float  # 0.0 – 1.0
    relevant_files: list[str]


class HumanExchange(TypedDict):
    question: str
    context: str
    answer: str | None


class TriageReport(TypedDict):
    severity: str  # LOW / MEDIUM / HIGH / CRITICAL
    category: str
    root_cause: str
    relevant_files: list[str]
    similar_issues: list[str]
    confidence: float


class BugTriageState(TypedDict):
    issue_url: str
    issue_title: str
    issue_body: str
    repository: str

    current_node: str
    next_node: str | None
    supervisor_reasoning: str
    iterations: int
    max_iterations: int
    paused: bool

    findings: Annotated[list[AgentFinding], lambda a, b: a + b]

    human_exchanges: list[HumanExchange]
    awaiting_human: bool

    codebase_chunks: list[str]
    similar_past_issues: list[str]

    web_results: list[str]

    report: TriageReport | None
    github_comment_draft: str | None
    ticket_draft: dict | None

    job_id: str
    owner_id: str
    langsmith_run_id: str | None
    status: str
```

---

## Graph Structure

### Node List

| Node              | Type           | Description                                              |
|-------------------|----------------|----------------------------------------------------------|
| `START`           | Built-in       | Entry point                                              |
| `supervisor`      | LLM node       | Reads current state; decides next step                   |
| `investigator`    | Tool node      | Calls LangServe `/agents/investigator`                   |
| `codebase_search` | Tool node      | Calls LangServe `/agents/codebase-search`                |
| `web_search`      | Tool node      | Calls LangServe `/agents/web-search`                     |
| `critic`          | Tool node      | Calls LangServe `/agents/critic`                         |
| `human_input`     | Interrupt node | Fires `interrupt()`; blocks until user answers           |
| `writer`          | Tool node      | Calls LangServe `/agents/writer`; produces final outputs |
| `END`             | Built-in       | Exit point                                               |

### Graph Definition (Pseudocode)

```python
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver

builder = StateGraph(BugTriageState)

builder.add_node("supervisor", supervisor_node)
builder.add_node("investigator", investigator_node)
builder.add_node("codebase_search", codebase_search_node)
builder.add_node("web_search", web_search_node)
builder.add_node("critic", critic_node)
builder.add_node("human_input", human_input_node)
builder.add_node("writer", writer_node)

builder.add_edge(START, "supervisor")

builder.add_conditional_edges(
    "supervisor",
    route_from_supervisor,
    {
        "investigator": "investigator",
        "codebase_search": "codebase_search",
        "web_search": "web_search",
        "critic": "critic",
        "human_input": "human_input",
        "writer": "writer",
        "end": END,
    }
)

for node in ["investigator", "codebase_search", "web_search", "critic"]:
    builder.add_edge(node, "supervisor")

builder.add_edge("human_input", "supervisor")
builder.add_edge("writer", END)

checkpointer = SqliteSaver.from_conn_string("jobs.db")
graph = builder.compile(checkpointer=checkpointer)
```

### Routing Logic

```python
def route_from_supervisor(state: BugTriageState) -> str:
    """
    Supervisor LLM outputs structured JSON with 'next' field.
    This function extracts it and returns the node name.
    Guards: max_iterations check, required-findings check.
    """
    if state["iterations"] >= state["max_iterations"]:
        return "writer"  # force completion

    return state["next_node"]
```

---

## Supervisor Agent Design

The supervisor is the most critical node. It reads the full current state and decides:

1. Which worker to call next (or whether to ask the human, or to finalize)
2. Whether it has enough information to write the final report
3. Whether it needs to ask the user a clarifying question

### Supervisor System Prompt (Abbreviated)

```
You are the supervisor of a bug triage team. You coordinate specialized agents
to investigate a GitHub issue and produce a full triage report.

Your available agents:
- investigator: Reads and interprets the issue body. Always call this first.
- codebase_search: Searches the repository for relevant code. Call when you need
  to locate the root cause in source code.
- web_search: Searches the web for error messages or stack traces. Call when the
  issue contains cryptic errors or library bugs.
- critic: Reviews findings for correctness and gaps. Call when you have a
  hypothesis but want a second opinion before finalizing.
- writer: Produces the final report. Call only when you have sufficient evidence.

Human input rules:
- Ask the user a question if and only if:
  (a) Two or more equally plausible root causes exist and you cannot distinguish them
      without user knowledge, OR
  (b) Critical context is missing that no tool can retrieve (e.g. recent deploys,
      env-specific config)
- Maximum 2 questions per job. Do not ask about things tools can discover.
- Frame questions concisely. Provide 2–3 specific options when possible.

Output JSON with fields: next_node, reasoning, question (if asking human), confidence.
```

### Supervisor Output Schema

```python
class SupervisorDecision(BaseModel):
    next_node: Literal[
        "investigator", "codebase_search", "web_search",
        "critic", "human_input", "writer", "end"
    ]
    reasoning: str
    question: str | None  # only populated when next_node == "human_input"
    question_context: str | None
    confidence: float  # 0.0–1.0
```

---

## Worker Agent Node Specs

Each worker node follows the same pattern: call the corresponding LangServe endpoint, get back an `AgentFinding`, append
it to state, return updated state to supervisor.

```python
async def investigator_node(state: BugTriageState) -> dict:
    response = await httpx.post(
        "http://localhost:8001/agents/investigator/invoke",
        json={
            "input": {
                "issue_title": state["issue_title"],
                "issue_body": state["issue_body"],
                "prior_findings": state["findings"],
            }
        }
    )
    finding = AgentFinding(**response.json()["output"])
    return {
        "findings": [finding],  # reducer appends this
        "current_node": "investigator",
        "iterations": state["iterations"] + 1,
    }
```

| Node              | LangServe Endpoint        | Key Inputs from State                  | Key Outputs to State                             |
|-------------------|---------------------------|----------------------------------------|--------------------------------------------------|
| `investigator`    | `/agents/investigator`    | `issue_title`, `issue_body`            | `findings`                                       |
| `codebase_search` | `/agents/codebase-search` | `issue_body`, `findings`, `repository` | `findings`, `codebase_chunks`                    |
| `web_search`      | `/agents/web-search`      | `issue_body`, `findings`               | `findings`, `web_results`                        |
| `critic`          | `/agents/critic`          | `findings`, `codebase_chunks`          | `findings` (critique finding)                    |
| `writer`          | `/agents/writer`          | all findings, human exchanges          | `report`, `github_comment_draft`, `ticket_draft` |

---

## Human-in-the-Loop Implementation

### Triggering an Interrupt

When the supervisor routes to `human_input`, the node fires `interrupt()`:

```python
from langgraph.types import interrupt


def human_input_node(state: BugTriageState) -> dict:
    last_exchange = state["human_exchanges"][-1]

    answer = interrupt({
        "question": last_exchange["question"],
        "context": last_exchange["context"],
    })

    updated_exchanges = state["human_exchanges"].copy()
    updated_exchanges[-1]["answer"] = answer

    return {
        "human_exchanges": updated_exchanges,
        "awaiting_human": False,
    }
```

### Resuming from FastAPI

When the user submits an answer via `POST /jobs/{id}/answer`, the endpoint cancels the pending timeout ARQ job and
resumes the graph. Full implementation is in the [Interrupt Timeout Mechanism](#interrupt-timeout-mechanism) section.

### Interrupt Timeout Mechanism

`interrupt()` blocks the graph indefinitely — LangGraph has no built-in timeout. The 30-minute timeout is implemented
by enqueuing a deferred ARQ job (`expire_human_input`) with a 30-minute delay at the moment the interrupt fires. If the
user has not answered by then, the job resumes the graph with a best-effort signal via `graph.ainvoke(Command(resume=...))`.
If the user answers first, the answer endpoint cancels the deferred job via `Job.abort()` before resuming the graph.

```python
# worker.py

TIMEOUT_ANSWER = "[no answer provided — proceeding with best-effort]"
HUMAN_INPUT_TIMEOUT_SECONDS = 1800  # 30 minutes

async def expire_human_input(ctx: dict, job_id: str):
    """
    Scheduled ARQ job: fires 30 min after a human_input interrupt if unanswered.
    Resumes the graph with a best-effort signal so the supervisor can proceed.
    """
    redis: Redis = ctx["redis"]

    job = Job(job_id, redis)
    info = await job.info()
    if info is not None and info.status in (JobStatus.complete, JobStatus.not_found):
        return

    config = {"configurable": {"thread_id": job_id}}
    await graph.ainvoke(Command(resume=TIMEOUT_ANSWER), config=config)

    channel = f"jobs:{job_id}:events"
    await redis.publish(channel, json.dumps({
        "type": "human_input.timeout",
        "message": "No answer received after 30 minutes. Proceeding with best-effort.",
    }))
```

The timeout job is enqueued at the moment the ARQ worker detects the graph has paused at a `human_input` node (i.e.,
`astream_events` yields an `on_chain_end` event whose metadata indicates an interrupt):

```python
# worker.py — inside run_triage(), after the astream_events loop
async def run_triage(ctx: dict, job_id: str, initial_state: dict):
    redis: Redis = ctx["redis"]
    config = {"configurable": {"thread_id": job_id}}
    channel = f"jobs:{job_id}:events"

    async for event in graph.astream_events(initial_state, config=config, version="v2"):
        sse_event = transform_langgraph_event(event)
        if sse_event:
            await redis.publish(channel, json.dumps(sse_event))

        if _is_human_input_interrupt(event):
            await arq_queue.enqueue_job(
                "expire_human_input",
                job_id,
                _job_id=f"timeout:{job_id}",
                _defer_by=timedelta(seconds=HUMAN_INPUT_TIMEOUT_SECONDS),
            )

    await redis.publish(channel, json.dumps({"type": "job.done"}))
```

**Answer endpoint cancels the timeout** by aborting the scheduled ARQ job before resuming the graph:

```python
@app.post("/jobs/{job_id}/answer")
async def submit_answer(job_id: str, body: AnswerRequest, redis: Redis = Depends(get_redis)):
    config = {"configurable": {"thread_id": job_id}}

    timeout_job_id = f"timeout:{job_id}"
    timeout_job = Job(timeout_job_id, redis)
    await timeout_job.abort(timeout=2)  # no-op if already fired or not found

    await graph.ainvoke(Command(resume=body.answer), config=config)
```

### Question Constraints

| Rule                  | Value                                                         | Rationale                                               |
|-----------------------|---------------------------------------------------------------|---------------------------------------------------------|
| Max questions per job | 2                                                             | Prevent over-reliance on user; agents should be capable |
| Timeout (no answer)   | 30 minutes — enforced via deferred ARQ job (`expire_human_input`) | Prevents indefinite graph hang; graph resumes with best-effort signal |
| Question format       | Single question + 2–3 concrete options when applicable        | Reduces cognitive load                                  |
| Blocker scope         | Entire graph pauses, not just one agent                       | Ensures answer is incorporated before any further work  |

---

## Pause, Redirect, and Kill

### Pause

Triggered by user clicking "Pause" in the UI. Sends `POST /jobs/{id}/pause`.

Implementation: Sets a flag in the checkpointed state. The supervisor checks this flag at the start of each iteration
and fires `interrupt()` with a "manual pause" signal if set. User can resume by clicking "Resume".

### Redirect

Triggered after a pause. User can type a new instruction into a text field in the UI: e.g., "Focus only on the database
layer — ignore the auth middleware."

Implementation: Resumes the graph via `Command(resume={"type": "redirect", "instruction": "..."})`. The supervisor node
treats redirect instructions as high-priority context prepended to its system prompt for all subsequent steps.

### Kill

Sends `DELETE /jobs/{id}`. Immediately terminates the LangGraph thread via ARQ's cross-process abort mechanism.
Final state is checkpointed with `status: "killed"`. Any partial outputs already in state are preserved and shown in
the output panel.

**Architecture:** The API server never runs the graph. Jobs are enqueued to ARQ workers via Redis. `Job.abort()` sends
an abort signal through Redis; the worker process holding that job cancels its asyncio task — this works across any
number of workers and processes by design. No module-level `running_tasks` dict is needed.

```mermaid
flowchart LR
    subgraph API["FastAPI API server (REST + SSE)"]
        REST["REST endpoints\n/jobs/*"]
        SSE["SSE subscriber\njobs:{id}:events"]
    end

    subgraph WORKER["ARQ Worker(s)"]
        GRAPH["graph.ainvoke()"]
        PUB["publishes events\nto Redis channel"]
    end

    REDIS[("Redis\nARQ queue + Pub/Sub\n+ job status")]
    PG[("PostgreSQL\nLangGraph state")]

    API -->|"enqueue_job()"| WORKER
    WORKER -->|"Redis Pub/Sub events"| API
    API -->|"Job.abort()"| REDIS
    REDIS -->|"job queue"| WORKER
    WORKER -->|"PostgresSaver"| PG
```

**ARQ worker function** — runs on a worker process, not the API server:

```python
# worker.py
async def run_triage(ctx: dict, job_id: str, initial_state: dict):
    redis: Redis = ctx["redis"]
    config = {"configurable": {"thread_id": job_id}}
    channel = f"jobs:{job_id}:events"

    async for event in graph.astream_events(initial_state, config=config, version="v2"):
        sse_event = transform_langgraph_event(event)
        if sse_event:
            await redis.publish(channel, json.dumps(sse_event))

    await redis.publish(channel, json.dumps({"type": "job.done"}))


class WorkerSettings:
    functions = [run_triage]
    allow_abort_jobs = True   # enables Job.abort() cross-worker
    max_jobs = 10             # concurrent job cap per worker
    retry_jobs = False        # LangGraph jobs are not idempotent by default
```

**Kill endpoint** — no dict lookup, no task tracking:

```python
@app.delete("/jobs/{job_id}")
async def kill_job(job_id: str, redis: Redis = Depends(get_redis)):
    job = Job(job_id, redis)
    info = await job.info()
    if info is None:
        raise HTTPException(status_code=404, detail="Job not found")

    aborted = await job.abort(timeout=5)
    if not aborted:
        # run_triage exits normally when interrupt() suspends the graph, so ARQ
        # marks the job complete while the LangGraph thread sits checkpointed.
        # The pending timeout job is present exactly in that window.
        timeout_job = Job(f"timeout:{job_id}", redis)
        timeout_info = await timeout_job.info()
        if timeout_info is None or timeout_info.status in (JobStatus.complete, JobStatus.not_found):
            raise HTTPException(status_code=409, detail="Job could not be aborted (may already be complete)")
        await timeout_job.abort(timeout=2)  # no-op if already fired

    config = {"configurable": {"thread_id": job_id}}
    await graph.aupdate_state(config, {"status": "killed"})

    return {"job_id": job_id, "status": "killed"}
```

---

## Checkpointing and Persistence

### Why Checkpointing Matters

LangGraph's checkpointer saves the full `BugTriageState` to a database after every node execution. This means:

- Jobs survive server restarts
- Users can close the browser and come back to a running job
- The full execution history is available for debugging
- Paused jobs (waiting for human input) persist indefinitely until answered

### Configuration

| Environment | Checkpointer    | Connection             |
|-------------|-----------------|------------------------|
| Development | `SqliteSaver`   | `jobs.db` (local file) |
| Production  | `PostgresSaver` | `DATABASE_URL` env var |

### Thread IDs

Each job is identified by a UUID that maps 1:1 to a LangGraph thread ID. This UUID is generated at `POST /jobs` and is
the same ID used in SSE stream URLs, answer endpoints, and LangSmith trace grouping.

---

## Streaming to Frontend

**Separation of concerns:** `graph.astream_events()` runs inside the ARQ worker (see [Kill](#kill)). The worker publishes each
transformed event to a Redis Pub/Sub channel (`jobs:{job_id}:events`). The FastAPI SSE endpoint is a pure subscriber
— it never executes graph logic.

This means multiple browser tabs can subscribe to the same job stream independently (each gets a separate Redis
subscriber), and a client disconnect drops only that subscriber — the running job in the ARQ worker is unaffected.

**Disconnect handling:** Starlette's `StreamingResponse` runs the generator inside an anyio cancel scope. When the
client disconnects, Starlette cancels the scope, which raises `asyncio.CancelledError` at whichever `await` the
generator is blocked on inside `pubsub.listen()`. The `finally` block fires unconditionally and cleans up the
subscriber. No polling, no `request.is_disconnected()` checks, no extra tasks.

```python
@router.get("/{job_id}/stream")
async def stream_job(
    job_id: Annotated[str, Depends(get_job_and_verify_owner)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> StreamingResponse:
    channel = f"jobs:{job_id}:events"

    async def event_generator():
        pubsub = redis.pubsub()
        await pubsub.subscribe(channel)
        seq = 0
        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                yield f"id: {seq}\ndata: {message['data']}\n\n"
                seq += 1
                if json.loads(message["data"]).get("type") == "job.done":
                    break
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

The `transform_langgraph_event()` function (called in the ARQ worker) maps LangGraph's internal event types (e.g.,
`on_chat_model_stream`, `on_tool_start`, `on_chain_end`) to the frontend event schema in
[PRD-002](PRD-002-frontend-ux.md).

**FastAPI lifespan** — no graph tasks to drain on shutdown; only the Redis pool needs cleanup:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = await create_redis_pool(RedisSettings())
    app.state.arq_queue = ArqRedis(app.state.redis)
    yield
    await app.state.redis.close()

app = FastAPI(lifespan=lifespan)
```

---

## Error Handling

| Error Scenario                          | Behavior                                                                                                                      |
|-----------------------------------------|-------------------------------------------------------------------------------------------------------------------------------|
| Worker agent LangServe endpoint is down | Supervisor retries once after 5s; on second failure, marks agent as errored and routes to next available agent or human_input |
| LLM rate limit (429)                    | Exponential backoff with max 3 retries; after that, job status set to FAILED                                                  |
| Supervisor outputs invalid JSON         | Pydantic validation catches it; supervisor is re-invoked once with an error correction prompt                                 |
| `max_iterations` reached                | Graph routes directly to `writer` with whatever findings have been accumulated                                                |
| Unhandled exception in any node         | Job status set to FAILED; full traceback captured in LangSmith; error event sent to frontend                                  |
| Checkpointer DB unavailable             | Job continues in-memory; warning logged; user notified that job will not survive restart                                      |
