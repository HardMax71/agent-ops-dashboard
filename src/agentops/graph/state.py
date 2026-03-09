from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

_CURRENT_SCHEMA_VERSION = 1


class AgentFinding(BaseModel):
    """Finding produced by an agent node."""

    agent_name: str
    summary: str
    confidence: float = Field(ge=0.0, le=1.0)
    hypothesis: str = ""
    affected_areas: list[str] = Field(default_factory=list)
    keywords_for_search: list[str] = Field(default_factory=list)
    error_messages: list[str] = Field(default_factory=list)
    relevant_files: list[str] = Field(default_factory=list)
    root_cause_location: str = ""
    verdict: str = ""
    gaps: list[str] = Field(default_factory=list)


class HumanExchange(BaseModel):
    """A completed Q&A exchange with a human."""

    question: str
    context: str = ""
    answer: str = ""
    asked_at: str = ""
    answered_at: str = ""


class TriageReport(BaseModel):
    """Final triage report produced by the writer agent."""

    severity: Literal["critical", "high", "medium", "low"] = "medium"
    root_cause: str = ""
    relevant_files: list[str] = Field(default_factory=list)
    recommended_fix: str = ""
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    github_comment: str = ""
    ticket_title: str = ""
    ticket_labels: list[str] = Field(default_factory=list)
    ticket_assignee: str = ""


class CriticFeedback(BaseModel):
    """Feedback from the critic agent."""

    verdict: Literal["APPROVED", "REJECTED"] = "REJECTED"
    gaps: list[str] = Field(default_factory=list)
    required_evidence: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)


class BugTriageState(BaseModel):
    """Full state for the bug triage graph."""

    schema_version: int = Field(default=0)

    # Job identification
    job_id: str

    @model_validator(mode="before")
    @classmethod
    def migrate_from_checkpoint(cls, data: dict[str, object]) -> dict[str, object]:  # noqa: ANN401
        """Set schema_version to current when loading old checkpoints."""
        data["schema_version"] = _CURRENT_SCHEMA_VERSION
        return data

    issue_url: str
    issue_title: str = ""
    issue_body: str = ""
    repository: str = ""
    owner_id: str = ""

    # Orchestration
    status: Literal[
        "queued", "running", "waiting", "paused", "done", "failed", "killed", "timed_out"
    ] = "queued"
    current_node: str = ""
    iterations: int = 0
    max_iterations: int = 10
    paused: bool = False
    awaiting_human: bool = False

    # Supervisor
    supervisor_confidence: float = 0.0
    supervisor_next: str = ""
    supervisor_reasoning: str = ""

    # Agent outputs
    findings: list[AgentFinding] = Field(default_factory=list)
    critic_feedback: CriticFeedback | None = None

    # HITL
    human_exchanges: list[HumanExchange] = Field(default_factory=list)
    pending_exchange: HumanExchange | None = None

    # Cost tracking
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    cost_budget_usd: float = 0.20
    per_agent_cost: dict[str, float] = Field(default_factory=dict)

    # Output
    report: TriageReport | None = None
    langsmith_run_id: str = ""
    langsmith_url: str = ""

    # Supervisor notes from user
    supervisor_notes: str = ""

    # Redirect instructions from user
    redirect_instructions: list[str] = Field(default_factory=list)
