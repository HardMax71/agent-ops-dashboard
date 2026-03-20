import json

import httpx

from agentops.graph.node_results import WriterNodeResult
from agentops.graph.state import BugTriageState, TriageReport


async def writer_node(state: BugTriageState) -> WriterNodeResult:
    """Call writer LangServe endpoint."""
    payload = {
        "input": {
            "issue_title": state.issue_title,
            "findings": json.dumps([f.model_dump() for f in state.findings]),
            "critic_feedback": json.dumps(
                state.critic_feedback.model_dump() if state.critic_feedback else {}
            ),
            "human_exchanges": json.dumps([e.model_dump() for e in state.human_exchanges]),
        }
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            "http://writer:8005/agents/writer/invoke",
            json=payload,
        )
        response.raise_for_status()
        raw = response.json()

    report = TriageReport.model_validate(raw["output"])
    report.ticket_title = report.ticket_title or state.issue_title
    return {
        "report": report,
        "current_node": "writer",
        "status": "done",
    }
