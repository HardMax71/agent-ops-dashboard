import json
import os
from pathlib import Path

os.environ.setdefault("JWT_SECRET", "test-placeholder-secret-32characters!!")

import pytest
import pytest_asyncio
from fakeredis import FakeAsyncRedis
from httpx import ASGITransport, AsyncClient

from agentops.api.main import create_app
from agentops.config import Settings

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "issues"


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


@pytest.fixture
def issue_001() -> dict:  # type: ignore[type-arg]
    return json.loads((FIXTURES_DIR / "issue_001.json").read_text())


@pytest.fixture
def issue_002() -> dict:  # type: ignore[type-arg]
    return json.loads((FIXTURES_DIR / "issue_002.json").read_text())


@pytest.fixture
def issue_003() -> dict:  # type: ignore[type-arg]
    return json.loads((FIXTURES_DIR / "issue_003.json").read_text())


@pytest_asyncio.fixture
async def api_client(fake_redis: FakeAsyncRedis) -> AsyncClient:
    app = create_app(testing=True)
    app.state.redis = fake_redis
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
