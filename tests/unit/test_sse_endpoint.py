"""Tests for GraphQL subscription (replaces SSE streaming)."""

from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from agentops.api.deps.arq import get_arq
from agentops.api.deps.redis import get_redis
from agentops.api.main import create_app
from agentops.config import Settings
from agentops.graphql.types import event_from_dict

pytestmark = pytest.mark.asyncio


@pytest.fixture
def sse_settings() -> Settings:
    return Settings(
        environment="test",
        jwt_secret="test-placeholder-secret-32characters!!",
        openai_api_key="sk-test",
    )


@pytest_asyncio.fixture
async def sse_client(
    sse_settings: Settings,
    fake_redis: "FakeAsyncRedis",  # noqa: F821
    mock_arq: MagicMock,
) -> AsyncClient:
    app = create_app(sse_settings, testing=True)
    app.dependency_overrides[get_redis] = lambda: fake_redis
    app.dependency_overrides[get_arq] = lambda: mock_arq
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client  # type: ignore[misc]
    app.dependency_overrides.clear()


class TestEventFromDict:
    """Test the event_from_dict helper used by subscriptions."""

    def test_agent_spawned(self) -> None:
        data = {
            "type": "agent.spawned",
            "agent_id": "a1",
            "agent_name": "investigator",
            "node": "investigator",
        }
        event = event_from_dict(data)
        assert event.__class__.__name__ == "AgentSpawnedEvent"

    def test_job_done(self) -> None:
        data = {"type": "job.done"}
        event = event_from_dict(data)
        assert event.__class__.__name__ == "JobDoneEvent"

    def test_job_failed(self) -> None:
        data = {"type": "job.failed", "error": "timeout"}
        event = event_from_dict(data)
        assert event.__class__.__name__ == "JobFailedEvent"

    def test_unknown_type_returns_job_done(self) -> None:
        data = {"type": "unknown.event"}
        event = event_from_dict(data)
        assert event.__class__.__name__ == "JobDoneEvent"


class TestGraphQLEndpoint:
    """Test that the GraphQL endpoint is accessible."""

    async def test_graphql_introspection(self, sse_client: AsyncClient) -> None:
        resp = await sse_client.post(
            "/graphql",
            json={"query": "{ __typename }"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["__typename"] == "Query"

    async def test_job_query_not_found_returns_error(self, sse_client: AsyncClient) -> None:
        resp = await sse_client.post(
            "/graphql",
            json={"query": '{ job(jobId: "nonexistent") { jobId } }'},
        )
        assert resp.status_code == 200
        assert resp.json().get("errors") is not None
