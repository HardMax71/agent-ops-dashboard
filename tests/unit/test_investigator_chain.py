
from investigator.models import InvestigatorFinding


def test_investigator_finding_schema() -> None:
    finding = InvestigatorFinding(
        agent_name="investigator",
        summary="Test",
        hypothesis="NPE in user service",
        affected_areas=["UserService", "UserController"],
        error_messages=["NullPointerException", "getUserById", "java.lang.NullPointerException"],
        confidence=0.85,
    )
    assert finding.agent_name == "investigator"
    assert len(finding.affected_areas) == 2


def test_investigator_finding_confidence_bounds() -> None:
    finding = InvestigatorFinding(
        agent_name="investigator",
        summary="Test",
        confidence=0.0,
    )
    assert finding.confidence == 0.0
