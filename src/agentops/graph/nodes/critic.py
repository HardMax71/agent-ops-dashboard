import json

import httpx

from agentops.graph.node_results import CriticNodeResult
from agentops.graph.state import AgentFinding, BugTriageState, CriticFeedback


async def critic_node(state: BugTriageState) -> CriticNodeResult:
    """Call critic LangServe endpoint."""
    inv_finding = next(
        (f for f in reversed(state.findings) if f.agent_name == "investigator"), None
    )
    payload = {
        "input": {
            "findings": json.dumps([f.model_dump() for f in state.findings]),
            "hypothesis": inv_finding.hypothesis if inv_finding else "",
            "human_exchanges": json.dumps([e.model_dump() for e in state.human_exchanges]),
        }
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            "http://critic:8004/agents/critic/invoke",
            json=payload,
        )
        response.raise_for_status()
        raw = response.json()

    return {
        "findings": state.findings + [AgentFinding.model_validate(raw["output"])],
        "critic_feedback": CriticFeedback.model_validate(raw["output"]),
        "current_node": "critic",
        "iterations": state.iterations + 1,
    }
