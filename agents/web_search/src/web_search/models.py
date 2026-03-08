from pydantic import BaseModel, Field


class WebSearchResult(BaseModel):
    url: str
    title: str
    snippet: str


class WebSearchFinding(BaseModel):
    agent_name: str = "web_search"
    summary: str
    confidence: float = Field(ge=0.0, le=1.0)
    search_results: list[WebSearchResult] = Field(default_factory=list)
    relevant_links: list[str] = Field(default_factory=list)
    analysis: str = ""
