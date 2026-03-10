from unittest.mock import patch

import pytest

from agentops.graph.nodes.human_input import human_input_node
from agentops.graph.state import BugTriageState, HumanExchange


@pytest.fixture
def base_state():
    return BugTriageState(
        job_id="test-1",
        issue_url="https://github.com/a/b/issues/1",
        iterations=2,
        supervisor_reasoning="What is the error message?",
    )


async def test_uses_pending_exchange(base_state):
    pending = HumanExchange(
        question="Can you reproduce?",
        context="The bug happens on login",
        asked_at="2026-01-01T00:00:00Z",
    )
    base_state.pending_exchange = pending

    with patch("agentops.graph.nodes.human_input.interrupt", return_value="Yes I can"):
        result = await human_input_node(base_state)

    assert result["pending_exchange"] is None
    assert result["awaiting_human"] is False
    exchanges = result["human_exchanges"]
    assert len(exchanges) == 1
    assert exchanges[0].question == "Can you reproduce?"
    assert exchanges[0].context == "The bug happens on login"
    assert exchanges[0].answer == "Yes I can"
    assert exchanges[0].asked_at == "2026-01-01T00:00:00Z"


async def test_falls_back_to_supervisor_reasoning(base_state):
    with patch("agentops.graph.nodes.human_input.interrupt", return_value="NullPointerException"):
        result = await human_input_node(base_state)

    exchanges = result["human_exchanges"]
    assert len(exchanges) == 1
    assert exchanges[0].question == "What is the error message?"
    assert exchanges[0].context == ""
    assert exchanges[0].answer == "NullPointerException"


async def test_falls_back_to_default_question():
    state = BugTriageState(
        job_id="test-2",
        issue_url="https://github.com/a/b/issues/2",
        iterations=0,
        supervisor_reasoning="",
    )
    with patch("agentops.graph.nodes.human_input.interrupt", return_value="Sure"):
        result = await human_input_node(state)

    exchanges = result["human_exchanges"]
    assert exchanges[0].question == "Please provide clarification."
