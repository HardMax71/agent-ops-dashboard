import os
import sys

# Add agent source paths for testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../agents/codebase_search/src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../agents/web_search/src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../agents/critic/src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../agents/writer/src"))


def test_codebase_finding_model() -> None:
    from codebase_search.models import CodebaseFinding, RelevantFile

    finding = CodebaseFinding(
        summary="Found relevant files",
        confidence=0.8,
        relevant_files=[RelevantFile(path="src/UserService.java", relevance_score=0.9)],
        root_cause_location="src/UserService.java:45",
    )
    assert finding.agent_name == "codebase_search"
    assert len(finding.relevant_files) == 1


def test_web_search_finding_model() -> None:
    from web_search.models import WebSearchFinding, WebSearchResult

    finding = WebSearchFinding(
        summary="Found relevant issues",
        confidence=0.7,
        search_results=[WebSearchResult(url="https://example.com", title="Issue", snippet="...")],
    )
    assert finding.agent_name == "web_search"


def test_critique_finding_model() -> None:
    from critic.models import CritiqueFinding

    finding = CritiqueFinding(
        summary="Review complete",
        confidence=0.9,
        verdict="APPROVED",
        ready_for_report=True,
    )
    assert finding.verdict == "APPROVED"
    assert finding.ready_for_report is True


def test_writer_output_model() -> None:
    from writer.models import WriterOutput

    output = WriterOutput(
        summary="Report written",
        confidence=0.85,
        severity="high",
        root_cause="NPE in getUserById",
        relevant_files=["src/UserService.java"],
        recommended_fix="Add null check",
        github_comment="Bug triaged: high severity NPE",
    )
    assert output.severity == "high"
    assert output.agent_name == "writer"


def test_critic_map_verdict() -> None:
    from critic.models import CritiqueFinding, map_critique_to_verdict

    approved = CritiqueFinding(
        summary="Approved",
        confidence=0.9,
        verdict="APPROVED",
        ready_for_report=True,
    )
    assert map_critique_to_verdict(approved) == "APPROVED"

    not_ready = CritiqueFinding(
        summary="Not ready",
        confidence=0.5,
        verdict="APPROVED",
        ready_for_report=False,
    )
    assert map_critique_to_verdict(not_ready) == "REJECTED"
