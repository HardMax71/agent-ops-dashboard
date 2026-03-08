---
id: PRD-003-1
title: SSE Event Pipeline & ARQ Worker Specification
status: DRAFT
domain: backend/orchestration
depends_on: [PRD-003, PRD-002]
---

# PRD-003-1 — SSE Event Pipeline & ARQ Worker Specification

| Field        | Value                                                                         |
|--------------|-------------------------------------------------------------------------------|
| Document ID  | PRD-003-1                                                                     |
| Version      | 1.0                                                                           |
| Status       | DRAFT                                                                         |
| Date         | March 2026                                                                    |
| Parent Doc   | [PRD-003](PRD-003-langgraph-orchestration.md)                                 |
| Related Docs | [PRD-002](PRD-002-frontend-ux.md) (Frontend SSE schema)                       |

---

## 1. Purpose & Scope

This document fully specifies the `transform_langgraph_event()` function and the surrounding
translation layer between LangGraph's internal event stream and the frontend SSE schema defined
in PRD-002.

PRD-003 establishes that the ARQ worker calls `graph.astream_events()` and publishes transformed
events to a Redis Pub/Sub channel. This document answers **how** that transformation works —
every LangGraph event type, every mapping rule, every edge case, and the complete annotated
`run_triage()` function.

**Boundary with PRD-003:** PRD-003 specifies the graph structure, state schema, HITL flow, and
checkpointing. This document covers only the event pipeline: what comes out of
`astream_events()` and how it becomes frontend SSE events.

---

## 2. `astream_events` v2 Reference

`graph.astream_events(input, config=config, version="v2")` is an async generator that yields
event dicts. The `version="v2"` parameter is required and changes event naming and metadata.

### Full Event Type Table

| Event type | Fires when | `event["data"]` contents | Key `event["metadata"]` fields |
|---|---|---|---|
| `on_chain_start` | A LangGraph node begins executing | `{"input": <node input dict>}` | `langgraph_node`, `langgraph_step`, `langgraph_checkpoint_ns`, `langgraph_triggers`, `langgraph_path` |
| `on_chain_end` | A LangGraph node finishes executing | `{"output": <node return dict>}` | `langgraph_node`, `langgraph_step`, `langgraph_checkpoint_ns` |
| `on_chain_stream` | Intermediate output from a node mid-run | `{"chunk": <partial output>}` | `langgraph_node`, `langgraph_step` |
| `on_chat_model_stream` | An LLM token is generated inside a node | `{"chunk": AIMessageChunk}` | `langgraph_node`, `langgraph_step`, `langgraph_checkpoint_ns` |
| `on_tool_start` | A tool invocation begins inside a node | `{"input": <tool input dict>}` | `langgraph_node`, `langgraph_step` |
| `on_tool_end` | A tool invocation completes inside a node | `{"output": <tool result>}` | `langgraph_node`, `langgraph_step` |
| `on_custom_event` | Application code called `emit_event()` | `{"data": <custom payload>}` | `langgraph_node` |

### Metadata Field Glossary

| Field | Type | Description |
|---|---|---|
| `langgraph_node` | `str` | Name of the currently executing graph node (e.g. `"investigator"`) |
| `langgraph_step` | `int` | Monotonically increasing step counter for the current graph execution |
| `langgraph_checkpoint_ns` | `str` | Namespace identifying the active checkpoint; format: `"node_name:uuid"` for parallel branches |
| `langgraph_triggers` | `list[str]` | Which edges triggered this node (usually `["supervisor"]` for worker nodes) |
| `langgraph_path` | `tuple[str, ...]` | Full path of the current execution context (useful for nested graphs) |

### Token Content Formats

`on_chat_model_stream` events contain `event["data"]["chunk"]` which is an `AIMessageChunk`.
The `.content` field varies by provider:

