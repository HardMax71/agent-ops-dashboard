from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph

from agentops.graph.nodes.investigator import investigator_node
from agentops.graph.nodes.writer import writer_node
from agentops.graph.state import BugTriageState
from agentops.graph.supervisor import route_from_supervisor, supervisor_node


def build_graph(checkpointer: object = None) -> object:  # noqa: ANN401
    """Build and compile the bug triage graph."""
    builder: StateGraph = StateGraph(BugTriageState)

    builder.add_node("supervisor", supervisor_node)
    builder.add_node("investigator", investigator_node)
    builder.add_node("writer", writer_node)

    builder.add_edge(START, "supervisor")
    builder.add_conditional_edges(
        "supervisor",
        route_from_supervisor,
        {
            "investigator": "investigator",
            "writer": "writer",
        },
    )
    builder.add_edge("investigator", "supervisor")
    builder.add_edge("writer", END)

    return builder.compile(checkpointer=checkpointer)


async def create_graph_with_sqlite(db_path: str = "checkpoints.db") -> object:  # noqa: ANN401
    """Create graph with SQLite checkpointer for development."""
    async with AsyncSqliteSaver.from_conn_string(db_path) as checkpointer:
        return build_graph(checkpointer=checkpointer)
