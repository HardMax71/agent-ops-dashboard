from agentops.graph.state import AgentFinding, BugTriageState, CriticFeedback, HumanExchange, TriageReport


def test_bug_triage_state_defaults() -> None:
    state = BugTriageState(job_id="test-123", issue_url="https://github.com/a/b/issues/1")
    assert state.status == "queued"
    assert state.iterations == 0
    assert state.awaiting_human is False
    assert state.findings == []
    assert state.human_exchanges == []


def test_agent_finding_creation() -> None:
    finding = AgentFinding(
        agent_name="investigator",
        summary="Test finding",
        confidence=0.9,
        hypothesis="Something broke",
        affected_areas=["auth", "db"],
        keywords_for_search=["null", "exception"],
        error_messages=["NullPointerException"],
    )
    assert finding.agent_name == "investigator"
    assert finding.summary == "Test finding"
    assert len(finding.affected_areas) == 2


def test_human_exchange() -> None:
    exchange = HumanExchange(
        question="What is the error?",
        answer="NullPointerException",
    )
    assert exchange.question == "What is the error?"
    assert exchange.answer == "NullPointerException"


def test_triage_report() -> None:
    report = TriageReport(
        severity="high",
        root_cause="Null check missing",
        relevant_files=["src/UserService.java"],
        recommended_fix="Add null check",
        confidence=0.95,
    )
    assert report.severity == "high"
    assert report.root_cause == "Null check missing"
    assert len(report.relevant_files) == 1


def test_critic_feedback() -> None:
    feedback = CriticFeedback(
        verdict="REJECTED",
        gaps=["Missing stack trace"],
        confidence=0.7,
    )
    assert feedback.verdict == "REJECTED"
    assert len(feedback.gaps) == 1
