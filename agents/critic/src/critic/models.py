from typing import Literal

from pydantic import BaseModel, Field


class CriticVerdict(BaseModel):
    verdict: Literal["APPROVED", "REJECTED"]
    gaps: list[str] = Field(default_factory=list)
    required_evidence: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class CritiqueFinding(BaseModel):
    agent_name: str = "critic"
    summary: str
    confidence: float = Field(ge=0.0, le=1.0)
    verdict: Literal["APPROVED", "REJECTED"] = "REJECTED"
    gaps: list[str] = Field(default_factory=list)
    required_evidence: list[str] = Field(default_factory=list)
    critique: str = ""
    ready_for_report: bool = False


def map_critique_to_verdict(finding: CritiqueFinding) -> Literal["APPROVED", "REJECTED"]:
    """APPROVED + ready_for_report=True → APPROVED, else REJECTED."""
    if finding.verdict == "APPROVED" and finding.ready_for_report:
        return "APPROVED"
    return "REJECTED"
