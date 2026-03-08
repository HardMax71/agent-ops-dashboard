from agentops.db.models import GitHubToken, Job, JobTraceSummary, RepoIndexMetadata, User


def test_user_model_has_required_fields() -> None:
    # Just verify the model class has the expected attributes
    assert hasattr(User, "github_id")
    assert hasattr(User, "github_login")
    assert hasattr(User, "avatar_url")
    assert hasattr(User, "created_at")


def test_job_model_has_required_fields() -> None:
    assert hasattr(Job, "id")
    assert hasattr(Job, "issue_url")
    assert hasattr(Job, "status")
    assert hasattr(Job, "current_node")
    assert hasattr(Job, "awaiting_human")
    assert hasattr(Job, "langsmith_url")


def test_github_token_model() -> None:
    assert hasattr(GitHubToken, "user_id")
    assert hasattr(GitHubToken, "encrypted_token")


def test_job_trace_summary_model() -> None:
    assert hasattr(JobTraceSummary, "job_id")
    assert hasattr(JobTraceSummary, "total_tokens")
    assert hasattr(JobTraceSummary, "total_cost_usd")
    assert hasattr(JobTraceSummary, "duration_seconds")
    assert hasattr(JobTraceSummary, "langsmith_deep_link")


def test_repo_index_metadata_model() -> None:
    assert hasattr(RepoIndexMetadata, "repository")
    assert hasattr(RepoIndexMetadata, "status")
    assert hasattr(RepoIndexMetadata, "indexed_at")
