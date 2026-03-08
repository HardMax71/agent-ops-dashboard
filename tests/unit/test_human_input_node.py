from agentops.graph.state import BugTriageState, HumanExchange
from agentops.tasks.triage import TIMEOUT_ANSWER


def test_bug_triage_state_hitl_fields() -> None:
    state = BugTriageState(job_id="test-123", issue_url="https://github.com/a/b/issues/1")
    assert state.awaiting_human is False
    assert state.pending_exchange is None
    assert state.human_exchanges == []


def test_human_exchange_completed() -> None:
    exchange = HumanExchange(
        question="What triggers the error?",
        answer="It happens when userId is null",
        asked_at="2024-01-01T00:00:00+00:00",
        answered_at="2024-01-01T00:01:00+00:00",
    )
    assert exchange.question == "What triggers the error?"
    assert exchange.answer == "It happens when userId is null"


def test_state_with_multiple_exchanges() -> None:
    exchanges = [
        HumanExchange(question="Q1?", answer="A1"),
        HumanExchange(question="Q2?", answer="A2"),
    ]
    state = BugTriageState(
        job_id="test-456",
        issue_url="https://github.com/a/b/issues/2",
        human_exchanges=exchanges,
    )
    assert len(state.human_exchanges) == 2
    assert state.awaiting_human is False


def test_timeout_answer_constant() -> None:
    assert len(TIMEOUT_ANSWER) > 0
    assert "[no answer provided" in TIMEOUT_ANSWER