- **OpenAI / most providers:** `chunk.content` is a `str` — the raw token text.
- **Anthropic:** `chunk.content` may be a `list[dict]`, where each dict has `{"type": "text", "text": "..."}`.

The transformer must handle both forms (see §5).

> **Note:** `on_llm_stream` is the older pre-v2 event name. Some non-OpenAI providers and older
> LangChain integrations still emit it. The transformer handles both (see §10).

---

## 3. LangGraph → Frontend SSE Mapping Table

This is the authoritative mapping between LangGraph events and the frontend SSE schema from
PRD-002. Every SSE event type in PRD-002's event table has a row here.

| LangGraph event | Condition | Frontend SSE event | Payload mapping | Notes |
|---|---|---|---|---|
| `on_chain_start` | `metadata["langgraph_node"] in WORKER_NODES` | `agent.spawned` | `agent_id`: new UUID stored in `spawned_agents`; `agent_name`: `langgraph_node`; `node`: `langgraph_node` | Every `on_chain_start` generates a new agent card — including re-entries (node called twice); each gets its own UUID |
| `on_chat_model_stream` | `metadata["langgraph_node"] in WORKER_NODES` AND token non-empty | `agent.token` | `agent_id`: from `spawned_agents[langgraph_node]`; `token`: extracted string token | Drop events where extracted token is `""` |
| `on_tool_start` | `metadata["langgraph_node"] in WORKER_NODES` | `agent.tool_call` | `agent_id`: from `spawned_agents`; `tool_name`: `event["name"]`; `input_preview`: truncated JSON of `data["input"]` at 60 chars | **Requires `ToolNode`** for Tavily and any other tool — `on_tool_start` is not emitted by `RunnableLambda`; see PRD-004-1 §5 |
| `on_tool_end` | `metadata["langgraph_node"] in WORKER_NODES` | `agent.tool_result` | `agent_id`: from `spawned_agents`; `tool_name`: `event["name"]`; `result_summary`: `str(data["output"])[:120]` | Same `ToolNode` requirement as `on_tool_start` |
| `on_chain_end` | `metadata["langgraph_node"] in WORKER_NODES` | `agent.done` | `agent_id`: from `spawned_agents`; `node`: `langgraph_node`; `elapsed_ms`: not directly available — omit or compute from wall time | — |
| Post-loop `aget_state()` | `bool(state.tasks)` is True after loop exits | `graph.interrupt` | `question`: from `state.tasks[0].interrupts[0].value["question"]`; `context`: from `state.tasks[0].interrupts[0].value["context"]` | See §6 for interrupt detection details |
| Answer endpoint | After `Command(resume=...)` succeeds | `graph.resumed` | `job_id` | Emitted by the answer endpoint, not the worker |
| `on_chain_end` | `metadata["langgraph_node"] in ALL_NODES` (any node) | `graph.node_complete` | `node`: `langgraph_node`; `step`: `langgraph_step` | Includes supervisor; useful for ExecutionTimeline |
| Pause endpoint | After interrupt fires for manual pause | `graph.paused` | `job_id` | Emitted by the pause endpoint, not the worker |
| `on_chat_model_stream` | `metadata["langgraph_node"] == "writer"` AND token non-empty | `output.token` | `token`: extracted string; `section`: derived from `langgraph_checkpoint_ns` | Uses checkpoint namespace to identify which RunnableParallel branch |
| `on_chain_end` | `metadata["langgraph_node"] == "writer"` AND `event["name"] in {"report", "comment_draft", "ticket_draft"}` | `output.section_done` | `section`: `event["name"]` | See §8 for RunnableParallel details |
| After `astream_events` loop completes without interrupt | — | `job.done` | — | Emitted by worker after loop exits clean |
| Exception in `astream_events` loop | — | `job.failed` | `error`: exception message | Emitted by worker's except block |

### ALL_NODES Constant

```python
ALL_NODES = {
    "supervisor", "investigator", "codebase_search",
    "web_search", "critic", "human_input", "writer"
}
```

