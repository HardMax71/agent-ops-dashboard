# PRD-008 — Authentication & Authorization

## AgentOps Dashboard — Identity, Session, and Access Control

| Field        | Value                                                                                                                                                                                                 |
|--------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Document ID  | PRD-008                                                                                                                                                                                               |
| Version      | 1.0                                                                                                                                                                                                   |
| Status       | DRAFT                                                                                                                                                                                                 |
| Date         | March 2026                                                                                                                                                                                            |
| Author       | Engineering Team                                                                                                                                                                                      |
| Parent       | [PRD-001](PRD-001-master-overview.md)                                                                                                                                                                 |
| Related Docs | [PRD-003](PRD-003-langgraph-orchestration.md) (job endpoints), [PRD-006](PRD-006-data-validation.md) (input validation), [PRD-007](PRD-007-developer-tooling.md) (tooling standards) |

---

## Table of Contents

1. [Overview](#1-overview)
2. [Threat Model](#2-threat-model)
3. [Identity Provider: GitHub OAuth 2.0](#3-identity-provider-github-oauth-20)
4. [Session & JWT Model](#4-session--jwt-model)
5. [REST API Authentication](#5-rest-api-authentication)
6. [SSE Endpoint Authentication](#6-sse-endpoint-authentication)
7. [Job Ownership & Per-Resource Authorization](#7-job-ownership--per-resource-authorization)
8. [GitHub OAuth Token Management](#8-github-oauth-token-management)
9. [Token Lifecycle](#9-token-lifecycle)
10. [CORS & Security Headers](#10-cors--security-headers)
11. [Dependencies & Libraries](#11-dependencies--libraries)
12. [Implementation Patterns](#12-implementation-patterns)
13. [Out of Scope (v1)](#13-out-of-scope-v1)

---

## 1. Overview

### 1.1 Why This PRD Exists

PRD-003 specifies five authenticated endpoints — `POST /jobs`, `GET /jobs/{id}/stream`,
`POST /jobs/{id}/answer`, `POST /jobs/{id}/pause`, `DELETE /jobs/{id}` — with no authentication
mechanism defined. In the current spec:

- Any actor who knows a job UUID can read another user's output stream
- Any actor can answer another user's `interrupt()`, injecting arbitrary text into a running agent
- Any actor can kill any job
- Any actor can create jobs, consuming operator-paid LLM API credits and GitHub API quota

This is not an oversight to defer — it is a design gap that affects the data model
(`BugTriageState` must carry `owner_id`), the API layer (every endpoint needs a dependency),
and the infrastructure (job registry, token store).

### 1.2 Scope

This PRD specifies:

- GitHub OAuth 2.0 as the sole identity provider (natural fit: product is GitHub-native)
- JWT-based session tokens for all API calls
- The authentication strategy for SSE streams (non-trivial; see §6)
- Per-job authorization (ownership model)
- Secure storage of GitHub OAuth tokens for repo operations
- Token lifecycle and the v1/v2 simplification boundary

---

## 2. Threat Model

### 2.1 Assets Worth Protecting

| Asset | Why It Matters |
|-------|----------------|
| Job output stream | May contain proprietary codebase content, security findings |
| Human-in-the-loop interrupt | Injecting a malicious answer steers the agent toward attacker-controlled output |
| Job lifecycle control (kill/pause) | Denial of service against a legitimate user |
| GitHub OAuth token | Repo read/write access; stored server-side |
| LLM API budget | Unlimited unauthenticated job creation burns operator credits |

### 2.2 In-Scope Threats

| Threat | Vector | Mitigation in This PRD |
|--------|--------|------------------------|
| Unauthenticated job creation | No auth on `POST /jobs` | `Depends(get_current_user)` on all `/jobs/*` |
| Cross-job access (IDOR) | Knowing or guessing a job UUID | Job ownership check on every per-job endpoint |
| UUID enumeration | Job UUIDs are v4 random (122 bits); guessing is computationally infeasible | Defense-in-depth only — ownership check is the primary control |
| Token theft via XSS | JWT in `localStorage` | JWT in `sessionStorage` (v1) / memory + HttpOnly refresh cookie (v2) |
| CSRF on state-mutating endpoints | Cross-origin form/fetch triggering `POST /jobs/{id}/answer` | `SameSite=Strict` on refresh cookie; Bearer token on all REST calls (CSRF requires stolen token, not just cookies) |
| GitHub OAuth token exfiltration | Token in JWT payload (base64-readable) | Token stored encrypted in Redis; only referenced by user ID |
| SSE stream hijack | Attacker opens EventSource to stream URL without auth | Auth required on SSE endpoint; see §6 |

### 2.3 Out-of-Scope Threats (not in v1)

- Compromised server / database — infrastructure-layer concern
- Brute-force of GitHub OAuth state parameter — mitigated by GitHub's own rate limiting
- Stolen refresh tokens — addressed in v2 (refresh token rotation)
- LLM prompt injection via authenticated user — separate concern (content moderation)

---

## 3. Identity Provider: GitHub OAuth 2.0

### 3.1 Why GitHub OAuth

- The product is GitHub-native: users connect GitHub repos, submit GitHub issues, and write back GitHub comments
- No need for a separate user database — GitHub identity (`github_id`, `login`) is the authoritative user record
- Users already have GitHub accounts by definition (PRD-001 §12)
- GitHub's OAuth flow is standard, well-documented, and handles MFA transparently

### 3.2 OAuth Application Scopes

Request the minimum scopes at authorization time:

| Scope | Why Required |
|-------|-------------|
| `read:user` | Get user identity: `id`, `login`, `name`, `avatar_url` |
| `repo` | Read issues and write comments on private and public repos |

> If the target repository is always public and write-back is not required, `repo` can be dropped
> to reduce the permission surface. v1 always requests `repo` for full functionality.

### 3.3 OAuth Web Application Flow

```
Browser                     Backend                          GitHub
   │                           │                               │
   │── GET /auth/login ────────►│                               │
   │                           │── redirect 302 ──────────────►│
   │                           │   github.com/login/oauth/     │
   │                           │   authorize?client_id=...     │
   │                           │   &redirect_uri=.../callback  │
   │                           │   &scope=read:user+repo       │
   │                           │   &state=<csrf_nonce>         │
   │                           │                               │
   │                           │◄── redirect with ?code&state ─│
   │◄── redirect 302 ──────────│                               │
   │    to /auth/callback      │                               │
   │                           │                               │
   │── GET /auth/callback ─────►│                               │
   │    ?code=...&state=...    │── POST access_token ─────────►│
   │                           │    (code + client_secret)     │
   │                           │◄── github_access_token ───────│
   │                           │                               │
   │                           │── GET /user (github_token) ──►│
   │                           │◄── {id, login, name, ...} ────│
   │                           │                               │
   │                           │  [store encrypted github_token in Redis]
   │                           │  [issue internal JWT]
   │                           │  [issue one-time auth_code → Redis, 30s TTL]
   │◄── redirect 302 ──────────│                               │
   │    to frontend            │                               │
   │    /auth/callback         │                               │
   │    ?code=<auth_code>      │                               │
   │                           │                               │
   │── POST /auth/token ───────►│                               │
   │    body: {code}           │  [validate auth_code, delete from Redis]
   │                           │  [return JWT + set refresh cookie]
   │◄── {access_token, ...} ───│                               │
```

**Why the one-time auth code step?**

The backend OAuth callback issues a short-lived (30-second, single-use) opaque `auth_code` stored in
Redis, then redirects the browser to the frontend with `?code=<auth_code>`. The frontend immediately
POSTs this code to `POST /auth/token` and receives the JWT. This ensures the JWT itself never appears
in a URL (not in browser history, not in server access logs, not as a URL fragment). The `auth_code`
is single-use and 30-second TTL, limiting its attack window even if a redirect is intercepted.

### 3.4 CSRF State Parameter

The `state` parameter sent to GitHub's authorization endpoint is a securely generated 32-byte random
nonce, stored in the user's session (Redis, 10-minute TTL). On callback, the backend validates that
the returned `state` matches the stored nonce before processing the code. This prevents CSRF attacks
on the OAuth flow itself.

---

## 4. Session & JWT Model

### 4.1 Token Architecture

Two tokens exist per authenticated session:

| Token | Type | Expiry | Storage | Purpose |
|-------|------|--------|---------|---------|
| **Access token** | Signed JWT | 15 minutes | React in-memory (`useRef` / context) | Authenticates all API calls |
| **Refresh token** | Opaque UUID | 7 days | `HttpOnly; Secure; SameSite=Strict` cookie | Silently renews access tokens |

**v1 simplification:** If the refresh flow adds too much complexity for the initial build, v1 may use
an 8-hour JWT stored in `sessionStorage` (survives page refresh within the tab, cleared on tab close).
This is explicitly acknowledged as an XSS risk tradeoff acceptable for a developer-facing internal
tool. The full two-token architecture is the target for v1.1.

### 4.2 JWT Claims

```json
{
  "sub": "1234567",          // GitHub user ID (stable integer, string-encoded)
  "login": "alex-dev",       // GitHub username (for display; not used for authz)
  "iat": 1741305600,         // issued-at (UTC epoch)
  "exp": 1741306500,         // expiry (iat + 900 seconds = 15 minutes)
  "jti": "uuid-v4"           // JWT ID — used for access token revocation if needed
}
```

**What is NOT in the JWT payload:**
- GitHub OAuth token — stored encrypted in Redis (JWT payload is base64-encoded, not encrypted)
- Email — not needed; `sub` (GitHub user ID) is the authoritative identity
- Permissions/roles — v1 has no RBAC; all authenticated users have equal access to their own jobs

### 4.3 Signing Algorithm

**v1: HS256** (HMAC-SHA256 with a shared secret). Simpler key management — one `JWT_SECRET` env var.

**v2: RS256** (RSA-SHA256, asymmetric). Private key signs on backend; public key exposed at
`GET /auth/.well-known/jwks.json` for potential third-party verification. Migrate when the system
scales to multiple backend services that need to verify tokens independently.

```toml
# Environment variables (managed via pydantic-settings — PRD-006)
JWT_SECRET=<64-byte random hex>        # v1
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_SECONDS=900        # 15 minutes
REFRESH_TOKEN_EXPIRE_SECONDS=604800    # 7 days
GITHUB_CLIENT_ID=<from GitHub App settings>
GITHUB_CLIENT_SECRET=<from GitHub App settings>
GITHUB_TOKEN_ENCRYPTION_KEY=<32-byte random hex for AES-256>
```

---

## 5. REST API Authentication

### 5.1 Protected Endpoints

Every `/jobs/*` endpoint requires authentication. The `Depends(get_current_user)` FastAPI dependency
is injected at the router level, not per-endpoint, so new endpoints cannot accidentally be added
without auth.

```python
# routes/jobs.py
from fastapi import APIRouter, Depends
from auth.dependencies import get_current_user
from auth.models import AuthenticatedUser

router = APIRouter(prefix="/jobs", dependencies=[Depends(get_current_user)])

# All routes under this router automatically require authentication.
# The resolved user is injected per-route where ownership checks are needed.

@router.post("/")
async def create_job(
    body: CreateJobRequest,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> JobResponse:
    ...

@router.get("/{job_id}/stream")
async def stream_job(
    job_id: str,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> StreamingResponse:
    ...
```

### 5.2 `get_current_user` Dependency

```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from pydantic import BaseModel

bearer_scheme = HTTPBearer()


class AuthenticatedUser(BaseModel):
    """Resolved identity from a validated JWT."""

    github_id: str      # "sub" claim — GitHub user ID
    github_login: str   # "login" claim — for display only
    jti: str            # JWT ID — for revocation checks if needed


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthenticatedUser:
    """Validate Bearer JWT and return the resolved user.

    Args:
        credentials: Extracted Bearer token from Authorization header.
        settings: Application settings (JWT_SECRET, algorithm).

    Returns:
        Resolved authenticated user from JWT claims.

    Raises:
        HTTPException: 401 if token is missing, expired, or invalid.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
        github_id: str | None = payload.get("sub")
        github_login: str | None = payload.get("login")
        jti: str | None = payload.get("jti")

        if github_id is None or jti is None:
            raise credentials_exception

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise credentials_exception

    return AuthenticatedUser(github_id=github_id, github_login=github_login or "", jti=jti)
```

### 5.3 Auth Endpoints (not under `/jobs/*`)

```
GET  /auth/login          → redirect to GitHub OAuth authorize URL
GET  /auth/callback       → exchange GitHub code, issue auth_code, redirect to frontend
POST /auth/token          → exchange auth_code for {access_token, token_type}
POST /auth/refresh        → exchange refresh cookie for new access_token
POST /auth/logout         → clear refresh cookie, invalidate refresh token in Redis
GET  /auth/me             → return current user info (requires Bearer)
```

---

## 6. SSE Endpoint Authentication

### 6.1 The Problem

The browser's native `EventSource` API (`new EventSource(url)`) does not support setting custom
request headers. This is a hard W3C specification constraint — not a browser quirk. Sending
`Authorization: Bearer <token>` via the `EventSource` constructor is impossible.

Three approaches exist; this PRD selects one and documents the rejected alternatives:

| Approach | Security | Complexity | Selected |
|----------|----------|------------|----------|
| **Fetch-based EventSource** (`@microsoft/fetch-event-source`) | Same as REST Bearer | Low — uniform auth | ✅ **Yes** |
| Short-lived stream ticket (`?t=<token>`) | Token in URL (logs, history) | Medium — extra endpoint | Fallback |
| HttpOnly session cookie | XSS-safe for SSE | High — CSRF on REST, two auth mechanisms | No |

### 6.2 Selected Approach: Fetch-Based EventSource

The React frontend uses `@microsoft/fetch-event-source` instead of the native `EventSource`. This
library implements the SSE protocol on top of the Fetch API, which supports arbitrary headers.

**Frontend (React):**

```typescript
import { fetchEventSource } from "@microsoft/fetch-event-source";

async function streamJob(jobId: string, accessToken: string) {
    await fetchEventSource(`/jobs/${jobId}/stream`, {
        method: "GET",
        headers: {
            Authorization: `Bearer ${accessToken}`,
        },
        onmessage(event) {
            const data = JSON.parse(event.data);
            dispatch(handleStreamEvent(data));
        },
        onerror(err) {
            if (err instanceof Response && err.status === 401) {
                // Token expired mid-stream: refresh token and reconnect
                await refreshAccessToken();
                throw err;  // fetchEventSource retries on throw
            }
        },
    });
}
```

**Backend:** The `GET /jobs/{id}/stream` endpoint authenticates via `Depends(get_current_user)`
identically to all other endpoints. No special handling is needed on the server side.

### 6.3 Fallback: Short-Lived Stream Ticket

If `@microsoft/fetch-event-source` introduces a compatibility issue (e.g., proxy that buffers Fetch
responses but passes `EventSource` connections), the fallback is a stream ticket:

```
POST /jobs/{id}/stream-token        (requires Bearer auth)
→ {"stream_token": "<opaque>", "expires_in": 60}

GET /jobs/{id}/stream?t=<stream_token>   (single-use, 60s window)
```

The stream token is a UUID stored in Redis with a 60-second TTL. It is validated and immediately
deleted when the stream connection is established (single-use). Once the SSE connection is open,
it is authenticated by the open TCP socket — the token is only used for the handshake.

**Fallback is not default** — it is documented here only for operational contingency.

### 6.4 Token Expiry During an Active Stream

Access tokens expire in 15 minutes. An ongoing stream may outlast the token. The frontend handles
this by catching the 401 response in `onerror`, calling `POST /auth/refresh` to get a new access
token, and re-opening the stream (SSE is reconnection-native). The `Last-Event-ID` header is sent
automatically by `fetchEventSource` on reconnect, allowing the backend to resume from the last
delivered event if Redis Pub/Sub history is maintained (v2 concern; v1 accepts potential event loss
on token-expiry reconnect).

---

## 7. Job Ownership & Per-Resource Authorization

### 7.1 The IDOR Risk

Job UUIDs are v4 random (122 bits of entropy). Guessing a UUID is computationally infeasible, but
relying on UUID unpredictability as the sole access control mechanism is security through obscurity
— not authorization. The correct control is: **only the user who created a job can operate on it**.

### 7.2 Job Registry

A lightweight job registry is maintained in Redis alongside the ARQ job queue. On job creation:

```python
# POST /jobs — after enqueuing the ARQ job
await redis.hset(
    f"job_registry:{job_id}",
    mapping={
        "owner_id": current_user.github_id,
        "created_at": datetime.utcnow().isoformat(),
        "status": "queued",
    },
)
await redis.expire(f"job_registry:{job_id}", 7 * 24 * 3600)  # 7-day TTL
```

This allows O(1) ownership checks without loading the full LangGraph checkpoint state from Postgres.

### 7.3 Ownership Check Dependency

```python
async def get_job_and_verify_owner(
    job_id: str,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> str:
    """Fetch job from registry and verify current user is the owner.

    Args:
        job_id: Job UUID from path parameter.
        current_user: Resolved authenticated user.
        redis: Redis connection.

    Returns:
        The validated job_id.

    Raises:
        HTTPException: 404 if job not found, 403 if caller does not own the job.
    """
    registry = await redis.hgetall(f"job_registry:{job_id}")
    if not registry:
        raise HTTPException(status_code=404, detail="Job not found")
    if registry["owner_id"] != current_user.github_id:
        # Return 404, not 403 — do not reveal that the job exists to non-owners
        raise HTTPException(status_code=404, detail="Job not found")
    return job_id
```

**Why 404 instead of 403:** Returning 403 confirms to an attacker that a job with that UUID exists.
Returning 404 reveals nothing about existence.

### 7.4 BugTriageState Schema Change

`BugTriageState` (PRD-003 §3) requires one new field:

```python
class BugTriageState(TypedDict):
    # ... existing fields ...
    owner_id: str   # GitHub user ID; set at job creation; never modified
```

This field is checkpointed with all other state, providing an immutable ownership record in the
LangGraph state history for audit purposes.

### 7.5 Endpoint Authorization Matrix

| Endpoint | Auth | Ownership check | Notes |
|----------|------|-----------------|-------|
| `POST /jobs` | ✅ `get_current_user` | N/A — creates new job | Sets `owner_id` in state + registry |
| `GET /jobs/{id}/stream` | ✅ `get_current_user` | ✅ `get_job_and_verify_owner` | Read-only but contains private data |
| `POST /jobs/{id}/answer` | ✅ `get_current_user` | ✅ `get_job_and_verify_owner` | Critical: injects text into running agent |
| `POST /jobs/{id}/pause` | ✅ `get_current_user` | ✅ `get_job_and_verify_owner` | |
| `DELETE /jobs/{id}` | ✅ `get_current_user` | ✅ `get_job_and_verify_owner` | |
| `GET /auth/me` | ✅ `get_current_user` | N/A | Returns caller's own identity |
| `POST /auth/refresh` | ✅ refresh cookie | N/A | No Bearer needed — cookie carries identity |
| `POST /auth/logout` | ✅ refresh cookie | N/A | |

---

## 8. GitHub OAuth Token Management

### 8.1 What Needs Storing

After the GitHub OAuth callback, the backend holds a GitHub access token (`gho_...`). This token is
used by LangGraph worker nodes when calling the GitHub API (reading issues, writing comments). It
must be accessible at job execution time, which may be hours after the initial login.

### 8.2 Storage: Encrypted in Redis

The GitHub OAuth token is never stored in the JWT payload (JWTs are signed, not encrypted — the
payload is base64-decodable). It is stored encrypted in Redis:

```python
import os
from cryptography.fernet import Fernet

fernet = Fernet(settings.GITHUB_TOKEN_ENCRYPTION_KEY)

async def store_github_token(github_user_id: str, github_token: str, redis: Redis) -> None:
    """Encrypt and store GitHub OAuth token in Redis."""
    encrypted = fernet.encrypt(github_token.encode())
    await redis.setex(
        f"github_token:{github_user_id}",
        7 * 24 * 3600,          # 7-day TTL, matches refresh token lifetime
        encrypted,
    )


async def get_github_token(github_user_id: str, redis: Redis) -> str | None:
    """Retrieve and decrypt GitHub OAuth token from Redis."""
    encrypted = await redis.get(f"github_token:{github_user_id}")
    if encrypted is None:
        return None
    return fernet.decrypt(encrypted).decode()
```

### 8.3 Token Availability in Worker Nodes

The ARQ worker context does not carry the JWT. Worker nodes that need GitHub API access call
`get_github_token(state["owner_id"], redis)` to retrieve the token at execution time:

```python
async def writer_node(state: BugTriageState, ctx: dict) -> dict:
    github_token = await get_github_token(state["owner_id"], ctx["redis"])
    if github_token is None:
        # User's session has expired — skip write-back, include warning in report
        return {"github_comment_draft": None, "status": "completed_no_writeback"}
    # ... post comment to GitHub ...
```

### 8.4 Token Expiry

GitHub OAuth tokens for OAuth Apps do not expire by default. However, GitHub App user tokens
expire after 8 hours (with refresh tokens). v1 uses an OAuth App (non-expiring tokens). v2
migration to GitHub Apps requires implementing the token refresh cycle.

---

## 9. Token Lifecycle

### 9.1 Access Token

| Property | Value |
|----------|-------|
| Type | Signed JWT (HS256) |
| Expiry | 15 minutes |
| Storage | React in-memory (`useRef` in auth context) |
| Lost on | Page refresh (triggers silent refresh via refresh cookie) |
| Revocation | Not supported in v1 (15-min window is the effective revocation delay) |

### 9.2 Refresh Token

| Property | Value |
|----------|-------|
| Type | Opaque UUID v4 |
| Expiry | 7 days |
| Storage | `HttpOnly; Secure; SameSite=Strict` cookie |
| Redis key | `refresh_token:{uuid}` → `{"github_id": "...", "issued_at": "..."}` |
| Revocation | Delete Redis key → immediate revocation |
| Rotation | Not in v1; add on v1.1 (new refresh token issued on every `/auth/refresh` call) |

### 9.3 Silent Token Refresh Flow

On page load and on every `401` response from the API, React calls `POST /auth/refresh`. The
browser automatically sends the HttpOnly refresh cookie; the backend validates it, issues a new
access JWT, and returns it in the response body. React stores the new access token in memory and
retries the failed request.

```typescript
// src/api/client.ts
const api = axios.create({ baseURL: "/api", withCredentials: true });

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401 && !error.config._retry) {
      error.config._retry = true;
      const { data } = await axios.post("/auth/refresh", {}, { withCredentials: true });
      setAccessToken(data.access_token);  // update React context
      error.config.headers.Authorization = `Bearer ${data.access_token}`;
      return api(error.config);
    }
    return Promise.reject(error);
  }
);
```

### 9.4 Logout

`POST /auth/logout`:
1. Delete the refresh token from Redis (immediate revocation)
2. Clear the `refresh_token` cookie (`Set-Cookie: refresh_token=; Max-Age=0; ...`)
3. React clears the in-memory access token

The 15-minute access token window remains valid after logout if the token is extracted, but this
is an accepted tradeoff (no server-side access token revocation in v1).

---

## 10. CORS & Security Headers

### 10.1 CORS Configuration

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_ORIGIN],  # e.g. "http://localhost:5173" in dev
    allow_credentials=True,    # required for refresh token cookie
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
```

`allow_origins` is a strict allowlist — never `["*"]` with `allow_credentials=True` (browsers
reject this combination, and it would negate cookie security).

### 10.2 Security Headers

```python
from starlette.middleware.base import BaseHTTPMiddleware

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-Frame-Options"] = "DENY"
        return response
```

`Strict-Transport-Security` is only meaningful in production (behind HTTPS). In development it
is harmless.

### 10.3 HTTPS

All production traffic terminates TLS at the reverse proxy (nginx / Caddy). The FastAPI app itself
runs on HTTP internally. The `Secure` cookie flag and `SameSite=Strict` on the refresh token
cookie are meaningless without HTTPS, so production deployment must enforce it.

---

## 11. Dependencies & Libraries

### 11.1 Backend (add to `[project.dependencies]` in pyproject.toml)

```toml
"PyJWT>=2.8",           # JWT encode/decode (HS256/RS256)
"cryptography>=42.0",   # Fernet AES-256-GCM for GitHub token encryption
"httpx>=0.27",          # GitHub API calls in OAuth callback (already in deps)
```

No `python-jose` — it is effectively unmaintained. `PyJWT` is the actively maintained standard.

### 11.2 Frontend (add to package.json)

```json
"@microsoft/fetch-event-source": "^2.0.1"
```

`@microsoft/fetch-event-source` (MIT) — Fetch-based SSE client supporting custom headers.
Maintained by Microsoft, used in Azure and VS Code. Drop-in replacement for `EventSource`
with a hook-based API compatible with React.

---

## 12. Implementation Patterns

### 12.1 Auth Router

```python
# src/auth/router.py
from fastapi import APIRouter, Depends, HTTPException, Response, Request
from fastapi.responses import RedirectResponse
import secrets
import httpx
import jwt
from datetime import datetime, timedelta, timezone
from uuid import uuid4

router = APIRouter(prefix="/auth")

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"


@router.get("/login")
async def login(request: Request, redis: Annotated[Redis, Depends(get_redis)]) -> RedirectResponse:
    """Initiate GitHub OAuth flow."""
    state = secrets.token_urlsafe(32)
    await redis.setex(f"oauth_state:{state}", 600, "valid")  # 10-minute window

    params = {
        "client_id": settings.GITHUB_CLIENT_ID,
        "redirect_uri": settings.GITHUB_REDIRECT_URI,
        "scope": "read:user repo",
        "state": state,
    }
    url = GITHUB_AUTHORIZE_URL + "?" + "&".join(f"{k}={v}" for k, v in params.items())
    return RedirectResponse(url)


@router.get("/callback")
async def callback(
    code: str,
    state: str,
    redis: Annotated[Redis, Depends(get_redis)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RedirectResponse:
    """Handle GitHub OAuth callback; issue one-time auth_code."""
    # Validate state (CSRF protection)
    stored = await redis.get(f"oauth_state:{state}")
    if stored is None:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")
    await redis.delete(f"oauth_state:{state}")

    # Exchange code for GitHub token
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            GITHUB_TOKEN_URL,
            data={
                "client_id": settings.GITHUB_CLIENT_ID,
                "client_secret": settings.GITHUB_CLIENT_SECRET,
                "code": code,
            },
            headers={"Accept": "application/json"},
        )
    github_token = token_resp.json().get("access_token")
    if not github_token:
        raise HTTPException(status_code=400, detail="GitHub token exchange failed")

    # Fetch GitHub identity
    async with httpx.AsyncClient() as client:
        user_resp = await client.get(
            GITHUB_USER_URL,
            headers={"Authorization": f"Bearer {github_token}"},
        )
    github_user = user_resp.json()

    # Store encrypted GitHub token
    await store_github_token(str(github_user["id"]), github_token, redis)

    # Issue one-time auth_code for frontend to exchange
    auth_code = secrets.token_urlsafe(32)
    await redis.setex(
        f"auth_code:{auth_code}",
        30,   # 30-second single-use window
        f"{github_user['id']}:{github_user['login']}",
    )

    return RedirectResponse(f"{settings.FRONTEND_ORIGIN}/auth/callback?code={auth_code}")


@router.post("/token")
async def exchange_token(
    body: AuthCodeRequest,
    response: Response,
    redis: Annotated[Redis, Depends(get_redis)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AccessTokenResponse:
    """Exchange one-time auth_code for access + refresh tokens."""
    value = await redis.getdel(f"auth_code:{body.code}")  # single-use: fetch and delete atomically
    if value is None:
        raise HTTPException(status_code=400, detail="Invalid or expired auth code")

    github_id, github_login = value.split(":", 1)

    # Issue access token
    jti = str(uuid4())
    access_token = jwt.encode(
        {
            "sub": github_id,
            "login": github_login,
            "jti": jti,
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(seconds=settings.ACCESS_TOKEN_EXPIRE_SECONDS),
        },
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )

    # Issue refresh token
    refresh_token = str(uuid4())
    await redis.setex(
        f"refresh_token:{refresh_token}",
        settings.REFRESH_TOKEN_EXPIRE_SECONDS,
        github_id,
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=settings.REFRESH_TOKEN_EXPIRE_SECONDS,
        path="/auth",   # cookie only sent to /auth endpoints
    )

    return AccessTokenResponse(access_token=access_token, token_type="bearer")
```

### 12.2 Protecting a Job Endpoint (Full Example)

```python
@router.get("/{job_id}/stream")
async def stream_job(
    job_id: Annotated[str, Depends(get_job_and_verify_owner)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> StreamingResponse:
    """Stream live agent events for a job.

    Authenticated via Bearer token (Authorization header).
    Ownership verified via job registry in Redis.
    Uses @microsoft/fetch-event-source on the frontend — not native EventSource.
    """
    channel = f"jobs:{job_id}:events"

    async def event_generator() -> AsyncGenerator[str, None]:
        pubsub = redis.pubsub()
        await pubsub.subscribe(channel)
        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                yield f"data: {message['data']}\n\n"
                if json.loads(message["data"]).get("type") == "job.done":
                    break
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

---

## 13. Out of Scope (v1)

| Feature | Rationale for Deferral |
|---------|------------------------|
| **RBAC / roles** | Single-user-per-job model; no shared access or team permissions in v1 |
| **Refresh token rotation** | Adds client complexity; 15-min access token + 7-day non-rotating refresh is acceptable for v1 |
| **Access token revocation** | Requires a Redis token blocklist; 15-min expiry limits the damage window |
| **GitHub App (vs OAuth App)** | GitHub Apps have expiring tokens + finer permission granularity; migration path documented in §8.4 |
| **Multi-user job sharing** | Share a job stream with a colleague — v2 feature requiring explicit ACL |
| **Rate limiting per user** | Prevent a single user from creating thousands of jobs; separate infrastructure concern (API gateway / Redis rate limiter) |
| **Audit log** | Record of who did what to which job; v2 compliance feature |
| **RS256 JWT signing** | Asymmetric keys useful when multiple services verify tokens; overkill for v1 monolith |
