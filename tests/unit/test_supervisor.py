from collections.abc import Callable
from unittest.mock import patch

import pytest

from agentops.graph.state import AgentFinding, BugTriageState, CriticFeedback, HumanExchange
from agentops.graph.supervisor import (
    build_supervisor_context,
    route_from_supervisor,
    supervisor_node,
)


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


def test_redirect_instructions_in_context(make_state):
    state = make_state(
        iterations=2,
        redirect_instructions=["focus on auth", "check DB layer"],
    )
    ctx = build_supervisor_context(state)
    block = ctx["redirect_instructions_block"]
    assert "1. focus on auth" in block
    assert "2. check DB layer" in block
    assert "Active redirect instructions" in block


def test_empty_redirect_instructions(make_state):
    state = make_state(iterations=2)
    ctx = build_supervisor_context(state)
    assert ctx["redirect_instructions_block"] == ""


async def test_pause_fires_interrupt(make_state):
    state = make_state(iterations=2, paused=True)
    with patch("agentops.graph.supervisor.interrupt") as mock_interrupt:
        mock_interrupt.side_effect = Exception("interrupt fired")
        with pytest.raises(Exception, match="interrupt fired"):
            await supervisor_node(state)
        mock_interrupt.assert_called_once_with("manual_pause")


async def test_pending_exchange_set_on_human_input(make_state):
    from agentops.graph.supervisor import SupervisorDecision

    decision = SupervisorDecision(
        next_node="human_input",
        reasoning="Need more info",
        confidence=0.8,
        question="What error do you see?",
        question_context="Login page returns 500",
    )

    state = make_state(iterations=2)

    with patch("agentops.graph.supervisor._invoke_supervisor", return_value=decision):
        with patch("agentops.graph.supervisor.ChatOpenAI"):
            result = await supervisor_node(state)

    assert result["awaiting_human"] is True
    assert result["pending_exchange"].question == "What error do you see?"
    assert result["pending_exchange"].context == "Login page returns 500"


async def test_no_pending_exchange_for_other_nodes(make_state):
    from agentops.graph.supervisor import SupervisorDecision

    decision = SupervisorDecision(
        next_node="investigator",
        reasoning="Investigate further",
        confidence=0.9,
    )

    state = make_state(iterations=2)

    with patch("agentops.graph.supervisor._invoke_supervisor", return_value=decision):
        with patch("agentops.graph.supervisor.ChatOpenAI"):
            result = await supervisor_node(state)

    assert "pending_exchange" not in result
    assert "awaiting_human" not in result
