"""Tests for GitHub API client."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from agentops.github.client import fetch_issue, parse_issue_url

pytestmark = pytest.mark.asyncio


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
        mock_response = httpx.Response(
            200,
            json={
                "title": "Bug report",
                "body": "Description here",
                "labels": [{"name": "bug"}, {"name": "urgent"}],
                "user": {"login": "testuser"},
                "created_at": "2024-01-01T00:00:00Z",
            },
        )
        with patch("agentops.github.client.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            result = await fetch_issue("owner", "repo", 1)

        assert result is not None
        assert result.title == "Bug report"
        assert result.body == "Description here"
        assert result.labels == ["bug", "urgent"]
        assert result.author == "testuser"

    async def test_404_returns_none(self) -> None:
        mock_response = httpx.Response(404, json={"message": "Not Found"})
        with patch("agentops.github.client.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            result = await fetch_issue("owner", "repo", 999)

        assert result is None

    async def test_401_returns_none(self) -> None:
        mock_response = httpx.Response(401, json={"message": "Bad credentials"})
        with patch("agentops.github.client.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            result = await fetch_issue("owner", "repo", 1, token="bad-token")

        assert result is None
