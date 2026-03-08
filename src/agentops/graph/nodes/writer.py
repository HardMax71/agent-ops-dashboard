import httpx

from agentops.graph.state import BugTriageState, TriageReport


async def writer_node(state: BugTriageState) -> dict:  # noqa: ANN401
    """Call writer LangServe endpoint."""
    payload = {
        "input": {
            "issue_title": state.issue_title,
            "findings": [f.model_dump() for f in state.findings],
            "critic_feedback": state.critic_feedback.model_dump() if state.critic_feedback else {},
            "human_exchanges": [e.model_dump() for e in state.human_exchanges],
        }
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            "http://writer:8005/agents/writer/invoke",
            json=payload,
        )
        response.raise_for_status()
        raw = response.json()

    output = raw.get("output", {})
    report = TriageReport(
        severity=output.get("severity", "medium"),
        root_cause=output.get("root_cause", ""),
        relevant_files=output.get("relevant_files", []),
        recommended_fix=output.get("recommended_fix", ""),
        confidence=output.get("confidence", 0.5),
        github_comment=output.get("github_comment", ""),
        ticket_draft={
            "title": output.get("ticket_title", state.issue_title),
            "labels": ",".join(output.get("ticket_labels", [])),
            "assignee": output.get("ticket_assignee", ""),
        },
    )
    return {
        "report": report,
        "current_node": "writer",
        "status": "done",
    }