---

## 4. WORKER_NODES Constant

`WORKER_NODES` is the set of node names that generate agent cards in the UI. The supervisor and
`human_input` nodes are excluded — they do not produce agent cards.

```python
WORKER_NODES = {"investigator", "codebase_search", "web_search", "critic", "writer"}
```

This constant is used in `transform_langgraph_event()` to gate which events produce
`agent.*` SSE events.

---

## 5. `transform_langgraph_event()` Specification

### Signature

```python
def transform_langgraph_event(
    event: dict,
    spawned_agents: dict[str, str],  # mutated in place: langgraph_node -> agent_id UUID
) -> list[dict]:
    """
    Translate a single LangGraph v2 event dict into zero or more frontend SSE event dicts.

    Returns an empty list if the event should be dropped (not published to Redis).
    Returns a list with two elements when a worker on_chain_end produces both
    agent.done (or output.section_done) and graph.node_complete.

    `spawned_agents` is maintained by the caller (run_triage) across the full
    astream_events loop. It maps graph node names to stable UUID agent_ids.
    """
```

### Input Structure

```python
{
    "event": str,           # e.g. "on_chat_model_stream"
    "name": str,            # runnable name (e.g. tool name, branch name)
    "data": dict,           # event-specific payload
    "metadata": dict,       # langgraph_node, langgraph_step, etc.
    "tags": list[str],
    "run_id": str,          # UUID of this specific run
    "parent_ids": list[str],
}
```

### Decision Tree Pseudocode

```python
def transform_langgraph_event(event, spawned_agents):
    ev = event["event"]
    meta = event.get("metadata", {})
    node = meta.get("langgraph_node")

    # Drop events without a langgraph_node (inner chain events — see §10)
    if not node:
        return []

    # --- agent.spawned ---
    # Emitted on every on_chain_start, including re-entries (node called twice in one run).
    # Each execution gets a fresh UUID so the UI shows a separate agent card per run.
    if ev == "on_chain_start" and node in WORKER_NODES:
        agent_id = str(uuid4())
        spawned_agents[node] = agent_id
        return [{
            "type": "agent.spawned",
            "agent_id": agent_id,
            "agent_name": node,
            "node": node,
        }]

    # --- agent.token / output.token ---
    if ev in {"on_chat_model_stream", "on_llm_stream"}:
        token = _extract_token(event["data"].get("chunk"))
        if not token:
            return []  # drop empty chunks

        if node == "writer":
            return [{
                "type": "output.token",
                "token": token,
                "section": _section_from_ns(meta.get("langgraph_checkpoint_ns", "")),
            }]
        elif node in WORKER_NODES:
            agent_id = spawned_agents.get(node)
            if not agent_id:
                return []
            return [{
                "type": "agent.token",
                "agent_id": agent_id,
                "token": token,
            }]
        return []

    # --- agent.tool_call ---
    if ev == "on_tool_start" and node in WORKER_NODES:
        agent_id = spawned_agents.get(node)
        if not agent_id:
            return []
        raw_input = event["data"].get("input", {})
        preview = json.dumps(raw_input, default=str)
        if len(preview) > 60:
            preview = preview[:60] + "..."
        return [{
            "type": "agent.tool_call",
            "agent_id": agent_id,
            "tool_name": event.get("name", "unknown"),
            "input_preview": preview,
        }]

    # --- agent.tool_result ---
    if ev == "on_tool_end" and node in WORKER_NODES:
        agent_id = spawned_agents.get(node)
        if not agent_id:
            return []
        output = event["data"].get("output", "")
        return [{
            "type": "agent.tool_result",
            "agent_id": agent_id,
            "tool_name": event.get("name", "unknown"),
            "result_summary": str(output)[:120],
        }]

    # --- agent.done + graph.node_complete (worker nodes) ---
    if ev == "on_chain_end" and node in WORKER_NODES:
        node_complete = {
            "type": "graph.node_complete",
            "node": node,
            "step": meta.get("langgraph_step"),
        }
        # Check for writer RunnableParallel branch first (output.section_done)
        branch_name = event.get("name", "")
        if node == "writer" and branch_name in {"report", "comment_draft", "ticket_draft"}:
            return [
                {"type": "output.section_done", "section": branch_name},
                node_complete,
            ]
        agent_id = spawned_agents.get(node)
        if not agent_id:
            return [node_complete]
        return [
            {"type": "agent.done", "agent_id": agent_id, "node": node},
            node_complete,
        ]

    # --- graph.node_complete (supervisor and human_input — non-worker nodes) ---
    if ev == "on_chain_end" and node in ALL_NODES:
        return [{
            "type": "graph.node_complete",
            "node": node,
            "step": meta.get("langgraph_step"),
        }]

    return []
```

