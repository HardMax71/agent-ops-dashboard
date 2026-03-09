"""Tests for auth router endpoints."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from agentops.api.deps.arq import get_arq
from agentops.api.deps.redis import get_redis
from agentops.api.main import create_app
from agentops.auth.service import create_access_token
from agentops.config import Settings, get_settings

pytestmark = pytest.mark.asyncio


@pytest.fixture
def auth_settings() -> Settings:
    return Settings(
        environment="test",
        jwt_secret="test-placeholder-secret-32characters!!",
        openai_api_key="sk-test",
        github_client_id="test-client-id",
        github_client_secret="test-client-secret",
    )


@pytest_asyncio.fixture
async def auth_client(
    auth_settings: Settings,
    fake_redis: "FakeAsyncRedis",  # noqa: F821
    mock_arq: "MagicMock",  # noqa: F821
) -> AsyncClient:
    app = create_app(auth_settings, testing=True)
    app.dependency_overrides[get_redis] = lambda: fake_redis
    app.dependency_overrides[get_arq] = lambda: mock_arq
    app.dependency_overrides[get_settings] = lambda: auth_settings
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client  # type: ignore[misc]
    app.dependency_overrides.clear()


class TestLogin:
    async def test_login_redirect_includes_state(
        self,
        auth_client: AsyncClient,
        fake_redis: "FakeAsyncRedis",  # noqa: F821
    ) -> None:
        resp = await auth_client.get("/auth/login", follow_redirects=False)
        assert resp.status_code == 307
        location = resp.headers["location"]
        assert "state=" in location
        assert "client_id=test-client-id" in location
        assert "scope=read:user" in location


class TestCallback:
    async def test_callback_rejects_invalid_state(self, auth_client: AsyncClient) -> None:
        resp = await auth_client.get(
            "/auth/callback", params={"code": "test", "state": "invalid"}, follow_redirects=False
        )
        assert resp.status_code == 403


class TestTokenExchange:
    async def test_valid_code_returns_200(
        self,
        auth_client: AsyncClient,
        fake_redis: "FakeAsyncRedis",  # noqa: F821
    ) -> None:
        await fake_redis.setex("auth_code:test-code", 300, "12345:testuser")
        resp = await auth_client.post("/auth/token", json={"code": "test-code"})
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    async def test_invalid_code_returns_401(self, auth_client: AsyncClient) -> None:
        resp = await auth_client.post("/auth/token", json={"code": "bad-code"})
        assert resp.status_code == 401


class TestRefresh:
    async def test_valid_cookie_returns_new_jwt(
        self,
        auth_client: AsyncClient,
        fake_redis: "FakeAsyncRedis",  # noqa: F821
    ) -> None:
        await fake_redis.setex("refresh_token:rt-id", 604800, "12345:testuser")
        auth_client.cookies.set("refresh_token", "rt-id")
        resp = await auth_client.post("/auth/refresh")
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    async def test_missing_cookie_returns_401(self, auth_client: AsyncClient) -> None:
        resp = await auth_client.post("/auth/refresh")
        assert resp.status_code == 401


class TestMe:
    async def test_valid_token_returns_user_info(
        self, auth_client: AsyncClient, auth_settings: Settings
    ) -> None:
        token = create_access_token("12345", "testuser", auth_settings)
        resp = await auth_client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["github_id"] == "12345"
        assert data["github_login"] == "testuser"

    async def test_no_token_returns_401(self, auth_client: AsyncClient) -> None:
        resp = await auth_client.get("/auth/me")
        assert resp.status_code == 401


class TestLogout:
    async def test_logout_clears_redis_and_cookie(
        self,
        auth_client: AsyncClient,
        fake_redis: "FakeAsyncRedis",  # noqa: F821
    ) -> None:
        await fake_redis.setex("refresh_token:rt-id", 604800, "12345:testuser")
        auth_client.cookies.set("refresh_token", "rt-id")
        resp = await auth_client.delete("/auth/logout")
        assert resp.status_code == 200
        assert resp.json()["status"] == "logged_out"
        # Token should be deleted from Redis
        stored = await fake_redis.get("refresh_token:rt-id")
        assert stored is None
