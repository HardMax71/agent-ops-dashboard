import logging

import redis.asyncio as aioredis

from agentops.auth.service import decrypt_github_token
from agentops.config import Settings
from agentops.github.client import add_labels, parse_issue_url, post_comment
from agentops.models.job import JobData

_logger = logging.getLogger(__name__)


async def post_triage_comment(
    redis: aioredis.Redis,
    job_id: str,
    github_id: str,
    settings: Settings,
    comment_override: str | None = None,
) -> str:
    """Post the triage comment to GitHub and optionally add labels.

    Returns the comment HTML URL.
    """
    raw = await redis.get(f"job:{job_id}")
    if raw is None:
        raise ValueError(f"Job {job_id} not found")
    data = JobData.model_validate_json(raw)

    if comment_override:
        data.github_comment = comment_override

    if not data.github_comment:
        raise ValueError("No triage comment available for this job")

    parsed = parse_issue_url(data.issue_url)
    if parsed is None:
        raise ValueError(f"Cannot parse issue URL: {data.issue_url}")
    owner, repo, number = parsed

    encrypted = await redis.get(f"github_token:{github_id}")
    if encrypted is None:
        raise ValueError("GitHub token not found — please reconnect your GitHub account")

    token = decrypt_github_token(encrypted, settings)

    comment_url = await post_comment(owner, repo, number, data.github_comment, token)

    if data.ticket_labels:
        await add_labels(owner, repo, number, data.ticket_labels, token)

    data.github_comment_url = comment_url
    await redis.setex(f"job:{job_id}", 86400, data.model_dump_json())

    return comment_url
