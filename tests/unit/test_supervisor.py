from collections.abc import Callable

from agentops.graph.state import AgentFinding, BugTriageState, CriticFeedback, HumanExchange
from agentops.graph.supervisor import build_supervisor_context, route_from_supervisor


def test_g1_first_iteration(make_state: Callable[..., BugTriageState]) -> None:
    state = make_state(iterations=0)
    assert route_from_supervisor(state) == "investigator"


def test_g3_max_iterations(make_state: Callable[..., BugTriageState]) -> None:
    state = make_state(iterations=10, max_iterations=10, supervisor_next="investigator")
    assert route_from_supervisor(state) == "writer"


def test_g4_end_without_report(make_state: Callable[..., BugTriageState]) -> None:
    state = make_state(iterations=5, supervisor_next="end", report=None)
    assert route_from_supervisor(state) == "writer"


def test_g5_critic_rejected_redirects_to_investigator(
    make_state: Callable[..., BugTriageState],
) -> None:
    feedback = CriticFeedback(verdict="REJECTED", confidence=0.5)
    state = make_state(iterations=3, supervisor_next="writer", critic_feedback=feedback)
    assert route_from_supervisor(state) == "investigator"


def test_g5_bypassed_by_g3(make_state: Callable[..., BugTriageState]) -> None:
    feedback = CriticFeedback(verdict="REJECTED", confidence=0.5)
    state = make_state(
        iterations=10, max_iterations=10, supervisor_next="writer", critic_feedback=feedback
    )
    assert route_from_supervisor(state) == "writer"


def test_g2_too_many_human_exchanges(make_state: Callable[..., BugTriageState]) -> None:
    exchanges = [
        HumanExchange(question="Q1?", answer="A1"),
        HumanExchange(question="Q2?", answer="A2"),
    ]
    state = make_state(iterations=3, supervisor_next="human_input", human_exchanges=exchanges)
    assert route_from_supervisor(state) == "codebase_search"


def test_normal_routing_codebase(make_state: Callable[..., BugTriageState]) -> None:
    state = make_state(iterations=2, supervisor_next="codebase_search")
    assert route_from_supervisor(state) == "codebase_search"


def test_build_supervisor_context(
    make_state: Callable[..., BugTriageState],
    make_finding: Callable[..., AgentFinding],
) -> None:
    findings = [make_finding("investigator"), make_finding("codebase_search")]
    state = make_state(findings=findings, iterations=2)
    ctx = build_supervisor_context(state)
    assert ctx["findings_count"] == 2
    assert "investigator" in ctx["agent_names"]
    assert ctx["critic_verdict"] == "none"


def test_normal_routing_to_writer(make_state: Callable[..., BugTriageState]) -> None:
    state = make_state(iterations=3, supervisor_next="writer")
    assert route_from_supervisor(state) == "writer"


def test_normal_routing_to_investigator(make_state: Callable[..., BugTriageState]) -> None:
    state = make_state(iterations=3, supervisor_next="investigator")
    assert route_from_supervisor(state) == "investigator"
