from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph

from agentops.graph.state import HumanExchange


async def check_for_interrupt(
    graph: CompiledStateGraph, config: RunnableConfig
) -> HumanExchange | None:
    """Check if the graph is suspended at a human_input interrupt.

    Returns the HumanExchange if suspended, or None if completed normally.
    Call this AFTER the astream_events loop exits.
    """
    state = await graph.aget_state(config)
    if not state.tasks:
        return None
    return state.tasks[0].interrupts[0].value
