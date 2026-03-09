import json
import os
from collections.abc import Callable
from pathlib import Path

os.environ.setdefault("JWT_SECRET", "test-placeholder-secret-32characters!!")

import pytest
import pytest_asyncio
from fakeredis import FakeAsyncRedis
from httpx import ASGITransport, AsyncClient

from agentops.api.deps.redis import get_redis
from agentops.api.main import create_app
from agentops.config import Settings
from agentops.graph.state import AgentFinding, BugTriageState


@pytest.fixture
def settings() -> Settings:
    return Settings(
        environment="test",
        redis_url="redis://localhost:6379/0",
        jwt_secret="test-placeholder-secret-32characters!!",
        openai_api_key="sk-test",
    )


@pytest.fixture
def fake_redis() -> FakeAsyncRedis:
    return FakeAsyncRedis(decode_responses=True)


@pytest.fixture(params=sorted((Path(__file__).parent / "fixtures" / "issues").glob("*.json")))
def issue_fixture(request: pytest.FixtureRequest) -> dict[str, str]:
    return json.loads(Path(request.param).read_text())


@pytest.fixture
def make_state() -> Callable[..., BugTriageState]:
    def _factory(**kwargs: object) -> BugTriageState:
        defaults: dict[str, object] = {
            "job_id": "test-123",
            "issue_url": "https://github.com/a/b/issues/1",
        }
        defaults.update(kwargs)
        return BugTriageState(**defaults)

    return _factory


@pytest.fixture
def make_finding() -> Callable[..., AgentFinding]:
    def _factory(agent_name: str = "investigator") -> AgentFinding:
        return AgentFinding(
            agent_name=agent_name,
            summary=f"{agent_name} finding",
            confidence=0.7,
            hypothesis="test hypothesis",
            keywords_for_search=["bug", "null"],
            affected_areas=["service"],
        )

    return _factory


@pytest_asyncio.fixture
async def api_client(settings: Settings, fake_redis: FakeAsyncRedis) -> AsyncClient:
    app = create_app(settings, testing=True)
    app.dependency_overrides[get_redis] = lambda: fake_redis
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()
