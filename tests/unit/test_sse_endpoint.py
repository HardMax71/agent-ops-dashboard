"""Tests for SSE streaming endpoint."""

import asyncio
import json
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


class TestStreamEndpoint:
    async def test_stream_404_for_unknown_job(self, sse_client: AsyncClient) -> None:
        resp = await sse_client.get("/jobs/nonexistent/stream")
        assert resp.status_code == 404

    async def test_stream_returns_event_stream_content_type(
        self,
        sse_client: AsyncClient,
        fake_redis: "FakeAsyncRedis",  # noqa: F821
    ) -> None:
        job_data = {
            "job_id": "job-sse-1",
            "status": "running",
            "issue_url": "https://github.com/a/b/issues/1",
            "langsmith_url": "",
            "awaiting_human": False,
            "current_node": "",
        }
        await fake_redis.setex("job:job-sse-1", 86400, json.dumps(job_data))

        # Publish a terminal event after short delay
        async def _publish_done() -> None:
            await asyncio.sleep(0.1)
            await fake_redis.publish(
                "jobs:job-sse-1:events",
                json.dumps({"type": "job.done"}),
            )

        asyncio.create_task(_publish_done())

        async with sse_client.stream("GET", "/jobs/job-sse-1/stream") as resp:
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers["content-type"]
            chunks = []
            async for chunk in resp.aiter_text():
                chunks.append(chunk)
                if "job.done" in chunk:
                    break

        combined = "".join(chunks)
        assert "job.done" in combined
