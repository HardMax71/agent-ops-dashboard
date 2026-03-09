from langsmith import Client


class LangSmithFeedbackHandler:
    """Handler for sending feedback to LangSmith.

    Note: LangSmith client is synchronous — call submit_feedback from a sync context
    or wrap with asyncio.to_thread().
    """

    def __init__(self, api_key: str, org_id: str, project_id: str) -> None:
        self.client = Client(api_key=api_key)
        self.org_id = org_id
        self.project_id = project_id

    def submit_feedback(
        self,
        run_id: str,
        key: str,
        score: float,
        comment: str = "",
    ) -> None:
        """Submit feedback for a LangSmith run (sync — LangSmith client is sync)."""
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


def fetch_runs_for_job(api_key: str, project_name: str, job_id: str) -> list[dict[str, str]]:
    """Fetch LangSmith runs for a given job ID (sync)."""
    client = Client(api_key=api_key)
    runs = list(
        client.list_runs(
            project_name=project_name,
            filter=f'has(metadata, \'{{"job_id": "{job_id}"}}\' )',
        )
    )
    return [{"id": str(r.id), "name": r.name or "", "status": r.status or ""} for r in runs]
