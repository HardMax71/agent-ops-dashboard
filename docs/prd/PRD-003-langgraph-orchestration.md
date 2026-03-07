# PRD-003 — LangGraph Orchestration & Human-in-the-Loop

## AgentOps Dashboard — Agent Runtime Requirements

| Field        | Value                                             |
|--------------|---------------------------------------------------|
| Document ID  | PRD-003                                           |
| Version      | 1.0                                               |
| Status       | DRAFT                                             |
| Date         | March 2026                                        |
| Parent Doc   | PRD-001                                           |
| Related Docs | PRD-002 (Frontend), PRD-004 (LangChain/LangServe) |

---

## Table of Contents

1. [Overview](#1-overview)
2. [LangGraph Fundamentals Used](#2-langgraph-fundamentals-used)
3. [Shared State Schema](#3-shared-state-schema)
4. [Graph Structure](#4-graph-structure)
5. [Supervisor Agent Design](#5-supervisor-agent-design)
6. [Worker Agent Node Specs](#6-worker-agent-node-specs)
7. [Human-in-the-Loop Implementation](#7-human-in-the-loop-implementation)
8. [Pause, Redirect, and Kill](#8-pause-redirect-and-kill)
9. [Checkpointing and Persistence](#9-checkpointing-and-persistence)
10. [Streaming to Frontend](#10-streaming-to-frontend)
11. [Error Handling](#11-error-handling)

---

## 1. Overview

This document specifies the LangGraph orchestration layer of AgentOps Dashboard — the system's brain. It covers how the
supervisor coordinates worker agents, how shared state flows through the graph, how human interrupts are handled, and
how job state is persisted across sessions.

LangGraph is used here in its intended role: **low-level orchestration of long-running, stateful, multi-agent workflows
**. It is deliberately not used for simple linear chains (those live in LangChain/LCEL at the LangServe layer — see
PRD-004).

---

## 2. LangGraph Fundamentals Used

| Concept           | Usage in This Product                                                                                                                     |
|-------------------|-------------------------------------------------------------------------------------------------------------------------------------------|
| `StateGraph`      | The main graph class; holds the shared `BugTriageState` across all nodes                                                                  |
| Nodes             | Each agent and decision point is a node: `supervisor`, `investigator`, `codebase_search`, `web_search`, `critic`, `human_input`, `writer` |
| Conditional edges | Supervisor's output determines which worker runs next via `add_conditional_edges`                                                         |
| `interrupt()`     | Pauses graph execution mid-node to await human input; resumes via `Command(resume=answer)`                                                |
| Checkpointer      | `SqliteSaver` (dev) / `PostgresSaver` (prod) — persists full graph state so jobs survive restarts                                         |
| Thread ID         | Each triage job maps to a LangGraph thread; jobs are fully isolated                                                                       |
| Streaming         | `graph.astream_events()` emits fine-grained events consumed by FastAPI SSE endpoint                                                       |

---

## 3. Shared State Schema

The `BugTriageState` TypedDict is the central data structure. Every node reads from and writes to this state. It is
persisted at every checkpoint.

```python
from typing import TypedDict, Optional, Annotated
from langgraph.graph.message import add_messages


class AgentFinding(TypedDict):
    agent_name: str
    summary: str
    details: str
    confidence: float  # 0.0 – 1.0
    relevant_files: list[str]


class HumanExchange(TypedDict):
    question: str
    context: str  # why the agent is asking
    answer: Optional[str]  # None until user responds


class TriageReport(TypedDict):
    severity: str  # LOW / MEDIUM / HIGH / CRITICAL
    category: str
    root_cause: str
    relevant_files: list[str]
    similar_issues: list[str]
    confidence: float


class BugTriageState(TypedDict):
    # Input
    issue_url: str
    issue_title: str
    issue_body: str
    repository: str

    # Orchestration control
    current_node: str
    next_node: Optional[str]
    supervisor_reasoning: str  # why supervisor chose next agent
    iterations: int  # guard against infinite loops
    max_iterations: int  # default: 12

    # Agent findings (accumulated)
    findings: Annotated[list[AgentFinding], lambda a, b: a + b]  # reducer: append

    # Human-in-the-loop
    human_exchanges: list[HumanExchange]  # full Q&A history
    awaiting_human: bool

    # Codebase context
    codebase_chunks: list[str]  # retrieved from vector index
    similar_past_issues: list[str]  # from issue search

    # Web search context
    web_results: list[str]

    # Final outputs
    report: Optional[TriageReport]
    github_comment_draft: Optional[str]
    ticket_draft: Optional[dict]

    # Metadata
    job_id: str
    langsmith_run_id: Optional[str]
    status: str  # matches frontend JobStatus enum
```

---

## 4. Graph Structure

### 4.1 Node List

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

### 4.2 Graph Definition (Pseudocode)

```python
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver

builder = StateGraph(BugTriageState)

# Add all nodes
builder.add_node("supervisor", supervisor_node)
builder.add_node("investigator", investigator_node)
builder.add_node("codebase_search", codebase_search_node)
builder.add_node("web_search", web_search_node)
builder.add_node("critic", critic_node)
builder.add_node("human_input", human_input_node)
builder.add_node("writer", writer_node)

# Entry: always start at supervisor
builder.add_edge(START, "supervisor")

# Supervisor routes conditionally
builder.add_conditional_edges(
    "supervisor",
    route_from_supervisor,  # returns the next node name
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

# All worker agents return to supervisor after completing
for node in ["investigator", "codebase_search", "web_search", "critic"]:
    builder.add_edge(node, "supervisor")

# Human input returns to supervisor with enriched state
builder.add_edge("human_input", "supervisor")

# Writer goes straight to END (final node)
builder.add_edge("writer", END)

# Compile with checkpointer
checkpointer = SqliteSaver.from_conn_string("jobs.db")
graph = builder.compile(checkpointer=checkpointer)
```

### 4.3 Routing Logic

```python
def route_from_supervisor(state: BugTriageState) -> str:
    """
    Supervisor LLM outputs structured JSON with 'next' field.
    This function extracts it and returns the node name.
    Guards: max_iterations check, required-findings check.
    """
    if state["iterations"] >= state["max_iterations"]:
        return "writer"  # force completion

    return state["next_node"]  # set by supervisor node
```

---

## 5. Supervisor Agent Design

The supervisor is the most critical node. It reads the full current state and decides:

1. Which worker to call next (or whether to ask the human, or to finalize)
2. Whether it has enough information to write the final report
3. Whether it needs to ask the user a clarifying question

### 5.1 Supervisor System Prompt (Abbreviated)

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

### 5.2 Supervisor Output Schema

```python
class SupervisorDecision(BaseModel):
    next_node: Literal[
        "investigator", "codebase_search", "web_search",
        "critic", "human_input", "writer", "end"
    ]
    reasoning: str  # shown in UI as supervisor's thinking
    question: Optional[str]  # only if next_node == "human_input"
    question_context: Optional[str]
    confidence: float  # 0.0–1.0; used for quality metrics
```

---

## 6. Worker Agent Node Specs

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

## 7. Human-in-the-Loop Implementation

### 7.1 Triggering an Interrupt

When the supervisor routes to `human_input`, the node fires `interrupt()`:

```python
from langgraph.types import interrupt


def human_input_node(state: BugTriageState) -> dict:
    # Get the question set by supervisor in prior step
    last_exchange = state["human_exchanges"][-1]

    # This pauses the graph and surfaces the question to the user
    answer = interrupt({
        "question": last_exchange["question"],
        "context": last_exchange["question_context"],
    })

    # When resumed, `answer` contains the user's response
    updated_exchanges = state["human_exchanges"].copy()
    updated_exchanges[-1]["answer"] = answer

    return {
        "human_exchanges": updated_exchanges,
        "awaiting_human": False,
    }
```

### 7.2 Resuming from FastAPI

When the user submits an answer via `POST /jobs/{id}/answer`:

```python
@app.post("/jobs/{job_id}/answer")
async def submit_answer(job_id: str, body: AnswerRequest):
    config = {"configurable": {"thread_id": job_id}}

    # Resume the graph with the user's answer
    await graph.ainvoke(
        Command(resume=body.answer),
        config=config,
    )
```

### 7.3 Question Constraints

| Rule                  | Value                                                  | Rationale                                               |
|-----------------------|--------------------------------------------------------|---------------------------------------------------------|
| Max questions per job | 2                                                      | Prevent over-reliance on user; agents should be capable |
| Timeout (no answer)   | 30 minutes                                             | After timeout, supervisor proceeds with best-effort     |
| Question format       | Single question + 2–3 concrete options when applicable | Reduces cognitive load                                  |
| Blocker scope         | Entire graph pauses, not just one agent                | Ensures answer is incorporated before any further work  |

---

## 8. Pause, Redirect, and Kill

### 8.1 Pause

Triggered by user clicking "Pause" in the UI. Sends `POST /jobs/{id}/pause`.

Implementation: Sets a flag in the checkpointed state. The supervisor checks this flag at the start of each iteration
and fires `interrupt()` with a "manual pause" signal if set. User can resume by clicking "Resume".

### 8.2 Redirect

Triggered after a pause. User can type a new instruction into a text field in the UI: e.g., "Focus only on the database
layer — ignore the auth middleware."

Implementation: Resumes the graph via `Command(resume={"type": "redirect", "instruction": "..."})`. The supervisor node
treats redirect instructions as high-priority context prepended to its system prompt for all subsequent steps.

### 8.3 Kill

Sends `DELETE /jobs/{id}`. Immediately terminates the LangGraph thread. Final state is checkpointed with
`status: "killed"`. Any partial outputs already in state are preserved and shown in the output panel.

```python
@app.delete("/jobs/{job_id}")
async def kill_job(job_id: str):
    config = {"configurable": {"thread_id": job_id}}
    # Update state to killed before cancelling
    await graph.aupdate_state(config, {"status": "killed"})
    # Cancel the background task running the graph
    running_tasks[job_id].cancel()
```

---

## 9. Checkpointing and Persistence

### 9.1 Why Checkpointing Matters

LangGraph's checkpointer saves the full `BugTriageState` to a database after every node execution. This means:

- Jobs survive server restarts
- Users can close the browser and come back to a running job
- The full execution history is available for debugging
- Paused jobs (waiting for human input) persist indefinitely until answered

### 9.2 Configuration

| Environment | Checkpointer    | Connection             |
|-------------|-----------------|------------------------|
| Development | `SqliteSaver`   | `jobs.db` (local file) |
| Production  | `PostgresSaver` | `DATABASE_URL` env var |

### 9.3 Thread IDs

Each job is identified by a UUID that maps 1:1 to a LangGraph thread ID. This UUID is generated at `POST /jobs` and is
the same ID used in SSE stream URLs, answer endpoints, and LangSmith trace grouping.

---

## 10. Streaming to Frontend

LangGraph's `astream_events()` emits fine-grained events. The FastAPI SSE handler subscribes to these and transforms
them into the frontend event types defined in PRD-002.

```python
@app.get("/jobs/{job_id}/stream")
async def stream_job(job_id: str):
    async def event_generator():
        config = {"configurable": {"thread_id": job_id}}
        async for event in graph.astream_events(None, config=config, version="v2"):
            sse_event = transform_langgraph_event(event)
            if sse_event:
                yield f"data: {json.dumps(sse_event)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

The `transform_langgraph_event()` function maps LangGraph's internal event types (e.g., `on_chat_model_stream`,
`on_tool_start`, `on_chain_end`) to the frontend event schema in PRD-002.

---

## 11. Error Handling

| Error Scenario                          | Behavior                                                                                                                      |
|-----------------------------------------|-------------------------------------------------------------------------------------------------------------------------------|
| Worker agent LangServe endpoint is down | Supervisor retries once after 5s; on second failure, marks agent as errored and routes to next available agent or human_input |
| LLM rate limit (429)                    | Exponential backoff with max 3 retries; after that, job status set to FAILED                                                  |
| Supervisor outputs invalid JSON         | Pydantic validation catches it; supervisor is re-invoked once with an error correction prompt                                 |
| `max_iterations` reached                | Graph routes directly to `writer` with whatever findings have been accumulated                                                |
| Unhandled exception in any node         | Job status set to FAILED; full traceback captured in LangSmith; error event sent to frontend                                  |
| Checkpointer DB unavailable             | Job continues in-memory; warning logged; user notified that job will not survive restart                                      |
