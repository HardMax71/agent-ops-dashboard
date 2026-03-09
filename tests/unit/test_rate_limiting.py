"""Tests for job creation rate limiting."""

from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from agentops.api.deps.arq import get_arq
from agentops.api.deps.redis import get_redis
from agentops.api.main import create_app
from agentops.config import Settings

pytestmark = pytest.mark.asyncio


@pytest.fixture
def rate_settings() -> Settings:
    return Settings(
        environment="test",
        jwt_secret="test-placeholder-secret-32characters!!",
        openai_api_key="sk-test",
    )


@pytest_asyncio.fixture
async def rate_client(
    rate_settings: Settings,
    fake_redis: "FakeAsyncRedis",  # noqa: F821
    mock_arq: MagicMock,
) -> AsyncClient:
    app = create_app(rate_settings, testing=True)
    app.dependency_overrides[get_redis] = lambda: fake_redis
    app.dependency_overrides[get_arq] = lambda: mock_arq
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client  # type: ignore[misc]
    app.dependency_overrides.clear()


class TestRateLimiting:
    async def test_429_when_limit_exceeded(
        self,
        rate_client: AsyncClient,
        fake_redis: "FakeAsyncRedis",  # noqa: F821
    ) -> None:
        # Set active job counter to the limit
        await fake_redis.set("active_jobs:anonymous", "10")

        resp = await rate_client.post(
            "/jobs",
            json={"issue_url": "https://github.com/a/b/issues/1"},
        )
        assert resp.status_code == 429

    async def test_allows_under_limit(
        self,
        rate_client: AsyncClient,
        fake_redis: "FakeAsyncRedis",  # noqa: F821
    ) -> None:
        await fake_redis.set("active_jobs:anonymous", "5")

        resp = await rate_client.post(
            "/jobs",
            json={"issue_url": "https://github.com/a/b/issues/1"},
        )
        assert resp.status_code == 202

    async def test_counter_incremented_on_creation(
        self,
        rate_client: AsyncClient,
        fake_redis: "FakeAsyncRedis",  # noqa: F821
    ) -> None:
        resp = await rate_client.post(
            "/jobs",
            json={"issue_url": "https://github.com/a/b/issues/1"},
        )
        assert resp.status_code == 202

        count = await fake_redis.get("active_jobs:anonymous")
        assert count == "1"
