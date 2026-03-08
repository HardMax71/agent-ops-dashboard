import httpx

from agentops.graph.state import AgentFinding, BugTriageState


def _get_keywords(state: BugTriageState) -> list[str]:
    for finding in reversed(state.findings):
        if finding.keywords_for_search:
            return finding.keywords_for_search
    return []


def _get_hypothesis(state: BugTriageState) -> str:
    for finding in reversed(state.findings):
        if finding.hypothesis:
            return finding.hypothesis
    return ""


def _get_affected_areas(state: BugTriageState) -> list[str]:
    for finding in reversed(state.findings):
        if finding.affected_areas:
            return finding.affected_areas
    return []


async def codebase_search_node(state: BugTriageState) -> dict:  # noqa: ANN401
    """Call codebase search LangServe endpoint."""
    payload = {
        "input": {
            "repository": state.repository,
            "keywords": _get_keywords(state),
            "hypothesis": _get_hypothesis(state),
            "affected_areas": _get_affected_areas(state),
        }
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            "http://codebase-search:8002/agents/codebase_search/invoke",
            json=payload,
        )
        response.raise_for_status()
        raw = response.json()

    output = raw.get("output", {})
    relevant_files = [f.get("path", "") for f in output.get("relevant_files", [])]
    finding = AgentFinding(
        agent_name="codebase_search",
        summary=output.get("summary", "Codebase search complete"),
        confidence=output.get("confidence", 0.5),
        relevant_files=relevant_files,
        root_cause_location=output.get("root_cause_location", ""),
    )
    return {
        "findings": state.findings + [finding],
        "current_node": "codebase_search",
        "iterations": state.iterations + 1,
    }
