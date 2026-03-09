from pydantic import BaseModel, Field, HttpUrl


class WebSearchResult(BaseModel):
    url: HttpUrl
    title: str
    snippet: str


class WebSearchFinding(BaseModel):
    agent_name: str = "web_search"
    summary: str
    confidence: float = Field(ge=0.0, le=1.0)
    search_results: list[WebSearchResult] = Field(default_factory=list)
    relevant_links: list[HttpUrl] = Field(default_factory=list)
    analysis: str = ""