### Token Extraction Helper

```python
def _extract_token(chunk) -> str:
    """
    Extract a plain string token from an AIMessageChunk.
    Handles both str content (OpenAI) and list[dict] content (Anthropic).
    """
    if chunk is None:
        return ""
    content = getattr(chunk, "content", chunk)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
        return "".join(parts)
    return ""
```

### Section Helper for Writer Tokens

```python
def _section_from_ns(checkpoint_ns: str) -> str | None:
    """
    Derive the writer RunnableParallel section name from the checkpoint namespace.
    Format is typically "writer:uuid4|branch_name:uuid4".
    Returns the branch name if found, else None.
    """
    known_sections = {"report", "comment_draft", "ticket_draft"}
    for part in checkpoint_ns.split("|"):
        name = part.split(":")[0]
        if name in known_sections:
            return name
    return None
```

---

## 6. Interrupt Detection: `_is_human_input_interrupt()`

### Primary Method (Recommended)

After the `astream_events` loop exits, call `graph.aget_state(config)` and check whether
`state.tasks` is non-empty. A non-empty `tasks` list means the graph suspended at an
`interrupt()` call — it did not run to completion.

```python
async def _check_for_interrupt(graph, config) -> dict | bool:
    """
    Returns the interrupt payload dict if the graph is suspended at a human_input
    interrupt, or False if the graph completed normally.

    Call this AFTER the astream_events loop exits.
    """
    state = await graph.aget_state(config)
    if not state.tasks:
        return False
    # Graph is suspended — extract interrupt payload
    try:
        payload = state.tasks[0].interrupts[0].value
        # payload is the dict passed to interrupt(): {"question": ..., "context": ...}
        return payload
    except (IndexError, AttributeError):
        # Tasks present but no interrupt value — unexpected; treat as completed
        return False
```

### Alternative Method (Stream-Mode Updates)

If you also need to detect the interrupt during the stream (not just after), add
`stream_mode=["updates"]` alongside `version="v2"` in the `astream_events` call and check for
the `"__interrupt__"` key in update chunks:

```python
async for event in graph.astream_events(
    initial_state,
    config=config,
    version="v2",
    stream_mode=["updates"],
):
    if isinstance(event, dict) and "__interrupt__" in event:
        # Graph is about to suspend
        interrupt_payload = event["__interrupt__"][0].value
```

For the ARQ worker pattern in PRD-003, the primary method (post-loop `aget_state()`) is
preferred because it is simpler and the `astream_events` loop terminates naturally when
`interrupt()` fires (the graph suspends, the generator exhausts).

### Interrupt Payload Structure

```python
# What interrupt() receives from the graph:
state.tasks[0].interrupts[0].value
# -> {"question": "...", "context": "..."}
# These are the keys passed to interrupt({...}) in human_input_node.
```

---

## 7. Agent Identity Tracking

### Problem

