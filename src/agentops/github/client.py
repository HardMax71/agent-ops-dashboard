import logging
import re

import httpx

from agentops.github.models import IssueData

_logger = logging.getLogger(__name__)

_ISSUE_URL_RE = re.compile(r"^https://github\.com/([^/]+)/([^/]+)/issues/(\d+)$")
_GITHUB_API_BASE = "https://api.github.com"


def parse_issue_url(url: str) -> tuple[str, str, int] | None:
    """Extract (owner, repo, issue_number) from a GitHub issue URL."""
    match = _ISSUE_URL_RE.match(url)
    if match is None:
        return None
    return match.group(1), match.group(2), int(match.group(3))


async def fetch_issue(
    owner: str,
    repo: str,
    number: int,
    token: str = "",
) -> IssueData | None:
    """Fetch issue metadata from the GitHub API. Returns None on failure."""
    headers: dict[str, str] = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{_GITHUB_API_BASE}/repos/{owner}/{repo}/issues/{number}",
                headers=headers,
                timeout=10.0,
            )
    except httpx.HTTPError:
        _logger.warning("GitHub API unreachable for %s/%s#%d", owner, repo, number)
        return None

    if not resp.is_success:
        _logger.warning(
            "GitHub API returned %d for %s/%s#%d", resp.status_code, owner, repo, number
        )
        return None

    data = resp.json()
    labels = [label["name"] for label in data.get("labels", []) if "name" in label]
    user = data.get("user", {})

    return IssueData(
        title=data.get("title", ""),
        body=data.get("body", "") or "",
        labels=labels,
        author=user.get("login", ""),
        created_at=data.get("created_at", ""),
    )
