import fakeredis
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_me_without_token_returns_401(api_client: AsyncClient) -> None:
    response = await api_client.get("/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logout_clears_cookie(api_client: AsyncClient, fake_redis: fakeredis.FakeAsyncRedis) -> None:
    # Store a fake refresh token
    await fake_redis.setex("refresh_token:test-uuid", 3600, "123:testuser")

    response = await api_client.delete(
        "/auth/logout",
        cookies={"refresh_token": "test-uuid"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "logged_out"

    # Verify token was deleted from Redis
    result = await fake_redis.get("refresh_token:test-uuid")
    assert result is None


@pytest.mark.asyncio
async def test_refresh_without_cookie_returns_401(api_client: AsyncClient) -> None:
    response = await api_client.post("/auth/refresh")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_exchange_invalid_auth_code_returns_401(api_client: AsyncClient) -> None:
    response = await api_client.post("/auth/token", json={"code": "invalid-code"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_exchange_valid_auth_code_returns_token(
    api_client: AsyncClient, fake_redis: fakeredis.FakeAsyncRedis
) -> None:
    # Store a valid auth code
    await fake_redis.setex("auth_code:valid-code-123", 300, "12345:testuser")

    response = await api_client.post("/auth/token", json={"code": "valid-code-123"})
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

    # Verify auth code was consumed
    result = await fake_redis.get("auth_code:valid-code-123")
    assert result is None


@pytest.mark.asyncio
async def test_me_with_valid_token_returns_user_info(api_client: AsyncClient) -> None:
    from agentops.auth.service import create_access_token
    from agentops.config import get_settings

    # Use the same settings the app uses
    app_settings = get_settings()
    token = create_access_token("12345", "testuser", app_settings)

    response = await api_client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert data["github_id"] == "12345"
    assert data["github_login"] == "testuser"