`on_chat_model_stream` and other events identify the currently-executing node via
`metadata["langgraph_node"]` (a string like `"investigator"`). The frontend, however, expects a
stable `agent_id` UUID per spawned agent instance — not a node name — so it can match tokens,
tool calls, and completion events to the same agent card.

### Solution

The worker maintains `spawned_agents: dict[str, str]` initialized as `{}` before the
`astream_events` loop begins. This dict is passed to `transform_langgraph_event()` by reference
and mutated in place.

```python
spawned_agents: dict[str, str] = {}  # node_name -> agent_id UUID

async for event in graph.astream_events(initial_state, config=config, version="v2"):
    for sse in transform_langgraph_event(event, spawned_agents):
        await redis.publish(channel, json.dumps(sse))
```

**Every `on_chain_start` for a worker node:** A new UUID is generated and stored in
`spawned_agents[node]`. All subsequent events for that execution (tokens, tool calls, chain_end)
look up the current UUID via `spawned_agents[node]`.

**Node called a second time (e.g. `investigator` redirected back):** Each `on_chain_start`
generates a fresh UUID. The old agent card in the UI remains (its `agent_id` is still valid);
a new card is created for the new run. This means the UI correctly shows two separate
investigator cards for two separate investigator runs.

---

## 8. Writer RunnableParallel → `output.section_done`

The writer node uses `RunnableParallel` to produce three output sections concurrently:

```python
writer_chain = RunnableParallel(
    report=report_chain,
    comment_draft=comment_chain,
    ticket_draft=ticket_chain,
)
```

### Event Detection

Each branch of the `RunnableParallel` emits an `on_chain_end` event when it completes. The
distinguishing fields:

- `event["event"] == "on_chain_end"`
- `event["metadata"]["langgraph_node"] == "writer"`
- `event["name"] in {"report", "comment_draft", "ticket_draft"}`

This maps to `output.section_done { section: event["name"] }`.

### Token Attribution

During writer execution, `on_chat_model_stream` events include `langgraph_checkpoint_ns`
identifying which parallel branch is running. The `_section_from_ns()` helper (§5) parses this
to set the `section` field on `output.token` events, so the frontend can route tokens to the
correct section panel.

Checkpoint namespace format for a parallel branch:
```
"writer:550e8400-e29b-41d4-a716-446655440000|report:7c9e6679-7425-40de-944b-e07fc1f90ae7"
```
The `_section_from_ns()` function splits on `|`, then splits each segment on `:` to get the
name prefix, and matches against the known section names.

---

## 9. Full Annotated `run_triage()` Function

### Service-Wide Worker Error Handler

Exception handling for cross-cutting concerns (publishing `job.failed`, logging) lives in one
place: a `@worker_error_handler` decorator applied to every ARQ worker function. No individual
worker function handles exceptions it cannot recover from. This is the project's
"service-wide middleware" for worker-layer errors (see PRD-007 §Architecture policy).

```python
# worker_middleware.py

import functools
import json
import logging
from collections.abc import Callable, Coroutine
from typing import Any

from redis.asyncio import Redis

logger = logging.getLogger(__name__)


def worker_error_handler(fn: Callable[..., Coroutine[Any, Any, None]]) -> Callable[..., Coroutine[Any, Any, None]]:
    """Service-wide ARQ worker error handler.

    Publishes job.failed to the Redis SSE channel on any unhandled exception,
    then re-raises so ARQ records the job as FAILED. Declared once; applied to
    all worker functions in WorkerSettings. Individual worker functions must not
    catch exceptions they cannot locally recover from.
    """
    @functools.wraps(fn)
    async def wrapper(ctx: dict, job_id: str, *args: object, **kwargs: object) -> None:
        try:
            return await fn(ctx, job_id, *args, **kwargs)
        except Exception as exc:
            redis: Redis = ctx["redis"]
            logger.exception("Worker function %s failed for job %s", fn.__name__, job_id)
            await redis.publish(
                f"jobs:{job_id}:events",
                json.dumps({"type": "job.failed", "error": str(exc)}),
            )
            raise

    return wrapper
```

