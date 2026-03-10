from langsmith import Client
from pydantic import BaseModel


class LangSmithRunSummary(BaseModel):
    id: str
    name: str
    status: str


class LangSmithFeedbackHandler:
    """Handler for sending feedback to LangSmith."""

    def __init__(self, api_key: str, org_id: str, project_id: str) -> None:
        self.client = Client(api_key=api_key)
        self.org_id = org_id
        self.project_id = project_id

    async def submit_feedback(
        self,
        run_id: str,
        key: str,
        score: float,
        comment: str = "",
    ) -> None:
        """Submit feedback for a LangSmith run."""
        self.client.create_feedback(
            run_id=run_id,
            key=key,
            score=score,
            comment=comment,
        )

    def get_deep_link(self, run_id: str) -> str:
        """Construct LangSmith deep link URL."""
        return (
            f"https://smith.langchain.com/o/{self.org_id}/projects/p/{self.project_id}/r/{run_id}"
        )


async def fetch_runs_for_job(
    api_key: str,
    project_name: str,
    job_id: str,
) -> list[LangSmithRunSummary]:
    """Fetch LangSmith runs for a given job ID."""
    client = Client(api_key=api_key)
    runs = list(
        client.list_runs(
            project_name=project_name,
            filter=f'has(metadata, \'{{"job_id": "{job_id}"}}\' )',
        )
    )
    return [
        LangSmithRunSummary(id=str(r.id), name=r.name or "", status=r.status or "") for r in runs
    ]
