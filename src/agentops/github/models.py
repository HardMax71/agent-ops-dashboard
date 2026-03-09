from pydantic import BaseModel


class IssueData(BaseModel):
    """GitHub issue metadata."""

    title: str
    body: str
    labels: list[str] = []
    author: str = ""
    created_at: str = ""
