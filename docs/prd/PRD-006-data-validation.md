---
id: PRD-006
title: Data Validation — GitHub Issue URL
status: DRAFT
domain: backend/api
depends_on: [PRD-001, PRD-003]
key_decisions: [pydantic-v2-annotated-type, github-issue-url-validation, ssrf-prevention, api-boundary-validation-only]
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

---

## `POST /jobs` Endpoint

```python
@router.post("/", status_code=202)
async def create_job(body: JobCreate, redis: Redis = Depends(get_redis)) -> dict:
    job_id = str(uuid4())
    initial_state = {
        "issue_url": body.issue_url,
        "job_id": job_id,
        ...
    }
    await arq_queue.enqueue_job("run_triage", job_id, initial_state)
    return {"job_id": job_id}
```

`body.issue_url` is already a plain `str` — `GitHubIssueUrl = Annotated[str, ...]` — so no conversion is needed
before passing it to `BugTriageState`.

> **Auth note:** `get_current_user` is omitted from this signature because authentication is enforced at the
> router level — `APIRouter(prefix="/jobs", dependencies=[Depends(get_current_user)])` — not per-endpoint.
> See [PRD-008 §REST API Authentication](PRD-008-authentication.md#rest-api-authentication) for the full auth pattern.

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

## What Is NOT Validated Here

| Concern                                      | Where it is handled                              |
|----------------------------------------------|--------------------------------------------------|
| GitHub issue existence (404 from GitHub API) | At job execution time in the investigator agent  |
| Repository access / authentication           | At job execution time via GitHub API credentials |
| Issue number range / validity                | GitHub returns 404 for non-existent numbers      |
| Rate limiting on `POST /jobs`                | API gateway / middleware layer (out of scope v1) |

These are intentionally deferred: validating them at the API boundary would require a synchronous GitHub API call,
adding latency and a network dependency to every job submission.
