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

The transformer uses `chunk.text` (a `TextAccessor` str subclass) which handles both forms internally — no branching needed in application code (see §6).

> **Note:** `on_llm_stream` is the older pre-v2 event name. Some non-OpenAI providers and older
> LangChain integrations still emit it. The transformer handles both (see §11).

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
| Post-loop `aget_state()` | `bool(state.tasks)` is True after loop exits | `graph.interrupt` | `question`: from `interrupt_payload.question`; `context`: from `interrupt_payload.context` (`HumanExchange` dot fields) | See §7 for interrupt detection details |
| Answer endpoint | After `Command(resume=...)` succeeds | `graph.resumed` | `job_id` | Emitted by the answer endpoint, not the worker |
| `on_chain_end` | `metadata["langgraph_node"] in ALL_NODES` (any node) | `graph.node_complete` | `node`: `langgraph_node`; `step`: `langgraph_step` | Includes supervisor; useful for ExecutionTimeline |
| Pause endpoint | After interrupt fires for manual pause | `graph.paused` | `job_id` | Emitted by the pause endpoint, not the worker |
| `on_chat_model_stream` | `metadata["langgraph_node"] == "writer"` AND token non-empty | `output.token` | `token`: extracted string; `section`: derived from `langgraph_checkpoint_ns` | Uses checkpoint namespace to identify which RunnableParallel branch |
| `on_chain_end` | `metadata["langgraph_node"] == "writer"` AND `event["name"] in {"report", "comment_draft", "ticket_draft"}` | `output.section_done` | `section`: `event["name"]` | See §9 for RunnableParallel details |
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

## 5. SSE Event Type Definitions

All SSE event types are declared as `TypedDict`s so every payload is statically typed
end-to-end. No `dict` literals, no `cast()`, no `isinstance()`.

```python
from typing import Literal, TypeAlias, TypedDict
from langchain_core.runnables.schema import StandardStreamEvent


class LangGraphEventMetadata(TypedDict, total=False):
    langgraph_node: str
    langgraph_step: int
    langgraph_checkpoint_ns: str
    langgraph_triggers: list[str]


class AgentSpawnedEvent(TypedDict):
    type: Literal["agent.spawned"]
    agent_id: str
    agent_name: str
    node: str

class AgentTokenEvent(TypedDict):
    type: Literal["agent.token"]
    agent_id: str
    token: str

class OutputTokenEvent(TypedDict):
    type: Literal["output.token"]
    token: str
    section: str | None

class AgentToolCallEvent(TypedDict):
    type: Literal["agent.tool_call"]
    agent_id: str
    tool_name: str
    input_preview: str

class AgentToolResultEvent(TypedDict):
    type: Literal["agent.tool_result"]
    agent_id: str
    tool_name: str
    result_summary: str

class AgentDoneEvent(TypedDict):
    type: Literal["agent.done"]
    agent_id: str
    node: str

class OutputSectionDoneEvent(TypedDict):
    type: Literal["output.section_done"]
    section: str

class GraphNodeCompleteEvent(TypedDict):
    type: Literal["graph.node_complete"]
    node: str
    step: int | None

SseEvent: TypeAlias = (
    AgentSpawnedEvent | AgentTokenEvent | OutputTokenEvent |
    AgentToolCallEvent | AgentToolResultEvent | AgentDoneEvent |
    OutputSectionDoneEvent | GraphNodeCompleteEvent
)
```

---

## 6. `LangGraphEventTransformer` Specification

The transformer replaces an if/elif chain with a dispatch table injected via DI.
Each handler is a plain typed function; the transformer class is stateless beyond its
`_handlers` dict.

### Handler Type

```python
from collections.abc import Callable
from langchain_core.messages import AIMessageChunk

_EventHandler: TypeAlias = Callable[[StandardStreamEvent, dict[str, str]], list[SseEvent]]
```

### Metadata Helper

```python
def _meta(event: StandardStreamEvent) -> LangGraphEventMetadata:
    return event.get("metadata", {})  # type: ignore[return-value]
```

### Individual Handlers

