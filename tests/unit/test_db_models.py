"""Tests for DB model definitions."""

from agentops.db.models import (
    Base,
    GitHubToken,
    Job,
    JobTraceSummary,
    RepoIndexMetadata,
    User,
)


class TestUser:
    def test_tablename(self) -> None:
        assert User.__tablename__ == "users"

    def test_inherits_base(self) -> None:
        assert issubclass(User, Base)

    def test_columns(self) -> None:
        columns = {c.name for c in User.__table__.columns}
        assert columns == {
            "id",
            "github_id",
            "github_login",
            "avatar_url",
            "created_at",
            "updated_at",
        }

    def test_github_id_unique(self) -> None:
        col = User.__table__.c.github_id
        assert col.unique is True
        assert col.index is True


class TestGitHubToken:
    def test_tablename(self) -> None:
        assert GitHubToken.__tablename__ == "github_tokens"

    def test_user_id_foreign_key(self) -> None:
        col = GitHubToken.__table__.c.user_id
        fk = list(col.foreign_keys)[0]
        assert fk.target_fullname == "users.id"


class TestJob:
    def test_tablename(self) -> None:
        assert Job.__tablename__ == "jobs"

    def test_id_is_string_pk(self) -> None:
        col = Job.__table__.c.id
        assert col.primary_key is True

    def test_status_indexed(self) -> None:
        col = Job.__table__.c.status
        assert col.index is True

    def test_owner_id_nullable(self) -> None:
        col = Job.__table__.c.owner_id
        assert col.nullable is True

    def test_columns(self) -> None:
        columns = {c.name for c in Job.__table__.columns}
        expected = {
            "id",
            "owner_id",
            "issue_url",
            "issue_title",
            "issue_body",
            "repository",
            "status",
            "current_node",
            "awaiting_human",
            "paused",
            "supervisor_notes",
            "langsmith_run_id",
            "langsmith_url",
            "total_tokens",
            "total_cost_usd",
            "created_at",
            "updated_at",
        }
        assert columns == expected

    def test_defaults(self) -> None:
        col = Job.__table__.c.status
        assert col.default.arg == "queued"


class TestJobTraceSummary:
    def test_job_id_foreign_key(self) -> None:
        col = JobTraceSummary.__table__.c.job_id
        fk = list(col.foreign_keys)[0]
        assert fk.target_fullname == "jobs.id"


class TestRepoIndexMetadata:
    def test_repository_unique_indexed(self) -> None:
        col = RepoIndexMetadata.__table__.c.repository
        assert col.unique is True
        assert col.index is True
