from agentops.graph.state import BugTriageState


def route_from_supervisor(state: BugTriageState) -> str:
    """Route based on supervisor decision with 5 guards."""
    # G1: First iteration always goes to investigator
    if state.iterations == 0:
        return "investigator"

    # G3: Max iterations reached → force writer
    if state.iterations >= state.max_iterations:
        return "writer"

    # G4: No report yet and supervisor says end → force writer
    if state.supervisor_next == "end" and state.report is None:
        return "writer"

    # G5: Critic rejected and supervisor wants writer → re-investigate (bypassed by G3)
    if (
        state.critic_feedback is not None
        and state.critic_feedback.verdict == "REJECTED"
        and state.supervisor_next == "writer"
        and state.iterations < state.max_iterations
    ):
        return "investigator"

    # G2: Too many human exchanges, force forward
    if len(state.human_exchanges) >= 2 and state.supervisor_next == "human_input":
        return "writer"

    next_node = state.supervisor_next
    valid_nodes = (
        "investigator", "codebase_search", "web_search", "critic", "human_input", "writer"
    )
    if next_node in valid_nodes:
        return next_node
    return "writer"


async def supervisor_node(state: BugTriageState) -> dict:  # noqa: ANN401
    """Stub supervisor — full implementation in Phase 2."""
    # Phase 1: simple fixed routing
    if state.iterations == 0:
        next_node = "investigator"
    elif state.findings:
        next_node = "writer"
    else:
        next_node = "writer"

    return {
        "supervisor_next": next_node,
        "supervisor_confidence": 0.8,
        "supervisor_reasoning": "Phase 1 stub routing",
    }
