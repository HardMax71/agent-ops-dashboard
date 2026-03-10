"""Tests for LangGraph event transformer."""

from unittest.mock import MagicMock

from agentops.events.transformer import LangGraphEventTransformer, _section_from_ns


class TestSectionFromNs:
    def test_report_section(self) -> None:
        assert _section_from_ns("writer:uuid1|report:uuid2") == "report"

    def test_comment_draft(self) -> None:
        assert _section_from_ns("writer:uuid1|comment_draft:uuid2") == "comment_draft"

    def test_unknown_returns_none(self) -> None:
        assert _section_from_ns("writer:uuid1|unknown:uuid2") is None

    def test_empty_returns_none(self) -> None:
        assert _section_from_ns("") is None


class TestStream:
    def test_empty_token_filtered(self) -> None:
        t = LangGraphEventTransformer()
        t._agents["investigator"] = "agent-1"
        chunk = MagicMock()
        chunk.content = ""
        event = {
            "event": "on_chat_model_stream",
            "data": {"chunk": chunk},
            "metadata": {"langgraph_node": "investigator"},
            "name": "",
        }
        assert t.transform(event) == []

    def test_agent_token(self) -> None:
        t = LangGraphEventTransformer()
        t._agents["investigator"] = "agent-1"
        chunk = MagicMock()
        chunk.content = "hello"
        event = {
            "event": "on_chat_model_stream",
            "data": {"chunk": chunk},
            "metadata": {"langgraph_node": "investigator"},
            "name": "",
        }
        result = t.transform(event)
        assert len(result) == 1
        assert result[0]["type"] == "agent.token"
        assert result[0]["token"] == "hello"

    def test_output_token_when_no_agent(self) -> None:
        t = LangGraphEventTransformer()
        chunk = MagicMock()
        chunk.content = "output"
        event = {
            "event": "on_chat_model_stream",
            "data": {"chunk": chunk},
            "metadata": {"langgraph_node": "writer", "langgraph_checkpoint_ns": ""},
            "name": "",
        }
        result = t.transform(event)
        assert len(result) == 1
        assert result[0]["type"] == "output.token"

    def test_llm_stream_uses_text(self) -> None:
        t = LangGraphEventTransformer()
        t._agents["investigator"] = "agent-1"
        chunk = MagicMock()
        chunk.text = "llm-token"
        event = {
            "event": "on_llm_stream",
            "data": {"chunk": chunk},
            "metadata": {"langgraph_node": "investigator"},
            "name": "",
        }
        result = t.transform(event)
        assert len(result) == 1
        assert result[0]["type"] == "agent.token"
        assert result[0]["token"] == "llm-token"


class TestToolStart:
    def test_with_agent(self) -> None:
        t = LangGraphEventTransformer()
        t._agents["investigator"] = "agent-1"
        event = {
            "event": "on_tool_start",
            "data": {"input": "short input"},
            "metadata": {"langgraph_node": "investigator"},
            "name": "search_tool",
        }
        result = t.transform(event)
        assert len(result) == 1
        assert result[0]["type"] == "agent.tool_call"
        assert result[0]["tool_name"] == "search_tool"

    def test_no_agent_returns_empty(self) -> None:
        t = LangGraphEventTransformer()
        event = {
            "event": "on_tool_start",
            "data": {"input": "x"},
            "metadata": {"langgraph_node": "unknown"},
            "name": "tool",
        }
        assert t.transform(event) == []

    def test_input_preview_truncated(self) -> None:
        t = LangGraphEventTransformer()
        t._agents["inv"] = "a1"
        event = {
            "event": "on_tool_start",
            "data": {"input": "a" * 200},
            "metadata": {"langgraph_node": "inv"},
            "name": "t",
        }
        result = t.transform(event)
        assert len(result[0]["input_preview"]) <= 60


class TestToolEnd:
    def test_result_summary_truncated(self) -> None:
        t = LangGraphEventTransformer()
        t._agents["inv"] = "a1"
        event = {
            "event": "on_tool_end",
            "data": {"output": "b" * 200},
            "metadata": {"langgraph_node": "inv"},
            "name": "t",
        }
        result = t.transform(event)
        assert len(result[0]["result_summary"]) <= 120


class TestChainStart:
    def test_generates_uuid(self) -> None:
        t = LangGraphEventTransformer()
        event = {
            "event": "on_chain_start",
            "data": {},
            "metadata": {"langgraph_node": "investigator"},
            "name": "",
        }
        result = t.transform(event)
        assert len(result) == 1
        assert result[0]["type"] == "agent.spawned"
        assert t._agents["investigator"]

    def test_regenerates_uuid_on_second_call(self) -> None:
        t = LangGraphEventTransformer()
        event = {
            "event": "on_chain_start",
            "data": {},
            "metadata": {"langgraph_node": "investigator"},
            "name": "",
        }
        t.transform(event)
        first_id = t._agents["investigator"]
        t.transform(event)
        assert t._agents["investigator"] != first_id


class TestChainEnd:
    def test_emits_done_and_node_complete(self) -> None:
        t = LangGraphEventTransformer()
        t._agents["investigator"] = "agent-1"
        event = {
            "event": "on_chain_end",
            "data": {},
            "metadata": {"langgraph_node": "investigator", "langgraph_step": 3},
            "name": "",
        }
        result = t.transform(event)
        types = [r["type"] for r in result]
        assert "agent.done" in types
        assert "graph.node_complete" in types


class TestTransformer:
    def test_unknown_event_returns_empty(self) -> None:
        t = LangGraphEventTransformer()
        event = {"event": "on_unknown", "data": {}, "metadata": {}, "name": ""}
        assert t.transform(event) == []

    def test_dispatches_to_handler(self) -> None:
        t = LangGraphEventTransformer()
        t._agents["inv"] = "a1"
        chunk = MagicMock()
        chunk.content = "token"
        event = {
            "event": "on_chat_model_stream",
            "data": {"chunk": chunk},
            "metadata": {"langgraph_node": "inv"},
            "name": "",
        }
        result = t.transform(event)
        assert len(result) == 1
