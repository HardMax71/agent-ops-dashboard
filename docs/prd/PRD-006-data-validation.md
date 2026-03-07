---
id: PRD-006
title: Data Validation — GitHub Issue URL
status: DRAFT
domain: backend/api
depends_on: [PRD-001, PRD-003]
key_decisions: [pydantic-v2-annotated-type, github-issue-url-validation, ssrf-prevention, api-boundary-validation-only, atomic-setnx-idempotency]
---

# PRD-006 — Data Validation: GitHub Issue URL

| Field        | Value                                                                                                           |
|--------------|-----------------------------------------------------------------------------------------------------------------|
| Document ID  | PRD-006                                                                                                         |
| Version      | 1.0                                                                                                             |
| Status       | DRAFT                                                                                                           |
| Date         | March 2026                                                                                                      |
| Author       | Product & Engineering Team                                                                                      |
| Parent Doc   | [PRD-001](PRD-001-master-overview.md)                                                                           |
| Related Docs | [PRD-003](PRD-003-langgraph-orchestration.md) (`POST /jobs` endpoint and `BugTriageState`)                      |

---

## Problem

`POST /jobs` accepts `issue_url` as a raw string with no structural validation. Without enforcement at the API
boundary, hostile or malformed URLs reach the GitHub API client:

- `file:///etc/passwd` — local file read via any HTTP library that follows non-HTTP schemes
- `http://internal-service/admin` — SSRF: attacker probes internal network topology
- `https://evil.com/repo/issues/1` — non-GitHub URL silently processed

FastAPI and Pydantic v2 provide HTTP 422 validation responses automatically when input models are typed correctly.
Enforcing validation at the API boundary means zero malformed URLs ever reach downstream processing — no explicit
`try/except` needed in route handlers or worker code.

---

## Validation Library: Pydantic v2

Pydantic v2 is already a dependency (pulled in by FastAPI and `pydantic-settings`). No additional package is needed.

| Feature          | Purpose in this PRD                                                                    |
|------------------|----------------------------------------------------------------------------------------|
| `Field(pattern=)` | Single regex applied to a `str` field; enforces scheme, host, and path in one shot   |
| `Annotated[str, Field(...)]` | Reusable type alias — define once, import wherever a GitHub issue URL is accepted |

No separate validator function, no custom URL type. Pydantic v2 evaluates the `pattern` constraint and returns
HTTP 422 automatically — the regex IS the validation layer.

---

## Reusable Type: `GitHubIssueUrl`

Defined once; imported wherever a GitHub issue URL is accepted.

```python
from typing import Annotated
from pydantic import Field

GitHubIssueUrl = Annotated[
    str,
    Field(pattern=r"^https://github\.com/[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+/issues/\d+$"),
]
```

**What the regex enforces:**

- `^https://` — HTTPS scheme only; blocks `http://`, `file://`, `ftp://`, `javascript://`, etc.
- `github\.com/` — host must be exactly `github.com`
- `[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+` — `{owner}/{repo}` (alphanumeric + `_`, `.`, `-`)
- `/issues/\d+$` — path segment `issues` followed by a numeric issue ID

---

## `JobCreate` Input Model

Used as the request body type for `POST /jobs`.

```python
from pydantic import BaseModel

class JobCreate(BaseModel):
    issue_url: GitHubIssueUrl
```

FastAPI automatically returns HTTP 422 with field-level error detail if validation fails — no explicit `try/except`
required in the route handler.

The `JobCreate` model has no explicit idempotency field — the key is derived server-side as
`SHA-256(issue_url + ":" + owner_id)` so callers need no special header or field.

---

## `POST /jobs` Endpoint

```python
@router.post("/", status_code=202)
async def create_job(
    body: JobCreate,
    redis: Redis = Depends(get_redis),
    current_user: User = Depends(get_current_user),
    response: Response = None,
) -> dict:
    idem_key = _idempotency_key(body.issue_url, current_user.id)
    job_id = str(uuid4())

    # Atomic SET NX: only one concurrent request wins; others see the winner's job_id.
    was_set = await redis.set(
        f"idempotency:{idem_key}", job_id, ex=86400, nx=True
    )
    if not was_set:
        existing = await redis.get(f"idempotency:{idem_key}")
        response.status_code = 200
        return {"job_id": existing.decode()}

    initial_state = {
        "issue_url": body.issue_url,
        "job_id": job_id,
        ...
    }
    await arq_queue.enqueue_job("run_triage", job_id, initial_state)
    return {"job_id": job_id}


def _idempotency_key(issue_url: str, owner_id: str) -> str:
    return hashlib.sha256(f"{issue_url}:{owner_id}".encode()).hexdigest()
```

`body.issue_url` is already a plain `str` — `GitHubIssueUrl = Annotated[str, ...]` — so no conversion is needed
before passing it to `BugTriageState`.

`get_current_user` is injected directly here (not only at router level) so that `owner_id`
is available for key derivation; the router-level dependency still enforces auth for all
other endpoints.

---

## Error Response

When `issue_url` fails validation, FastAPI/Pydantic returns HTTP 422 automatically:

```json
{
  "detail": [
    {
      "type": "string_pattern_mismatch",
      "loc": ["body", "issue_url"],
      "msg": "String should match pattern '^https://github\\.com/...'",
      "input": "http://internal-service/admin",
      "ctx": { "pattern": "^https://github\\.com/[A-Za-z0-9_.\\-]+/[A-Za-z0-9_.\\-]+/issues/\\d+$" }
    }
  ]
}
```

No additional error handling code is required in the route or worker.

---

## Idempotent 200 Response

If a job for the same `issue_url` + authenticated user already exists (submitted within the last
24 hours), `POST /jobs` returns **HTTP 200** with the existing job ID:

```json
{ "job_id": "<existing-uuid>" }
```

The frontend should treat 200 identically to 202 — navigate to the existing job's workspace.

---

## What Is NOT Validated Here

| Concern                                      | Where it is handled                              |
|----------------------------------------------|--------------------------------------------------|
| GitHub issue existence (404 from GitHub API) | At job execution time in the investigator agent  |
| Repository access / authentication           | At job execution time via GitHub API credentials |
| Issue number range / validity                | GitHub returns 404 for non-existent numbers      |
| Rate limiting on `POST /jobs`                | API gateway / middleware layer (out of scope v1) |
| Duplicate job detection (same URL, same user) | `POST /jobs` handler via Redis idempotency key |

These are intentionally deferred: validating them at the API boundary would require a synchronous GitHub API call,
adding latency and a network dependency to every job submission.
