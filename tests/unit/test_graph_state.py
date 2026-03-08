from agentops.graph.state import (
    AgentFinding,
    BugTriageState,
    CriticFeedback,
    HumanExchange,
    TriageReport,
)


def test_bug_triage_state_defaults() -> None:
    state = BugTriageState(job_id="test-123", issue_url="https://github.com/a/b/issues/1")
    assert state.status == "queued"
    assert state.iterations == 0
    assert state.findings == []
    assert state.human_exchanges == []
    assert state.report is None
    assert state.paused is False
    assert state.awaiting_human is False


def test_agent_finding_creation() -> None:
    finding = AgentFinding(
        agent_name="investigator",
        summary="Test finding",
        confidence=0.8,
        hypothesis="Something broke",
        affected_areas=["auth", "db"],
        keywords_for_search=["null", "exception"],
        error_messages=["NullPointerException"],
    )
    assert finding.agent_name == "investigator"
    assert finding.confidence == 0.8
    assert len(finding.affected_areas) == 2


def test_human_exchange() -> None:
    exchange = HumanExchange(question="What is the error?", answer="NullPointerException")
    assert exchange.question == "What is the error?"
    assert exchange.answer == "NullPointerException"


def test_triage_report() -> None:
    report = TriageReport(
        severity="high",
        root_cause="Null check missing",
        relevant_files=["src/UserService.java"],
        recommended_fix="Add null check",
        confidence=0.9,
    )
    assert report.severity == "high"
    assert report.confidence == 0.9


def test_critic_feedback() -> None:
    feedback = CriticFeedback(
        verdict="APPROVED",
        gaps=[],
        required_evidence=[],
        confidence=0.95,
    )
    assert feedback.verdict == "APPROVED"
