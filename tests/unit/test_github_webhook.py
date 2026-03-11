import hashlib
import hmac
import json

import pytest
from httpx import ASGITransport, AsyncClient

from agentops.api.deps.redis import get_redis
from agentops.api.deps.settings import get_settings
from agentops.api.main import create_app
from agentops.config import Settings

WEBHOOK_SECRET = "test-webhook-secret"


def _sign(payload: bytes, secret: str) -> str:
    """Compute X-Hub-Signature-256 for a payload."""
    digest = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


@pytest.mark.asyncio
async def test_github_webhook_rejects_missing_secret(api_client: AsyncClient) -> None:
    """When github_webhook_secret is empty the endpoint returns 403."""
    response = await api_client.post(
        "/webhooks/github",
        content=b"{}",
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "push",
            "X-Hub-Signature-256": "",
        },
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "GitHub webhook secret not configured"


@pytest.mark.asyncio
async def test_github_webhook_push_event(
    settings: Settings,
    fake_redis: "FakeAsyncRedis",  # noqa: F821
) -> None:
    """Test that a valid push event queues an index update."""
    settings.github_webhook_secret = WEBHOOK_SECRET

    app = create_app(settings, testing=True)
    app.dependency_overrides[get_redis] = lambda: fake_redis
    app.dependency_overrides[get_settings] = lambda: settings

    payload = {
        "ref": "refs/heads/main",
        "before": "abc123",
        "after": "def456",
        "repository": {
            "full_name": "owner/repo",
            "default_branch": "main",
        },
    }
    body = json.dumps(payload).encode()
    signature = _sign(body, WEBHOOK_SECRET)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/webhooks/github",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Event": "push",
                "X-Hub-Signature-256": signature,
            },
        )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "queued"
    assert data["repository"] == "owner/repo"


@pytest.mark.asyncio
async def test_github_webhook_non_push_event(
    settings: Settings,
    fake_redis: "FakeAsyncRedis",  # noqa: F821
) -> None:
    """Non-push events are ignored with a descriptive status."""
    settings.github_webhook_secret = WEBHOOK_SECRET

    app = create_app(settings, testing=True)
    app.dependency_overrides[get_redis] = lambda: fake_redis
    app.dependency_overrides[get_settings] = lambda: settings

    body = b"{}"
    signature = _sign(body, WEBHOOK_SECRET)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/webhooks/github",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Event": "star",
                "X-Hub-Signature-256": signature,
            },
        )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ignored"
    assert data["event"] == "star"
