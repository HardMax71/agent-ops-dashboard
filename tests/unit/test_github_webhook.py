import json

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_github_webhook_push_event(api_client: AsyncClient) -> None:
    """Test that a valid push event queues an index update."""
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
    response = await api_client.post(
        "/webhooks/github",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "push",
            "X-Hub-Signature-256": "",
        },
    )
    # Without a secret configured, should accept it
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_github_webhook_non_push_event(api_client: AsyncClient) -> None:
    response = await api_client.post(
        "/webhooks/github",
        content=b"{}",
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "star",
            "X-Hub-Signature-256": "",
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"
