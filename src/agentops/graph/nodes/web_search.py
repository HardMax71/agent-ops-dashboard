import httpx

from agentops.graph.node_results import AgentNodeResult
from agentops.graph.state import AgentFinding, BugTriageState


async def web_search_node(state: BugTriageState) -> AgentNodeResult:
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

    finding = AgentFinding.model_validate(raw["output"])
    return {
        "findings": state.findings + [finding],
        "current_node": "web_search",
        "iterations": state.iterations + 1,
    }
