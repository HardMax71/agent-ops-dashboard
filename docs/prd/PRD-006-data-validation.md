---
id: PRD-006
title: Data Validation — GitHub Issue URL
status: DRAFT
domain: backend/api
depends_on: [PRD-001, PRD-003]
key_decisions: [pydantic-v2-annotated-type, github-issue-url-validation, ssrf-prevention, api-boundary-validation-only]
---

# PRD-006 — Data Validation: GitHub Issue URL

## AgentOps Dashboard — Input Validation Requirements

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

## Table of Contents

1. [Problem](#1-problem)
2. [Validation Library: Pydantic v2](#2-validation-library-pydantic-v2)
3. [Reusable Type: GitHubIssueUrl](#3-reusable-type-githubissueurl)
4. [JobCreate Input Model](#4-jobcreate-input-model)
5. [POST /jobs Endpoint](#5-post-jobs-endpoint)
6. [Error Response](#6-error-response)
7. [What Is NOT Validated Here](#7-what-is-not-validated-here)

---

## 1. Problem

`POST /jobs` accepts `issue_url` as a raw string with no structural validation. Without enforcement at the API
boundary, hostile or malformed URLs reach the GitHub API client:

- `file:///etc/passwd` — local file read via any HTTP library that follows non-HTTP schemes
- `http://internal-service/admin` — SSRF: attacker probes internal network topology
- `https://evil.com/repo/issues/1` — non-GitHub URL silently processed

FastAPI and Pydantic v2 provide HTTP 422 validation responses automatically when input models are typed correctly.
Enforcing validation at the API boundary means zero malformed URLs ever reach downstream processing — no explicit
`try/except` needed in route handlers or worker code.

---

## 2. Validation Library: Pydantic v2

Pydantic v2 is already a dependency (pulled in by FastAPI and `pydantic-settings`). No additional package is needed.

| Feature           | Purpose in this PRD                                                                     |
|-------------------|-----------------------------------------------------------------------------------------|
| `AnyHttpUrl`      | Validates scheme is `http` or `https`; parses host; rejects `file://`, `ftp://`, etc.  |
| `AfterValidator`  | Runs a function on the already-parsed `AnyHttpUrl` to enforce the GitHub issue path pattern |

This is the canonical FastAPI/Pydantic v2 pattern for reusable validated types. No separate third-party GitHub URL
library is used — Pydantic IS the standard validation layer for FastAPI.

---

## 3. Reusable Type: `GitHubIssueUrl`

Defined once; imported wherever a GitHub issue URL is accepted.

```python
import re
from typing import Annotated
from pydantic import AnyHttpUrl, AfterValidator

_GITHUB_ISSUE_RE = re.compile(
    r"^https://github\.com/[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+/issues/\d+$"
)

def _validate_github_issue_url(v: AnyHttpUrl) -> AnyHttpUrl:
    if not _GITHUB_ISSUE_RE.match(str(v)):
        raise ValueError(
            "issue_url must be a GitHub issue URL: "
            "https://github.com/{owner}/{repo}/issues/{number}"
        )
    return v

GitHubIssueUrl = Annotated[AnyHttpUrl, AfterValidator(_validate_github_issue_url)]
```

**Validation layers (in order):**

1. `AnyHttpUrl` rejects any non-HTTP/HTTPS scheme — blocks `file://`, `ftp://`, `javascript://`, etc.
2. `AfterValidator` enforces:
   - Host must be exactly `github.com`
   - Path must match `/{owner}/{repo}/issues/{number}` (owner/repo: alphanumeric + `_`, `.`, `-`; number: digits only)

---

## 4. `JobCreate` Input Model

Used as the request body type for `POST /jobs`.

```python
from pydantic import BaseModel

class JobCreate(BaseModel):
    issue_url: GitHubIssueUrl
```

FastAPI automatically returns HTTP 422 with field-level error detail if validation fails — no explicit `try/except`
required in the route handler.

---

## 5. `POST /jobs` Endpoint

```python
@app.post("/jobs", status_code=202)
async def create_job(body: JobCreate, redis: Redis = Depends(get_redis)) -> dict:
    job_id = str(uuid4())
    initial_state = {
        "issue_url": str(body.issue_url),  # str() — BugTriageState uses plain str
        "job_id": job_id,
        ...
    }
    await arq_queue.enqueue_job("run_triage", job_id, initial_state)
    return {"job_id": job_id}
```

`str(body.issue_url)` converts the validated `AnyHttpUrl` back to a plain string for `BugTriageState`, which uses
`issue_url: str` (internal state that only ever receives already-validated URLs from this boundary).

---

## 6. Error Response

When `issue_url` fails validation, FastAPI/Pydantic returns HTTP 422 automatically:

```json
{
  "detail": [
    {
      "type": "value_error",
      "loc": ["body", "issue_url"],
      "msg": "Value error, issue_url must be a GitHub issue URL: https://github.com/{owner}/{repo}/issues/{number}",
      "input": "http://internal-service/admin"
    }
  ]
}
```

No additional error handling code is required in the route or worker.

---

## 7. What Is NOT Validated Here

| Concern                                      | Where it is handled                              |
|----------------------------------------------|--------------------------------------------------|
| GitHub issue existence (404 from GitHub API) | At job execution time in the investigator agent  |
| Repository access / authentication           | At job execution time via GitHub API credentials |
| Issue number range / validity                | GitHub returns 404 for non-existent numbers      |
| Rate limiting on `POST /jobs`                | API gateway / middleware layer (out of scope v1) |

These are intentionally deferred: validating them at the API boundary would require a synchronous GitHub API call,
adding latency and a network dependency to every job submission.
