import uuid
from collections.abc import Callable

from langchain_core.runnables.schema import StandardStreamEvent

from agentops.events.types import (
    AgentDoneEvent,
    AgentSpawnedEvent,
    AgentTokenEvent,
    AgentToolCallEvent,
    AgentToolResultEvent,
    GraphNodeCompleteEvent,
    LangGraphEventMetadata,
    OutputTokenEvent,
    SseEvent,
)

type _EventHandler = Callable[[StandardStreamEvent, dict[str, str]], list[SseEvent]]


def _meta(event: StandardStreamEvent) -> LangGraphEventMetadata:
    return event.get("metadata", {})  # type: ignore[return-value]


def _section_from_ns(checkpoint_ns: str) -> str | None:
    """Derive the writer RunnableParallel section name from checkpoint namespace."""
    known_sections = {"report", "comment_draft", "ticket_draft"}
    for part in checkpoint_ns.split("|"):
        name = part.split(":")[0]
        if name in known_sections:
            return name
    return None


def _handle_stream(event: StandardStreamEvent, spawned_agents: dict[str, str]) -> list[SseEvent]:
    meta = _meta(event)
    node = meta.get("langgraph_node", "")
    agent_id = spawned_agents.get(node, "")
    chunk = event["data"]["chunk"]
    token: str = chunk.text
    if not token:
        return []
    if agent_id:
        return [AgentTokenEvent(type="agent.token", agent_id=agent_id, token=token)]
    section = _section_from_ns(meta.get("langgraph_checkpoint_ns", ""))
    return [OutputTokenEvent(type="output.token", token=token, section=section or node or None)]


def _handle_tool_start(
    event: StandardStreamEvent, spawned_agents: dict[str, str]
) -> list[SseEvent]:
    meta = _meta(event)
    node = meta.get("langgraph_node", "")
    agent_id = spawned_agents.get(node, "")
    if not agent_id:
        return []
    tool_name: str = event["name"]
    input_preview = str(event["data"].get("input", ""))[:60]
    return [
        AgentToolCallEvent(
            type="agent.tool_call",
            agent_id=agent_id,
            tool_name=tool_name,
            input_preview=input_preview,
        )
    ]


def _handle_tool_end(event: StandardStreamEvent, spawned_agents: dict[str, str]) -> list[SseEvent]:
    meta = _meta(event)
    node = meta.get("langgraph_node", "")
    agent_id = spawned_agents.get(node, "")
    if not agent_id:
        return []
    tool_name: str = event["name"]
    result_summary = str(event["data"].get("output", ""))[:120]
    return [
        AgentToolResultEvent(
            type="agent.tool_result",
            agent_id=agent_id,
            tool_name=tool_name,
            result_summary=result_summary,
        )
    ]


def _handle_chain_start(
    event: StandardStreamEvent, spawned_agents: dict[str, str]
) -> list[SseEvent]:
    meta = _meta(event)
    node = meta.get("langgraph_node", "")
    if not node:
        return []
    agent_id = str(uuid.uuid4())
    spawned_agents[node] = agent_id
    return [
        AgentSpawnedEvent(
            type="agent.spawned",
            agent_id=agent_id,
            agent_name=node,
            node=node,
        )
    ]


def _handle_chain_end(event: StandardStreamEvent, spawned_agents: dict[str, str]) -> list[SseEvent]:
    meta = _meta(event)
    node = meta.get("langgraph_node", "")
    step = meta.get("langgraph_step")
    agent_id = spawned_agents.get(node, "")
    results: list[SseEvent] = []
    if agent_id:
        results.append(AgentDoneEvent(type="agent.done", agent_id=agent_id, node=node))
    results.append(GraphNodeCompleteEvent(type="graph.node_complete", node=node, step=step))
    return results


_DEFAULT_HANDLERS: dict[str, _EventHandler] = {
    "on_chat_model_stream": _handle_stream,
    "on_llm_stream": _handle_stream,
    "on_tool_start": _handle_tool_start,
    "on_tool_end": _handle_tool_end,
    "on_chain_start": _handle_chain_start,
    "on_chain_end": _handle_chain_end,
}


class LangGraphEventTransformer:
    """Transforms LangGraph stream events to SSE events via dispatch table."""

    def __init__(self, handlers: dict[str, _EventHandler] | None = None) -> None:
        self._handlers = handlers or _DEFAULT_HANDLERS

    def transform(
        self,
        event: StandardStreamEvent,
        spawned_agents: dict[str, str],
    ) -> list[SseEvent]:
        handler = self._handlers.get(event["event"])
        return handler(event, spawned_agents) if handler is not None else []
