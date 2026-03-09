"""Tests for GitHub API client."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from githubkit.exception import RequestFailed

from agentops.github.client import fetch_issue, parse_issue_url

pytestmark = pytest.mark.asyncio


def _make_issue_response(
    title: str = "Bug report",
    body: str = "Description here",
    labels: list[SimpleNamespace] | None = None,
    login: str = "testuser",
    created_at: datetime | None = None,
) -> MagicMock:
    """Build a mock response matching githubkit's async_get return shape."""
    if labels is None:
        labels = [SimpleNamespace(name="bug"), SimpleNamespace(name="urgent")]
    if created_at is None:
        created_at = datetime(2024, 1, 1, tzinfo=UTC)

    user = SimpleNamespace(login=login)
    parsed_data = SimpleNamespace(
        title=title,
        body=body,
        labels=labels,
        user=user,
        created_at=created_at,
    )
    resp = MagicMock()
    resp.parsed_data = parsed_data
    return resp


class TestParseIssueUrl:
    def test_valid_url(self) -> None:
        result = parse_issue_url("https://github.com/owner/repo/issues/42")
        assert result == ("owner", "repo", 42)

    def test_invalid_url(self) -> None:
        assert parse_issue_url("https://github.com/owner/repo/pull/1") is None

    def test_not_github(self) -> None:
        assert parse_issue_url("https://gitlab.com/owner/repo/issues/1") is None

    def test_missing_number(self) -> None:
        assert parse_issue_url("https://github.com/owner/repo/issues/") is None

    def test_url_with_extra_path(self) -> None:
        assert parse_issue_url("https://github.com/owner/repo/issues/1/comments") is None


class TestFetchIssue:
    async def test_successful_fetch(self) -> None:
        mock_resp = _make_issue_response()
        mock_gh = AsyncMock()
        mock_gh.rest.issues.async_get = AsyncMock(return_value=mock_resp)
        mock_gh.__aenter__ = AsyncMock(return_value=mock_gh)
        mock_gh.__aexit__ = AsyncMock(return_value=None)

        with patch("agentops.github.client.GitHub", return_value=mock_gh):
            result = await fetch_issue("owner", "repo", 1)

        assert result is not None
        assert result.title == "Bug report"
        assert result.body == "Description here"
        assert result.labels == ["bug", "urgent"]
        assert result.author == "testuser"
        assert result.created_at == "2024-01-01T00:00:00+00:00"

    async def test_404_returns_none(self) -> None:
        mock_gh = AsyncMock()
        mock_gh.rest.issues.async_get = AsyncMock(side_effect=RequestFailed(MagicMock()))
        mock_gh.__aenter__ = AsyncMock(return_value=mock_gh)
        mock_gh.__aexit__ = AsyncMock(return_value=None)

        with patch("agentops.github.client.GitHub", return_value=mock_gh):
            result = await fetch_issue("owner", "repo", 999)

        assert result is None

    async def test_401_returns_none(self) -> None:
        mock_gh = AsyncMock()
        mock_gh.rest.issues.async_get = AsyncMock(side_effect=RequestFailed(MagicMock()))
        mock_gh.__aenter__ = AsyncMock(return_value=mock_gh)
        mock_gh.__aexit__ = AsyncMock(return_value=None)

        with patch("agentops.github.client.GitHub", return_value=mock_gh):
            result = await fetch_issue("owner", "repo", 1, token="bad-token")

        assert result is None
