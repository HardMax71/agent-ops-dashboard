import pytest
from pydantic import ValidationError

from agents.investigator.src.investigator.models import InvestigatorFinding


def test_investigator_finding_schema() -> None:
    finding = InvestigatorFinding(
        agent_name="investigator",
        summary="Test",
        confidence=0.7,
        hypothesis="NPE in user service",
        affected_areas=["UserService", "UserController"],
        keywords_for_search=["NullPointerException", "getUserById"],
        error_messages=["java.lang.NullPointerException"],
    )
    assert finding.hypothesis == "NPE in user service"
    assert len(finding.affected_areas) == 2
    assert len(finding.keywords_for_search) == 2


def test_investigator_finding_confidence_bounds() -> None:
    with pytest.raises(ValidationError):
        InvestigatorFinding(
            agent_name="investigator",
            summary="Test",
            confidence=1.5,  # out of range
            hypothesis="test",
            affected_areas=[],
            keywords_for_search=[],
            error_messages=[],
        )
