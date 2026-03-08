from agentops.graph.state import AgentFinding, BugTriageState


async def investigator_node(state: BugTriageState) -> dict:  # noqa: ANN401
    """Stub investigator node — calls LangServe endpoint in Phase 2."""
    finding = AgentFinding(
        agent_name="investigator",
        summary=f"Investigating issue: {state.issue_url}",
        confidence=0.5,
        hypothesis="Needs full implementation in Phase 2",
        affected_areas=["unknown"],
        keywords_for_search=["bug", "issue"],
        error_messages=[],
    )
    return {
        "findings": [finding],
        "current_node": "investigator",
        "iterations": state.iterations + 1,
    }
