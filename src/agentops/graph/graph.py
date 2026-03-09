from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from agentops.graph.nodes.codebase_search import codebase_search_node
from agentops.graph.nodes.critic import critic_node
from agentops.graph.nodes.human_input import human_input_node
from agentops.graph.nodes.investigator import investigator_node
from agentops.graph.nodes.web_search import web_search_node
from agentops.graph.nodes.writer import writer_node
from agentops.graph.state import BugTriageState
from agentops.graph.supervisor import route_from_supervisor, supervisor_node


def build_graph(checkpointer: BaseCheckpointSaver | None = None) -> CompiledStateGraph:
    """Build and compile the full bug triage graph."""
    builder: StateGraph = StateGraph(BugTriageState)

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
        },
    )
    builder.add_edge("investigator", "supervisor")
    builder.add_edge("codebase_search", "supervisor")
    builder.add_edge("web_search", "supervisor")
    builder.add_edge("critic", "supervisor")
    builder.add_edge("human_input", "supervisor")
    builder.add_edge("writer", END)

    return builder.compile(checkpointer=checkpointer)


def create_graph_in_memory() -> CompiledStateGraph:
    """Create graph with in-memory checkpointer for development.

    For production, use build_graph(checkpointer=AsyncPostgresSaver(...)) managed
    by the application lifespan instead.
    """
    return build_graph(checkpointer=MemorySaver())


async def create_graph_with_postgres(conninfo: str) -> CompiledStateGraph:
    """Create graph with PostgreSQL-backed checkpointer for production."""
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    saver = AsyncPostgresSaver.from_conn_string(conninfo)
    await saver.setup()
    return build_graph(checkpointer=saver)
