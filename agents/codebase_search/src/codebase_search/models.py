from pydantic import BaseModel, Field


class RelevantFile(BaseModel):
    path: str
    relevance_score: float = 0.0
    snippet: str = ""


class CodebaseFinding(BaseModel):
    agent_name: str = "codebase_search"
    summary: str
    confidence: float = 0.0
    relevant_files: list[RelevantFile] = Field(default_factory=list)
    root_cause_location: str = ""
    analysis: str = ""
