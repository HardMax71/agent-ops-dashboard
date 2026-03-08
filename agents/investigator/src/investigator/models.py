from pydantic import BaseModel, Field


class AgentFindingBase(BaseModel):
    """Base class for all agent findings."""

    agent_name: str
    summary: str
    confidence: float = Field(ge=0.0, le=1.0)


class InvestigatorFinding(AgentFindingBase):
    """Output from the investigator agent."""

    hypothesis: str
    affected_areas: list[str]
    keywords_for_search: list[str]
    error_messages: list[str]
