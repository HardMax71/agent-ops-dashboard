from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from agentops.graph.state import BugTriageState
from agentops.graph.supervisor import route_from_supervisor, supervisor_node


async def _stub_node(state: BugTriageState) -> dict:  # noqa: ANN401
    """Stub node — real implementation lives in the agent microservice."""
    return {"current_node": state.supervisor_next, "iterations": state.iterations + 1}


async def investigator_node(state: BugTriageState) -> dict:  # noqa: ANN401
    """Stub investigator node — proxies to investigator microservice in production."""
    return await _stub_node(state)


async def codebase_search_node(state: BugTriageState) -> dict:  # noqa: ANN401
    """Stub codebase_search node — proxies to codebase_search microservice in production."""
    return await _stub_node(state)


async def web_search_node(state: BugTriageState) -> dict:  # noqa: ANN401
    """Stub web_search node — proxies to web_search microservice in production."""
    return await _stub_node(state)


async def critic_node(state: BugTriageState) -> dict:  # noqa: ANN401
    """Stub critic node — proxies to critic microservice in production."""
    return await _stub_node(state)


async def writer_node(state: BugTriageState) -> dict:  # noqa: ANN401
    """Stub writer node — proxies to writer microservice in production."""
    return await _stub_node(state)


def build_graph(checkpointer: object = None) -> object:  # noqa: ANN401
    """Build and compile the full bug triage graph."""
    builder: StateGraph = StateGraph(BugTriageState)

    builder.add_node("supervisor", supervisor_node)
    builder.add_node("investigator", investigator_node)
    builder.add_node("codebase_search", codebase_search_node)
    builder.add_node("web_search", web_search_node)
    builder.add_node("critic", critic_node)
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
            "writer": "writer",
        },
    )
    builder.add_edge("investigator", "supervisor")
    builder.add_edge("codebase_search", "supervisor")
    builder.add_edge("web_search", "supervisor")
    builder.add_edge("critic", "supervisor")
    builder.add_edge("writer", END)

    return builder.compile(checkpointer=checkpointer)


async def create_graph_with_sqlite(db_path: str = "checkpoints.db") -> object:  # noqa: ANN401
    """Create graph with in-memory checkpointer for development.

    For production, use build_graph(checkpointer=AsyncPostgresSaver(...)) managed
    by the application lifespan instead.
    """
    return build_graph(checkpointer=MemorySaver())
