import uuid
from collections import defaultdict

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

_KNOWN_SECTIONS: frozenset[str] = frozenset({"report", "comment_draft", "ticket_draft"})


def _section_from_ns(checkpoint_ns: str) -> str | None:
    """Derive the writer RunnableParallel section name from checkpoint namespace."""
    for part in checkpoint_ns.split("|"):
        name = part.split(":")[0]
        if name in _KNOWN_SECTIONS:
            return name
    return None


class LangGraphEventTransformer:
    """Stateful transformer: owns agent tracking, dispatches via match."""

    def __init__(self) -> None:
        self._agents: defaultdict[str, str] = defaultdict(str)

    def _meta(self, event: StandardStreamEvent) -> LangGraphEventMetadata:
        return event.get("metadata", {})  # type: ignore[return-value]

    def transform(self, event: StandardStreamEvent) -> list[SseEvent]:
        match event["event"]:
            case "on_chat_model_stream":
                return self._on_chat_stream(event)
            case "on_llm_stream":
                return self._on_llm_stream(event)
            case "on_tool_start":
                return self._on_tool_start(event)
            case "on_tool_end":
                return self._on_tool_end(event)
            case "on_chain_start":
                return self._on_chain_start(event)
            case "on_chain_end":
                return self._on_chain_end(event)
            case _:
                return []

    def _on_chat_stream(self, event: StandardStreamEvent) -> list[SseEvent]:
        content = event["data"]["chunk"].content
        token: str = str(content) if content else ""
        return self._emit_token(event, token)

    def _on_llm_stream(self, event: StandardStreamEvent) -> list[SseEvent]:
        token: str = event["data"]["chunk"].text
        return self._emit_token(event, token)

    def _emit_token(self, event: StandardStreamEvent, token: str) -> list[SseEvent]:
        if not token:
            return []
        meta = self._meta(event)
        node = meta.get("langgraph_node", "")
        agent_id = self._agents[node]
        if agent_id:
            return [AgentTokenEvent(type="agent.token", agent_id=agent_id, token=token)]
        section = _section_from_ns(meta.get("langgraph_checkpoint_ns", ""))
        return [OutputTokenEvent(type="output.token", token=token, section=section or node or None)]

    def _on_tool_start(self, event: StandardStreamEvent) -> list[SseEvent]:
        node = self._meta(event).get("langgraph_node", "")
        agent_id = self._agents[node]
        if not agent_id:
            return []
        return [
            AgentToolCallEvent(
                type="agent.tool_call",
                agent_id=agent_id,
                tool_name=event["name"],
                input_preview=str(event["data"].get("input", ""))[:60],
            )
        ]

    def _on_tool_end(self, event: StandardStreamEvent) -> list[SseEvent]:
        node = self._meta(event).get("langgraph_node", "")
        agent_id = self._agents[node]
        if not agent_id:
            return []
        return [
            AgentToolResultEvent(
                type="agent.tool_result",
                agent_id=agent_id,
                tool_name=event["name"],
                result_summary=str(event["data"].get("output", ""))[:120],
            )
        ]

    def _on_chain_start(self, event: StandardStreamEvent) -> list[SseEvent]:
        node = self._meta(event).get("langgraph_node", "")
        if not node:
            return []
        agent_id = str(uuid.uuid4())
        self._agents[node] = agent_id
        return [
            AgentSpawnedEvent(
                type="agent.spawned",
                agent_id=agent_id,
                agent_name=node,
                node=node,
            )
        ]

    def _on_chain_end(self, event: StandardStreamEvent) -> list[SseEvent]:
        meta = self._meta(event)
        node = meta.get("langgraph_node", "")
        agent_id = self._agents[node]
        node_complete = GraphNodeCompleteEvent(
            type="graph.node_complete",
            node=node,
            step=meta.get("langgraph_step"),
        )
        if agent_id:
            return [AgentDoneEvent(type="agent.done", agent_id=agent_id, node=node), node_complete]
        return [node_complete]
