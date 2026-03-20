from typing import Literal, TypedDict


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
    section: str


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


type SseEvent = (
    AgentSpawnedEvent
    | AgentTokenEvent
    | OutputTokenEvent
    | AgentToolCallEvent
    | AgentToolResultEvent
    | AgentDoneEvent
    | OutputSectionDoneEvent
    | GraphNodeCompleteEvent
)

ALL_NODES = frozenset(
    {
        "investigator",
        "codebase_search",
        "web_search",
        "critic",
        "writer",
        "human_input",
    }
)

WORKER_NODES = frozenset(
    {
        "investigator",
        "codebase_search",
        "web_search",
        "critic",
        "writer",
    }
)
