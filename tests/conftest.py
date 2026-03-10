import json
import os
from collections.abc import Callable, Coroutine
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("JWT_SECRET", "test-placeholder-secret-32characters!!")
os.environ.setdefault("ENVIRONMENT", "test")

import pytest
import pytest_asyncio
from fakeredis import FakeAsyncRedis
from httpx import ASGITransport, AsyncClient

from agentops.api.deps.arq import get_arq
from agentops.api.deps.redis import get_redis
from agentops.api.deps.settings import get_settings
from agentops.api.main import create_app
from agentops.auth.service import create_access_token
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


@pytest.fixture
def make_job(fake_redis: FakeAsyncRedis) -> Callable[..., Coroutine[None, None, dict[str, object]]]:
    async def _factory(job_id: str = "job-1", **overrides: object) -> dict[str, object]:
        data: dict[str, object] = {
            "job_id": job_id,
            "status": "running",
            "issue_url": "https://github.com/a/b/issues/1",
            "langsmith_url": "",
            "awaiting_human": False,
            "current_node": "",
            **overrides,
        }
        await fake_redis.setex(f"job:{job_id}", 86400, json.dumps(data))
        return data

    return _factory


@pytest.fixture
def mock_arq() -> MagicMock:
    arq = MagicMock()
    arq.enqueue_job = AsyncMock(return_value=None)
    arq.abort_job = AsyncMock(return_value=None)
    arq.aclose = AsyncMock(return_value=None)
    return arq


@pytest.fixture
def make_token(settings: Settings) -> Callable[..., str]:
    """Create a JWT access token for testing."""

    def _factory(github_id: str = "12345", github_login: str = "testuser") -> str:
        return create_access_token(github_id, github_login, settings)

    return _factory


@pytest_asyncio.fixture
async def api_client(
    settings: Settings,
    fake_redis: FakeAsyncRedis,
    mock_arq: MagicMock,
) -> AsyncClient:
    app = create_app(settings, testing=True)
    app.dependency_overrides[get_redis] = lambda: fake_redis
    app.dependency_overrides[get_arq] = lambda: mock_arq
    app.dependency_overrides[get_settings] = lambda: settings
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def auth_client(
    settings: Settings,
    fake_redis: FakeAsyncRedis,
    mock_arq: MagicMock,
) -> AsyncClient:
    """API client with auth router configured."""
    app = create_app(settings, testing=True)
    app.dependency_overrides[get_redis] = lambda: fake_redis
    app.dependency_overrides[get_arq] = lambda: mock_arq
    app.dependency_overrides[get_settings] = lambda: settings
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()
