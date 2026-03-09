from agentops.graph.state import (
    _CURRENT_SCHEMA_VERSION,
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


def test_critic_feedback_from_dict() -> None:
    feedback = CriticFeedback.model_validate(
        {
            "agent_name": "critic",
            "summary": "Review done",
            "verdict": "REJECTED",
            "gaps": ["missing tests"],
            "confidence": 0.6,
            "critique": "needs work",
        }
    )
    assert feedback.verdict == "REJECTED"
    assert feedback.gaps == ["missing tests"]


def test_human_exchange_context_field() -> None:
    exchange = HumanExchange(
        question="What is the error?",
        context="Occurs during login flow",
        answer="NullPointerException",
    )
    assert exchange.context == "Occurs during login flow"


def test_human_exchange_context_default() -> None:
    exchange = HumanExchange(question="What is the error?")
    assert exchange.context == ""


def test_redirect_instructions_field() -> None:
    state = BugTriageState(
        job_id="test-123",
        issue_url="https://github.com/a/b/issues/1",
        redirect_instructions=["focus on auth", "check DB"],
    )
    assert len(state.redirect_instructions) == 2
    assert state.redirect_instructions[0] == "focus on auth"


def test_redirect_instructions_default() -> None:
    state = BugTriageState(
        job_id="test-123",
        issue_url="https://github.com/a/b/issues/1",
    )
    assert state.redirect_instructions == []


def test_timed_out_is_valid_status() -> None:
    state = BugTriageState(
        job_id="test-123",
        issue_url="https://github.com/a/b/issues/1",
        status="timed_out",
    )
    assert state.status == "timed_out"


def test_schema_version_set_on_construction() -> None:
    state = BugTriageState(
        job_id="test-123",
        issue_url="https://github.com/a/b/issues/1",
    )
    assert state.schema_version == _CURRENT_SCHEMA_VERSION


def test_schema_version_migrated_from_old_checkpoint() -> None:
    """Old checkpoints without schema_version get migrated to current version."""
    state = BugTriageState.model_validate(
        {
            "job_id": "test-123",
            "issue_url": "https://github.com/a/b/issues/1",
        }
    )
    assert state.schema_version == _CURRENT_SCHEMA_VERSION
