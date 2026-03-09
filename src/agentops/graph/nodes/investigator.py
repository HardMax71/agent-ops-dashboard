import httpx

from agentops.graph.state import AgentFinding, BugTriageState


async def investigator_node(state: BugTriageState) -> dict:  # noqa: ANN401 — LangGraph node returns partial state dict
    """Call investigator LangServe endpoint."""
    payload = {
        "input": {
            "issue_url": state.issue_url,
            "issue_title": state.issue_title,
            "issue_body": state.issue_body,
            "repository": state.repository,
        }
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            "http://investigator:8001/agents/investigator/invoke",
            json=payload,
        )
        response.raise_for_status()
        raw = response.json()

    finding = AgentFinding.model_validate(raw["output"] | {"agent_name": "investigator"})
    return {
        "findings": state.findings + [finding],
        "current_node": "investigator",
        "iterations": state.iterations + 1,
    }
