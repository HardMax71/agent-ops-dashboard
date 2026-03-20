import logging
import re
from urllib.parse import urlparse

from githubkit import GitHub, TokenAuthStrategy, UnauthAuthStrategy
from githubkit.exception import RequestFailed

from agentops.github.models import IssueData

_logger = logging.getLogger(__name__)

_ISSUE_PATH_RE = re.compile(r"^/([^/]+)/([^/]+)/issues/(\d+)/?$")


def parse_issue_url(url: str) -> tuple[str, str, int] | None:
    """Extract (owner, repo, issue_number) from a GitHub issue URL."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "github.com":
        return None
    match = _ISSUE_PATH_RE.match(parsed.path)
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
    labels: list[str] = [label.name for label in issue.labels if label.name]
    return IssueData(
        title=issue.title,
        body=issue.body or "",
        labels=labels,
        author=issue.user.login if issue.user else "",
        created_at=issue.created_at.isoformat() if issue.created_at else "",
    )


async def post_comment(
    owner: str,
    repo: str,
    number: int,
    body: str,
    token: str,
) -> str:
    """Post a comment on a GitHub issue. Returns the comment HTML URL."""
    auth = TokenAuthStrategy(token)
    try:
        async with GitHub(auth) as gh:
            resp = await gh.rest.issues.async_create_comment(
                owner=owner, repo=repo, issue_number=number, data={"body": body}
            )
    except RequestFailed:
        _logger.warning("GitHub API comment post failed for %s/%s#%d", owner, repo, number)
        raise

    return str(resp.parsed_data.html_url)


async def add_labels(
    owner: str,
    repo: str,
    number: int,
    labels: list[str],
    token: str,
) -> None:
    """Add labels to a GitHub issue."""
    auth = TokenAuthStrategy(token)
    try:
        async with GitHub(auth) as gh:
            await gh.rest.issues.async_add_labels(
                owner=owner, repo=repo, issue_number=number, data={"labels": labels}
            )
    except RequestFailed:
        _logger.warning("GitHub API add_labels failed for %s/%s#%d", owner, repo, number)
        raise
