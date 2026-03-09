"""Tests for internal LangSmith webhook router."""

from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from agentops.api.deps.arq import get_arq
from agentops.api.deps.redis import get_redis
from agentops.api.main import create_app
from agentops.config import Settings, get_settings

pytestmark = pytest.mark.asyncio

_WEBHOOK_BODY = {
    "rule_id": "rule-123",
    "run_id": "run-456",
    "event_type": "alert",
    "payload": {"key": "value"},
}


@pytest.fixture
def internal_settings() -> Settings:
    return Settings(
        environment="test",
        jwt_secret="test-placeholder-secret-32characters!!",
        openai_api_key="sk-test",
        langsmith_webhook_secret="test-webhook-secret",
    )


@pytest_asyncio.fixture
async def internal_client(
    internal_settings: Settings,
    fake_redis: "FakeAsyncRedis",  # noqa: F821
    mock_arq: MagicMock,
) -> AsyncClient:
    app = create_app(internal_settings, testing=True)
    app.dependency_overrides[get_redis] = lambda: fake_redis
    app.dependency_overrides[get_arq] = lambda: mock_arq
    app.dependency_overrides[get_settings] = lambda: internal_settings
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client  # type: ignore[misc]
    app.dependency_overrides.clear()


class TestLangSmithAlert:
    async def test_valid_secret_returns_200(self, internal_client: AsyncClient) -> None:
        resp = await internal_client.post(
            "/internal/langsmith-alert?secret=test-webhook-secret",
            json=_WEBHOOK_BODY,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "received"
        assert resp.json()["rule_id"] == "rule-123"

    async def test_invalid_secret_returns_403(self, internal_client: AsyncClient) -> None:
        resp = await internal_client.post(
            "/internal/langsmith-alert?secret=wrong",
            json=_WEBHOOK_BODY,
        )
        assert resp.status_code == 403

    async def test_missing_secret_returns_403(self, internal_client: AsyncClient) -> None:
        resp = await internal_client.post(
            "/internal/langsmith-alert",
            json=_WEBHOOK_BODY,
        )
        assert resp.status_code == 403
