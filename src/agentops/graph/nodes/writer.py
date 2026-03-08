from agentops.graph.state import BugTriageState, TriageReport


async def writer_node(state: BugTriageState) -> dict:  # noqa: ANN401
    """Stub writer node — full implementation in Phase 2."""
    report = TriageReport(
        severity="medium",
        root_cause="Analysis pending full implementation",
        relevant_files=[],
        recommended_fix="See agent findings",
        confidence=0.5,
        github_comment="Bug triage complete. See full report.",
        ticket_draft={"title": state.issue_title or "Bug triage", "labels": "bug"},
    )
    return {
        "report": report,
        "current_node": "writer",
        "status": "done",
    }
