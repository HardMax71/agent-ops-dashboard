"""GitHub write-back service — post triage results back to GitHub issues."""

import json
import logging

import redis.asyncio as aioredis

from agentops.auth.service import decrypt_github_token
from agentops.config import Settings
from agentops.github.client import add_labels, parse_issue_url, post_comment

_logger = logging.getLogger(__name__)


async def post_triage_comment(
    redis: aioredis.Redis,
    job_id: str,
    github_id: str,
    settings: Settings,
) -> str:
    """Post the triage comment to GitHub and optionally add labels.

    Returns the comment HTML URL.
    """
    raw = await redis.get(f"job:{job_id}")
    if raw is None:
        raise ValueError(f"Job {job_id} not found")
    data = json.loads(raw)

    issue_url: str = data.get("issue_url", "")
    github_comment: str = data.get("github_comment", "")
    ticket_labels: list[str] = data.get("ticket_labels", [])

    if not github_comment:
        raise ValueError("No triage comment available for this job")

    parsed = parse_issue_url(issue_url)
    if parsed is None:
        raise ValueError(f"Cannot parse issue URL: {issue_url}")
    owner, repo, number = parsed

    encrypted = await redis.get(f"github_token:{github_id}")
    if encrypted is None:
        raise ValueError("GitHub token not found — please reconnect your GitHub account")

    token = decrypt_github_token(encrypted, settings)

    comment_url = await post_comment(owner, repo, number, github_comment, token)

    if ticket_labels:
        await add_labels(owner, repo, number, ticket_labels, token)

    data["github_comment_url"] = comment_url
    await redis.setex(f"job:{job_id}", 86400, json.dumps(data))

    return comment_url
