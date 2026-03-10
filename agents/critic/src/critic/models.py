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
