from agentops.graph.state import AgentFinding, BugTriageState, CriticFeedback, HumanExchange
from agentops.graph.supervisor import build_supervisor_context, route_from_supervisor


def make_state(**kwargs: object) -> BugTriageState:
    return BugTriageState(
        job_id="test-123",
        issue_url="https://github.com/a/b/issues/1",
        **kwargs,
    )


def make_finding(agent_name: str, **kwargs: object) -> AgentFinding:
    return AgentFinding(
        agent_name=agent_name,
        summary=f"{agent_name} finding",
        confidence=0.7,
        hypothesis="test hypothesis",
        affected_areas=["bug"],
        keywords_for_search=["null"],
        error_messages=["service"],
        **kwargs,
    )


def test_g1_first_iteration() -> None:
    state = make_state(iterations=0)
    assert route_from_supervisor(state) == "investigator"


def test_g3_max_iterations() -> None:
    state = make_state(iterations=10, supervisor_next="investigator")
    assert route_from_supervisor(state) == "writer"


def test_g4_end_without_report() -> None:
    state = make_state(iterations=5, supervisor_next="end", report=None)
    assert route_from_supervisor(state) == "writer"


def test_g5_critic_rejected_redirects_to_investigator() -> None:
    state = make_state(
        iterations=3,
        supervisor_next="writer",
        critic_feedback=CriticFeedback(verdict="REJECTED"),
    )
    assert route_from_supervisor(state) == "investigator"


def test_g5_bypassed_by_g3() -> None:
    # G3 takes priority: max iterations → writer even if critic rejected
    state = make_state(
        iterations=10,
        supervisor_next="writer",
        critic_feedback=CriticFeedback(verdict="REJECTED"),
    )
    assert route_from_supervisor(state) == "writer"


def test_g2_too_many_human_exchanges() -> None:
    exchanges = [
        HumanExchange(question="Q1?", answer="A1"),
        HumanExchange(question="Q2?", answer="A2"),
    ]
    state = make_state(
        iterations=3,
        supervisor_next="human_input",
        human_exchanges=exchanges,
    )
    assert route_from_supervisor(state) == "codebase_search"


def test_normal_routing_codebase() -> None:
    state = make_state(iterations=3, supervisor_next="codebase_search")
    assert route_from_supervisor(state) == "codebase_search"


def test_build_supervisor_context() -> None:
    findings = [make_finding("investigator"), make_finding("codebase_search")]
    state = make_state(
        iterations=2,
        findings=findings,
    )
    ctx = build_supervisor_context(state)
    assert ctx["iterations"] == 2
    assert ctx["findings_count"] == 2
    assert "investigator" in ctx["agent_names"]
