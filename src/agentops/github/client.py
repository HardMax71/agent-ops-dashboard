import logging
import re

from githubkit import GitHub, TokenAuthStrategy, UnauthAuthStrategy
from githubkit.exception import RequestFailed

from agentops.github.models import IssueData

_logger = logging.getLogger(__name__)

_ISSUE_URL_RE = re.compile(r"^https://github\.com/([^/]+)/([^/]+)/issues/(\d+)$")


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
    auth = TokenAuthStrategy(token) if token else UnauthAuthStrategy()
    try:
        async with GitHub(auth) as gh:
            resp = await gh.rest.issues.async_get(owner=owner, repo=repo, issue_number=number)
    except RequestFailed:
        _logger.warning("GitHub API request failed for %s/%s#%d", owner, repo, number)
        return None

    issue = resp.parsed_data
    labels: list[str] = [
        label.name
        for label in issue.labels
        if label.name  # type: ignore[union-attr]
    ]
    return IssueData(
        title=issue.title,
        body=issue.body or "",
        labels=labels,
        author=issue.user.login if issue.user else "",
        created_at=issue.created_at.isoformat() if issue.created_at else "",
    )
