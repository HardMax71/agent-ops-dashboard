from langgraph.types import interrupt

from agentops.graph.state import BugTriageState, HumanExchange


async def human_input_node(state: BugTriageState) -> dict:  # noqa: ANN401 — LangGraph node returns partial state dict
    """Pause the graph and ask the human a clarifying question.

    Uses LangGraph interrupt() to suspend execution.  When the graph is
    resumed (via Command or update_state), the value passed back becomes
    the return value of interrupt() and is stored as the answer.
    """
    pending = state.pending_exchange
    question = (
        pending.question
        if pending
        else (state.supervisor_reasoning or "Please provide clarification.")
    )
    context = pending.context if pending else ""

    answer: str = str(interrupt({"question": question, "context": context}))

    exchange = HumanExchange(
        question=question,
        context=context,
        answer=answer,
        asked_at=pending.asked_at if pending else "",
    )
    return {
        "human_exchanges": state.human_exchanges + [exchange],
        "pending_exchange": None,
        "awaiting_human": False,
        "current_node": "human_input",
        "iterations": state.iterations + 1,
    }
