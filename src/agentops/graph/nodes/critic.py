import httpx

from agentops.graph.state import AgentFinding, BugTriageState, CriticFeedback


async def critic_node(state: BugTriageState) -> dict:  # noqa: ANN401 — LangGraph node returns partial state dict
    """Call critic LangServe endpoint."""
    inv_finding = next(
        (f for f in reversed(state.findings) if f.agent_name == "investigator"), None
    )
    payload = {
        "input": {
            "findings": [f.model_dump() for f in state.findings],
            "hypothesis": inv_finding.hypothesis if inv_finding else "",
            "human_exchanges": [e.model_dump() for e in state.human_exchanges],
        }
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            "http://critic:8004/agents/critic/invoke",
            json=payload,
        )
        response.raise_for_status()
        raw = response.json()

    output = raw.get("output", {})
    feedback = CriticFeedback(
        verdict=output.get("verdict", "REJECTED"),
        gaps=output.get("gaps", []),
        required_evidence=output.get("required_evidence", []),
        confidence=output.get("confidence", 0.5),
    )
    finding = AgentFinding(
        agent_name="critic",
        summary=output.get("summary", "Critique complete"),
        confidence=output.get("confidence", 0.5),
        verdict=output.get("verdict", "REJECTED"),
        gaps=output.get("gaps", []),
    )
    return {
        "findings": state.findings + [finding],
        "critic_feedback": feedback,
        "current_node": "critic",
        "iterations": state.iterations + 1,
    }
