"""Pure Strawberry types for the GraphQL schema.

No Pydantic bridge — types defined directly as Strawberry dataclasses.
"""

from __future__ import annotations

from typing import Annotated

import strawberry

# ── Query/Mutation response types ──────────────────────────────────────


@strawberry.type
class UserInfo:
    github_id: str
    github_login: str
    avatar_url: str
    jti: strawberry.Private[str]


@strawberry.type
class Job:
    job_id: strawberry.ID
    status: str
    issue_url: str
    issue_title: str
    repository: str
    langsmith_url: str
    awaiting_human: bool
    current_node: str
    created_at: str
    github_comment_url: str = ""


@strawberry.input
class CreateJobInput:
    issue_url: str
    supervisor_notes: str = ""


@strawberry.type
class CreateJobResult:
    job_id: strawberry.ID
    status: str


@strawberry.type
class JobActionResult:
    status: str
    job_id: strawberry.ID


@strawberry.type
class PostCommentResult:
    ok: bool
    comment_url: str = ""


@strawberry.type
class LogoutResult:
    ok: bool


@strawberry.type
class DeleteTokenResult:
    ok: bool


# ── SSE event types (one per TypedDict in events/types.py) ────────────


@strawberry.type
class AgentSpawnedEvent:
    agent_id: str
    agent_name: str
    node: str


@strawberry.type
class AgentTokenEvent:
    agent_id: str
    token: str


@strawberry.type
class OutputTokenEvent:
    token: str
    section: str | None = None


@strawberry.type
class AgentToolCallEvent:
    agent_id: str
    tool_name: str
    input_preview: str


@strawberry.type
class AgentToolResultEvent:
    agent_id: str
    tool_name: str
    result_summary: str


@strawberry.type
class AgentDoneEvent:
    agent_id: str
    node: str


@strawberry.type
class OutputSectionDoneEvent:
    section: str


@strawberry.type
class GraphNodeCompleteEvent:
    node: str
    step: int | None = None


@strawberry.type
class GraphInterruptEvent:
    question: str
    context: str


@strawberry.type
class JobDoneEvent:
    _empty: bool | None = None


@strawberry.type
class JobFailedEvent:
    error: str


@strawberry.type
class JobKilledEvent:
    _empty: bool | None = None


@strawberry.type
class JobTimedOutEvent:
    _empty: bool | None = None


JobEvent = Annotated[
    AgentSpawnedEvent
    | AgentTokenEvent
    | OutputTokenEvent
    | AgentToolCallEvent
    | AgentToolResultEvent
    | AgentDoneEvent
    | OutputSectionDoneEvent
    | GraphNodeCompleteEvent
    | GraphInterruptEvent
    | JobDoneEvent
    | JobFailedEvent
    | JobKilledEvent
    | JobTimedOutEvent,
    strawberry.union("JobEvent"),
]

# ── Dispatch helper ───────────────────────────────────────────────────

_EVENT_MAP: dict[str, type] = {
    "agent.spawned": AgentSpawnedEvent,
    "agent.token": AgentTokenEvent,
    "output.token": OutputTokenEvent,
    "agent.tool_call": AgentToolCallEvent,
    "agent.tool_result": AgentToolResultEvent,
    "agent.done": AgentDoneEvent,
    "output.section_done": OutputSectionDoneEvent,
    "graph.node_complete": GraphNodeCompleteEvent,
    "graph.interrupt": GraphInterruptEvent,
    "job.done": JobDoneEvent,
    "job.failed": JobFailedEvent,
    "job.killed": JobKilledEvent,
    "job.timed_out": JobTimedOutEvent,
}


def event_from_dict(
    data: dict[str, str | int | bool | None],
) -> (
    AgentSpawnedEvent
    | AgentTokenEvent
    | OutputTokenEvent
    | AgentToolCallEvent
    | AgentToolResultEvent
    | AgentDoneEvent
    | OutputSectionDoneEvent
    | GraphNodeCompleteEvent
    | GraphInterruptEvent
    | JobDoneEvent
    | JobFailedEvent
    | JobKilledEvent
    | JobTimedOutEvent
    | None
):
    """Convert a Redis pub/sub JSON dict into the matching Strawberry event type."""
    event_type = str(data.get("type", ""))
    cls = _EVENT_MAP.get(event_type)
    if cls is None:
        return None
    # Strip "type" key — Strawberry types don't have it
    fields = {k: v for k, v in data.items() if k != "type"}
    return cls(**fields)
