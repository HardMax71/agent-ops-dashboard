import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../agents/codebase_search/src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../agents/web_search/src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../agents/critic/src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../agents/writer/src"))

from codebase_search.models import CodebaseFinding, RelevantFile
from critic.models import CritiqueFinding, map_critique_to_verdict
from web_search.models import WebSearchFinding, WebSearchResult
from writer.models import WriterOutput


def test_codebase_finding_model() -> None:
    finding = CodebaseFinding(
        summary="Found relevant files",
        confidence=0.9,
        relevant_files=[RelevantFile(path="src/UserService.java", snippet="src/UserService.java:45")],
    )
    assert finding.agent_name == "codebase_search"
    assert finding.summary == "Found relevant files"
    assert len(finding.relevant_files) == 1


def test_web_search_finding_model() -> None:
    finding = WebSearchFinding(
        summary="Found relevant issues",
        confidence=0.8,
        search_results=[WebSearchResult(url="https://example.com", title="Issue", snippet="...")],
    )
    assert finding.agent_name == "web_search"
    assert finding.summary == "Found relevant issues"
    assert len(finding.search_results) == 1


def test_critique_finding_model() -> None:
    finding = CritiqueFinding(
        summary="Review complete",
        verdict="APPROVED",
        ready_for_report=True,
    )
    assert finding.verdict == "APPROVED"
    assert finding.summary == "Review complete"


def test_writer_output_model() -> None:
    output = WriterOutput(
        summary="Report written",
        severity="high",
        root_cause="NPE in getUserById",
    )
    assert output.agent_name == "writer"
    assert output.severity == "high"
    assert output.root_cause == "NPE in getUserById"


def test_critic_map_verdict() -> None:
    approved = CritiqueFinding(
        summary="ok",
        verdict="APPROVED",
        ready_for_report=True,
    )
    rejected = CritiqueFinding(
        summary="not ok",
        verdict="APPROVED",
        ready_for_report=False,
    )
    assert map_critique_to_verdict(approved) == "APPROVED"
    assert map_critique_to_verdict(rejected) == "REJECTED"
