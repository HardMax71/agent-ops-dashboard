import logging

import httpx

from agentops.graph.state import AgentFinding, BugTriageState
from agentops.index.collection import get_codebase_retriever

_logger = logging.getLogger(__name__)


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


async def codebase_search_node(state: BugTriageState) -> dict:  # noqa: ANN401 — LangGraph node returns partial state dict
    """Call codebase search LangServe endpoint with optional local index context."""
    # Retrieve local context from Chroma index if available
    local_context: list[str] = []
    if state.repository:
        retriever = get_codebase_retriever(state.repository)
        if retriever is not None:
            query = " ".join(_get_keywords(state)) or _get_hypothesis(state)
            if query:
                docs = retriever.invoke(query)
                local_context = [doc.page_content for doc in docs]
                _logger.info("Chroma returned %d docs for %s", len(docs), state.repository)

    payload = {
        "input": {
            "repository": state.repository,
            "keywords": _get_keywords(state),
            "hypothesis": _get_hypothesis(state),
            "affected_areas": _get_affected_areas(state),
            "local_context": local_context,
        }
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            "http://codebase-search:8002/agents/codebase_search/invoke",
            json=payload,
        )
        response.raise_for_status()
        raw = response.json()

    finding = AgentFinding.model_validate(raw["output"])
    return {
        "findings": state.findings + [finding],
        "current_node": "codebase_search",
        "iterations": state.iterations + 1,
    }