### `run_triage()` — Clean, No Exception Handling

```python
# worker.py

import json
from datetime import timedelta
from uuid import uuid4

from arq import ArqRedis
from redis.asyncio import Redis

from .graph import graph
from .transform import transform_langgraph_event, _check_for_interrupt
from .worker_middleware import worker_error_handler

HUMAN_INPUT_TIMEOUT_SECONDS = 1800  # 30 minutes


@worker_error_handler
async def run_triage(ctx: dict, job_id: str, initial_state: dict) -> None:
    """Run the LangGraph triage graph and stream SSE events to Redis Pub/Sub.

    Streams graph execution events, translates them to frontend SSE format,
    and publishes each to the job's Redis channel. After the loop, detects
    whether the graph suspended at a human_input interrupt or completed normally
    and publishes the appropriate terminal event. Unhandled exceptions are caught
    and published by the worker_error_handler decorator.
    """
    redis: Redis = ctx["redis"]
    arq_queue: ArqRedis = ctx["arq_queue"]
    config = {"configurable": {"thread_id": job_id}}
    channel = f"jobs:{job_id}:events"

    spawned_agents: dict[str, str] = {}

    async for event in graph.astream_events(initial_state, config=config, version="v2"):
        for sse in transform_langgraph_event(event, spawned_agents):
            await redis.publish(channel, json.dumps(sse))

    interrupt_payload = await _check_for_interrupt(graph, config)

    if interrupt_payload:
        await redis.publish(channel, json.dumps({
            "type": "graph.interrupt",
            "question": interrupt_payload.get("question", ""),
            "context": interrupt_payload.get("context", ""),
        }))
        await arq_queue.enqueue_job(
            "expire_human_input",
            job_id,
            _job_id=f"timeout:{job_id}",
            _defer_by=timedelta(seconds=HUMAN_INPUT_TIMEOUT_SECONDS),
        )
    else:
        await redis.publish(channel, json.dumps({"type": "job.done"}))


class WorkerSettings:
    functions = [run_triage]
    allow_abort_jobs = True    # enables Job.abort() cross-worker
    max_jobs = 10              # concurrent job cap per worker
    retry_jobs = False         # at-most-once; deduplication at API layer (PRD-006)
```

---

## 10. Known Issues & Gotchas

### `on_llm_stream` vs `on_chat_model_stream`

Some providers and older LangChain integrations emit `on_llm_stream` instead of
`on_chat_model_stream`. The transformer checks both:

```python
if ev in {"on_chat_model_stream", "on_llm_stream"}:
    ...
```

### Nested Runnable Streaming

If a worker node uses a sub-chain rather than calling the LLM directly, `astream_events` may
not propagate inner events (LangChain issue #6105). Worker agents must be called via `httpx` to
LangServe (as specified in PRD-003 §Worker Agent Node Specs), not as nested LangChain chains.
Nested chain calls inside a graph node will produce incomplete event streams.

### Event Deduplication

`astream_events` can emit duplicate token events with different `run_id` but same content for
the same generation step. The primary deduplication filter is:

```python
if not meta.get("langgraph_node"):
    return None  # drop inner chain events that lack graph context
```

Only process events where `metadata["langgraph_node"]` is set. Graph-level events always have
it; inner chain events for the same token may not.

### Empty Content Chunks

Models emit `on_chat_model_stream` events with empty-string content at the start and end of
generation (role-only chunks). Drop these:

```python
token = _extract_token(chunk)
if not token:
    return None
```

### Multiple `on_chain_start` for the Same Node

If the supervisor routes to the same worker twice (redirect flow), each `on_chain_start` fires
for that node. The current implementation correctly handles this by generating a new UUID each
time, creating a second agent card. The `spawned_agents` dict is intentionally overwritten (not
guarded with `if node not in spawned_agents`) for this reason.
