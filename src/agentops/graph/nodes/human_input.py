from langgraph.types import interrupt

from agentops.graph.state import BugTriageState, HumanExchange


async def human_input_node(state: BugTriageState) -> dict:  # noqa: ANN401
    """Pause the graph and ask the human a clarifying question.

    Uses LangGraph interrupt() to suspend execution.  When the graph is
    resumed (via Command or update_state), the value passed back becomes
    the return value of interrupt() and is stored as the answer.
    """
    question = state.supervisor_reasoning or "Please provide clarification."
    answer: str = interrupt({"question": question})
    exchange = HumanExchange(question=question, answer=answer)
    return {
        "human_exchanges": state.human_exchanges + [exchange],
        "awaiting_human": False,
        "current_node": "human_input",
        "iterations": state.iterations + 1,
    }
