import httpx

from agentops.graph.state import AgentFinding, BugTriageState


async def web_search_node(state: BugTriageState) -> dict:  # noqa: ANN401 — LangGraph node returns partial state dict
    """Call web search LangServe endpoint."""
    inv_finding = next(
        (f for f in reversed(state.findings) if f.agent_name == "investigator"), None
    )
    payload = {
        "input": {
            "issue_title": state.issue_title,
            "hypothesis": inv_finding.hypothesis if inv_finding else "",
            "keywords_for_search": inv_finding.keywords_for_search if inv_finding else [],
            "error_messages": inv_finding.error_messages if inv_finding else [],
        }
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            "http://web-search:8003/agents/web_search/invoke",
            json=payload,
        )
        response.raise_for_status()
        raw = response.json()

    output = raw.get("output") or {}
    finding = AgentFinding(
        agent_name="web_search",
        summary=output.get("summary") or "Web search complete",
        confidence=output.get("confidence") or 0.5,
    )
    return {
        "findings": state.findings + [finding],
        "current_node": "web_search",
        "iterations": state.iterations + 1,
    }
