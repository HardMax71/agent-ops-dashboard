from typing import Literal

from pydantic import BaseModel, Field


class WriterOutput(BaseModel):
    agent_name: str = "writer"
    summary: str
    confidence: float = 0.0
    severity: Literal["critical", "high", "medium", "low"] = "medium"
    root_cause: str = ""
    relevant_files: list[str] = Field(default_factory=list)
    recommended_fix: str = ""
    github_comment: str = ""
    ticket_title: str = ""
    ticket_labels: list[str] = Field(default_factory=list)
    ticket_assignee: str = ""
