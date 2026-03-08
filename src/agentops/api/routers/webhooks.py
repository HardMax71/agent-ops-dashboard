import hashlib
import hmac
import json

from fastapi import APIRouter, Header, HTTPException, Request, status

from agentops.api.deps.redis import RedisDep
from agentops.api.deps.settings import SettingsDep

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _verify_github_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify GitHub webhook X-Hub-Signature-256 header."""
    expected = "sha256=" + hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/github")
async def github_webhook(
    request: Request,
    redis: RedisDep,
    settings: SettingsDep,
    x_hub_signature_256: str = Header(default=""),
    x_github_event: str = Header(default=""),
) -> dict[str, str]:
    """Handle GitHub push webhooks for incremental index updates."""
    body = await request.body()

    if settings.github_webhook_secret:
        if not _verify_github_signature(body, x_hub_signature_256, settings.github_webhook_secret):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")

    if x_github_event != "push":
        return {"status": "ignored", "event": x_github_event}

    payload = json.loads(body)
    ref = payload.get("ref", "")
    default_branch = payload.get("repository", {}).get("default_branch", "main")

    if ref != f"refs/heads/{default_branch}":
        return {"status": "ignored", "reason": "not default branch"}

    repository = payload.get("repository", {}).get("full_name", "")
    before_sha = payload.get("before", "")
    after_sha = payload.get("after", "")

    # Enqueue incremental index update
    await redis.lpush(
        "arq:queue",
        json.dumps({
            "function": "update_codebase_index",
            "args": [repository, before_sha, after_sha],
        }),
    )

    return {"status": "queued", "repository": repository}
