"""Tests for LangGraph event transformer."""

from unittest.mock import MagicMock

from agentops.events.transformer import (
    LangGraphEventTransformer,
    _handle_chain_end,
    _handle_chain_start,
    _handle_stream,
    _handle_tool_end,
    _handle_tool_start,
    _section_from_ns,
)


class TestSectionFromNs:
    def test_report_section(self) -> None:
        assert _section_from_ns("writer:uuid1|report:uuid2") == "report"

    def test_comment_draft(self) -> None:
        assert _section_from_ns("writer:uuid1|comment_draft:uuid2") == "comment_draft"

    def test_unknown_returns_none(self) -> None:
        assert _section_from_ns("writer:uuid1|unknown:uuid2") is None

    def test_empty_returns_none(self) -> None:
        assert _section_from_ns("") is None


class TestHandleStream:
    def test_empty_token_filtered(self) -> None:
        chunk = MagicMock()
        chunk.text = ""
        event = {
            "event": "on_chat_model_stream",
            "data": {"chunk": chunk},
            "metadata": {"langgraph_node": "investigator"},
            "name": "",
        }
        result = _handle_stream(event, {"investigator": "agent-1"})
        assert result == []

    def test_agent_token(self) -> None:
        chunk = MagicMock()
        chunk.text = "hello"
        event = {
            "event": "on_chat_model_stream",
            "data": {"chunk": chunk},
            "metadata": {"langgraph_node": "investigator"},
            "name": "",
        }
        result = _handle_stream(event, {"investigator": "agent-1"})
        assert len(result) == 1
        assert result[0]["type"] == "agent.token"
        assert result[0]["token"] == "hello"

    def test_output_token_when_no_agent(self) -> None:
        chunk = MagicMock()
        chunk.text = "output"
        event = {
            "event": "on_chat_model_stream",
            "data": {"chunk": chunk},
            "metadata": {"langgraph_node": "writer", "langgraph_checkpoint_ns": ""},
            "name": "",
        }
        result = _handle_stream(event, {})
        assert len(result) == 1
        assert result[0]["type"] == "output.token"


class TestHandleToolStart:
    def test_with_agent(self) -> None:
        event = {
            "event": "on_tool_start",
            "data": {"input": "short input"},
            "metadata": {"langgraph_node": "investigator"},
            "name": "search_tool",
        }
        result = _handle_tool_start(event, {"investigator": "agent-1"})
        assert len(result) == 1
        assert result[0]["type"] == "agent.tool_call"
        assert result[0]["tool_name"] == "search_tool"

    def test_no_agent_returns_empty(self) -> None:
        event = {
            "event": "on_tool_start",
            "data": {"input": "x"},
            "metadata": {"langgraph_node": "unknown"},
            "name": "tool",
        }
        assert _handle_tool_start(event, {}) == []

    def test_input_preview_truncated(self) -> None:
        event = {
            "event": "on_tool_start",
            "data": {"input": "a" * 200},
            "metadata": {"langgraph_node": "inv"},
            "name": "t",
        }
        result = _handle_tool_start(event, {"inv": "a1"})
        assert len(result[0]["input_preview"]) <= 60


class TestHandleToolEnd:
    def test_result_summary_truncated(self) -> None:
        event = {
            "event": "on_tool_end",
            "data": {"output": "b" * 200},
            "metadata": {"langgraph_node": "inv"},
            "name": "t",
        }
        result = _handle_tool_end(event, {"inv": "a1"})
        assert len(result[0]["result_summary"]) <= 120


class TestHandleChainStart:
    def test_generates_uuid(self) -> None:
        spawned: dict[str, str] = {}
        event = {
            "event": "on_chain_start",
            "data": {},
            "metadata": {"langgraph_node": "investigator"},
            "name": "",
        }
        result = _handle_chain_start(event, spawned)
        assert len(result) == 1
        assert result[0]["type"] == "agent.spawned"
        assert "investigator" in spawned

    def test_regenerates_uuid_on_second_call(self) -> None:
        spawned: dict[str, str] = {}
        event = {
            "event": "on_chain_start",
            "data": {},
            "metadata": {"langgraph_node": "investigator"},
            "name": "",
        }
        _handle_chain_start(event, spawned)
        first_id = spawned["investigator"]
        _handle_chain_start(event, spawned)
        assert spawned["investigator"] != first_id


class TestHandleChainEnd:
    def test_emits_done_and_node_complete(self) -> None:
        event = {
            "event": "on_chain_end",
            "data": {},
            "metadata": {"langgraph_node": "investigator", "langgraph_step": 3},
            "name": "",
        }
        result = _handle_chain_end(event, {"investigator": "agent-1"})
        types = [r["type"] for r in result]
        assert "agent.done" in types
        assert "graph.node_complete" in types


class TestTransformer:
    def test_unknown_event_returns_empty(self) -> None:
        transformer = LangGraphEventTransformer()
        event = {"event": "on_unknown", "data": {}, "metadata": {}, "name": ""}
        assert transformer.transform(event, {}) == []

    def test_dispatches_to_handler(self) -> None:
        chunk = MagicMock()
        chunk.text = "token"
        event = {
            "event": "on_chat_model_stream",
            "data": {"chunk": chunk},
            "metadata": {"langgraph_node": "inv"},
            "name": "",
        }
        transformer = LangGraphEventTransformer()
        result = transformer.transform(event, {"inv": "a1"})
        assert len(result) == 1
