from typing import Literal

from pydantic import BaseModel, Field

JobStatus = Literal[
    "queued",
    "running",
    "waiting",
    "pausing",
    "paused",
    "done",
    "failed",
    "killed",
    "timed_out",
]
TERMINAL_STATUSES: frozenset[str] = frozenset({"killed", "done", "failed", "timed_out"})


class JobData(BaseModel):
    job_id: str
    status: JobStatus = "queued"
    issue_url: str
    issue_title: str = ""
    issue_body: str = ""
    repository: str = ""
    supervisor_notes: str = ""
    langsmith_url: str = ""
    langsmith_run_id: str = ""
    awaiting_human: bool = False
    current_node: str = ""
    owner_id: str = ""
    created_at: str = ""
    paused: bool = False
    waiting_since: str = ""
    github_comment: str = ""
    github_comment_url: str = ""
    severity: str = ""
    relevant_files: list[str] = Field(default_factory=list)
    recommended_fix: str = ""
    ticket_title: str = ""
    ticket_labels: list[str] = Field(default_factory=list)
    redirect_instructions: list[str] = Field(default_factory=list)
