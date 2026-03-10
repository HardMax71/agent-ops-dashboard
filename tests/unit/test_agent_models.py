from codebase_search.models import CodebaseFinding
from critic.models import CritiqueFinding
from web_search.models import WebSearchFinding, WebSearchResult
from writer.models import WriterOutput


def test_codebase_finding_model() -> None:
    finding = CodebaseFinding(
        summary="Found relevant files",
        confidence=0.8,
        relevant_files=["src/UserService.java"],
        root_cause_location="src/UserService.java:45",
    )
    assert finding.agent_name == "codebase_search"
    assert len(finding.relevant_files) == 1


def test_web_search_finding_model() -> None:
    finding = WebSearchFinding(
        summary="Found relevant issues",
        confidence=0.7,
        search_results=[WebSearchResult(url="https://example.com", title="Issue", snippet="...")],
    )
    assert finding.agent_name == "web_search"


def test_critique_finding_model() -> None:
    finding = CritiqueFinding(
        summary="Review complete",
        confidence=0.9,
        verdict="APPROVED",
    )
    assert finding.verdict == "APPROVED"


def test_writer_output_model() -> None:
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