```python
def _handle_stream(event: StandardStreamEvent, spawned_agents: dict[str, str]) -> list[SseEvent]:
    meta = _meta(event)
    node = meta.get("langgraph_node", "")
    agent_id = spawned_agents.get(node, "")
    chunk: AIMessageChunk = event["data"]["chunk"]   # Any → typed (valid Pyright)
    token = chunk.text                                # TextAccessor — str subclass
    if not token:
        return []
    if agent_id:
        return [AgentTokenEvent(type="agent.token", agent_id=agent_id, token=token)]
    return [OutputTokenEvent(type="output.token", token=token, section=node or None)]


def _handle_tool_start(event: StandardStreamEvent, spawned_agents: dict[str, str]) -> list[SseEvent]:
    meta = _meta(event)
    node = meta.get("langgraph_node", "")
    agent_id = spawned_agents.get(node, "")
    if not agent_id:
        return []
    tool_name: str = event["name"]
    input_preview = str(event["data"].get("input", ""))[:120]
    return [AgentToolCallEvent(
        type="agent.tool_call", agent_id=agent_id,
        tool_name=tool_name, input_preview=input_preview,
    )]


def _handle_tool_end(event: StandardStreamEvent, spawned_agents: dict[str, str]) -> list[SseEvent]:
    meta = _meta(event)
    node = meta.get("langgraph_node", "")
    agent_id = spawned_agents.get(node, "")
    if not agent_id:
        return []
    tool_name: str = event["name"]
    result_summary = str(event["data"].get("output", ""))[:120]
    return [AgentToolResultEvent(
        type="agent.tool_result", agent_id=agent_id,
        tool_name=tool_name, result_summary=result_summary,
    )]


def _handle_chain_end(event: StandardStreamEvent, spawned_agents: dict[str, str]) -> list[SseEvent]:
    meta = _meta(event)
    node = meta.get("langgraph_node", "")
    step = meta.get("langgraph_step")
    return [GraphNodeCompleteEvent(type="graph.node_complete", node=node, step=step)]
```

### Transformer Class

```python
class LangGraphEventTransformer:
    """Injected via DI container (see PRD-012). Wire up in the dependency factory."""

    def __init__(self, handlers: dict[str, _EventHandler]) -> None:
        self._handlers = handlers

    def transform(
        self,
        event: StandardStreamEvent,
        spawned_agents: dict[str, str],
    ) -> list[SseEvent]:
        handler = self._handlers.get(event["event"])
        return handler(event, spawned_agents) if handler is not None else []
```

DI wire-up (in the container / factory, not in module scope):

```python
LangGraphEventTransformer(handlers={
    "on_chat_model_stream": _handle_stream,
    "on_llm_stream": _handle_stream,    # legacy provider compat — same handler
    "on_tool_start": _handle_tool_start,
    "on_tool_end": _handle_tool_end,
    "on_chain_end": _handle_chain_end,
})
```

Zero if/elif. Zero isinstance. Zero reflection. Adding a new event type = add one handler
function + one entry in the DI wire-up.

> **`BaseMessage.text`:** `AIMessageChunk.text` is a `TextAccessor` (`str` subclass) that
> handles both `str` content (OpenAI) and `list[dict]` content (Anthropic) internally.
> Call `.text` directly — never inspect `.content` or `.content_blocks`.

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

## 7. Interrupt Detection: `_check_for_interrupt()`

### Primary Method (Recommended)

After the `astream_events` loop exits, call `graph.aget_state(config)` and check whether
`state.tasks` is non-empty. A non-empty `tasks` list means the graph suspended at an
`interrupt()` call — it did not run to completion.

```python
async def _check_for_interrupt(graph, config) -> HumanExchange | None:
    """
    Returns the HumanExchange if the graph is suspended at a human_input interrupt,
    or None if the graph completed normally.

    Call this AFTER the astream_events loop exits.
    human_input_node calls interrupt(state.pending_exchange) — the value is a HumanExchange.
    """
    state = await graph.aget_state(config)
    if not state.tasks:
        return None
    return state.tasks[0].interrupts[0].value
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
    if "__interrupt__" in event:
        # Graph is about to suspend
        interrupt_payload: HumanExchange = event["__interrupt__"][0].value
```

For the ARQ worker pattern in PRD-003, the primary method (post-loop `aget_state()`) is
preferred because it is simpler and the `astream_events` loop terminates naturally when
`interrupt()` fires (the graph suspends, the generator exhausts).

### Interrupt Payload Structure

```python
# human_input_node calls: interrupt(state.pending_exchange)
# state.pending_exchange is a HumanExchange — dot fields throughout:
state.tasks[0].interrupts[0].value   # -> HumanExchange
# Access: interrupt_payload.question, interrupt_payload.context
```

---

## 8. Agent Identity Tracking

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

## 9. Writer RunnableParallel → `output.section_done`

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
identifying which parallel branch is running. The `_section_from_ns()` helper (§6) parses this
to set the `section` field on `output.token` events, so the frontend can route tokens to the
correct section panel.

Checkpoint namespace format for a parallel branch:
```
"writer:550e8400-e29b-41d4-a716-446655440000|report:7c9e6679-7425-40de-944b-e07fc1f90ae7"
```
The `_section_from_ns()` function splits on `|`, then splits each segment on `:` to get the
name prefix, and matches against the known section names.

---

## 10. Full Annotated `run_triage()` Function

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
            "question": interrupt_payload.question,
            "context": interrupt_payload.context,
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

## 11. Known Issues & Gotchas

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
chunk: AIMessageChunk = event["data"]["chunk"]
token = chunk.text   # TextAccessor (str subclass) — empty string for role-only chunks
if not token:
    return []
```

### Multiple `on_chain_start` for the Same Node

If the supervisor routes to the same worker twice (redirect flow), each `on_chain_start` fires
for that node. The current implementation correctly handles this by generating a new UUID each
time, creating a second agent card. The `spawned_agents` dict is intentionally overwritten (not
guarded with `if node not in spawned_agents`) for this reason.
