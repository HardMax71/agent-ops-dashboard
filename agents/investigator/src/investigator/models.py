from pydantic import BaseModel, Field


class AgentFindingBase(BaseModel):
    """Base class for all agent findings."""

    agent_name: str
    summary: str
    confidence: float = 0.0


class InvestigatorFinding(AgentFindingBase):
    """Output from the investigator agent."""

    agent_name: str = "investigator"
    hypothesis: str = ""
    affected_areas: list[str] = Field(default_factory=list)
    keywords_for_search: list[str] = Field(default_factory=list)
    error_messages: list[str] = Field(default_factory=list)
