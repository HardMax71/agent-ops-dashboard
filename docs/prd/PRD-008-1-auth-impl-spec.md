---
id: PRD-008-1
title: Auth Implementation Spec
status: DRAFT
domain: backend/auth
depends_on: [PRD-008]
parent: PRD-008
---

# PRD-008-1 — Auth Implementation Spec

| Field        | Value                                                                 |
|--------------|-----------------------------------------------------------------------|
| Document ID  | PRD-008-1                                                             |
| Version      | 1.0                                                                   |
| Status       | DRAFT                                                                 |
| Date         | March 2026                                                            |
| Parent Doc   | [PRD-008](PRD-008-authentication.md)                                  |
| Related Docs | [PRD-003](PRD-003-langgraph-orchestration.md), [PRD-006](PRD-006-data-validation.md), [PRD-007](PRD-007-developer-tooling.md) |

---

## 1. Purpose & Scope

This document fills the **10 implementation gaps** in PRD-008 that block building the auth
layer from the parent doc alone. PRD-008 describes *what* the system does; this document
specifies *how* to implement each missing piece.

| Gap | Topic                                                        | Section |
|-----|--------------------------------------------------------------|---------|
| 1   | `POST /auth/refresh` endpoint never implemented              | §2      |
| 2   | Refresh token Redis value format inconsistent                | §2      |
| 3   | Two env vars missing from config table                       | §4      |
| 4   | GitHub token 1-year inactivity revocation undocumented       | §5      |
| 5   | `Content-Security-Policy` absent from SecurityHeadersMiddleware | §6   |
| 6   | `secure=True` cookie drops silently on localhost HTTP        | §7      |
| 7   | GitHub OAuth scope guidance inverted                         | §8      |
| 8   | `@microsoft/fetch-event-source` maintenance status inaccurate | §9    |
| 9   | `AuthCodeRequest`, `AccessTokenResponse`, `UserInfoResponse` never defined | §3 |
| 10  | `jwt.decode` uses zero clock-skew leeway                     | §10     |

**Out of scope:** Inter-service auth (PRD-008 §Inter-Service Authentication is complete),
job ownership checks (complete in PRD-008), SSE stream ticket fallback (complete in PRD-008),
LangSmith integration (PRD-005-1).

---

## 2. `POST /auth/refresh` Implementation (Gaps 1 & 2)

### The Missing Handler

PRD-008 lists `POST /auth/refresh` in the endpoint table and the React axios interceptor calls
it on every 401, but no implementation is shown anywhere in the parent document. Without this
handler the auth system cannot sustain sessions beyond the 15-minute access token window.

```python
# src/auth/router.py  (add after exchange_token)

@router.post("/refresh")
async def refresh_access_token(
    request: Request,
    redis: Annotated[Redis, Depends(get_redis)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AccessTokenResponse:
    """Exchange a valid refresh cookie for a new access token.

    The refresh token cookie is HttpOnly — the browser sends it automatically.
    No rotation in v1: the same refresh token UUID remains valid until it expires
    or is explicitly revoked via POST /auth/logout.

    Raises:
        HTTPException: 401 if the refresh cookie is absent, not found in Redis,
                       or its Redis key has expired.
    """
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No refresh token — please log in",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Redis key format: "refresh_token:{uuid}" → plain github_id string
    github_id = await redis.get(f"refresh_token:{refresh_token}")
    if github_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token expired or revoked — please log in",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # github_id is stored as bytes by redis-py; decode to str
    if isinstance(github_id, bytes):
        github_id = github_id.decode()

    jti = str(uuid4())
    access_token = jwt.encode(
        {
            "sub": github_id,
            "jti": jti,
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc)
            + timedelta(seconds=settings.ACCESS_TOKEN_EXPIRE_SECONDS),
        },
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )

    return AccessTokenResponse(access_token=access_token, token_type="bearer")
```

**Note:** The `login` claim is omitted from the refreshed JWT because the refresh token stores
only `github_id`. This is intentional: `login` is display-only and the frontend can retrieve it
from the initial token or `GET /auth/me`. If `login` is needed in the refreshed token, store
`github_id:github_login` in the Redis refresh key (same pattern as `auth_code` storage).

### Refresh Token Redis Value Format (Gap 2 Correction)

PRD-008's Token Lifecycle table states:

> `refresh_token:{uuid}` → `{"github_id": "...", "issued_at": "..."}`

**This is wrong.** The actual `exchange_token` handler stores:

```python
await redis.setex(f"refresh_token:{refresh_token}", ..., github_id)
```

The value is a **plain `github_id` string** (e.g. `"1234567"`). The `issued_at` field in the
table is never used anywhere and should not be stored. The Token Lifecycle table in PRD-008 §Token
Lifecycle → Refresh Token has been corrected to reflect this.

### Out of Scope: Refresh Token Rotation

v1 does not rotate the refresh token on use. A new UUID is not issued on each `/auth/refresh`
call. The same refresh token UUID remains valid until `REFRESH_TOKEN_EXPIRE_SECONDS` elapses or
until `POST /auth/logout` deletes it from Redis. Rotation (new UUID on every use, old UUID
immediately invalidated) is a v1.1 concern documented in PRD-008 §Out of Scope.

---

## 3. Missing Pydantic Models (Gap 9)

The `/auth/token` handler references `AuthCodeRequest` and `AccessTokenResponse`, and the
`/auth/me` endpoint is listed in PRD-008 but never implemented. All three models and the
`/auth/me` handler are defined here.

### Model Definitions

```python
# src/auth/models.py

from pydantic import BaseModel


class AuthCodeRequest(BaseModel):
    """Body for POST /auth/token — exchange one-time auth code for tokens."""

    code: str


class AccessTokenResponse(BaseModel):
    """Response from POST /auth/token and POST /auth/refresh."""

    access_token: str
    token_type: str = "bearer"


class UserInfoResponse(BaseModel):
    """Response from GET /auth/me — caller's identity from the JWT."""

    github_id: str
    github_login: str
    jti: str
```

### `/auth/me` Implementation

`GET /auth/me` decodes the JWT claims from `get_current_user` and returns them. No Redis or
database call is needed — the claims are already validated by the dependency.

```python
# src/auth/router.py

@router.get("/me")
async def get_me(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> UserInfoResponse:
    """Return the authenticated caller's identity from the validated JWT.

    No external lookup — claims come directly from the Bearer token payload.
    """
    return UserInfoResponse(
        github_id=current_user.github_id,
        github_login=current_user.github_login,
        jti=current_user.jti,
    )
```

---

## 4. Complete Environment Variable Reference (Gap 3)

PRD-008's env var block is missing `GITHUB_REDIRECT_URI` and `FRONTEND_ORIGIN`, both of which
are used in the `login()` and `callback()` handlers shown in the same document. The complete
reference is:

| Variable | Required | Example Value | Description |
|----------|----------|---------------|-------------|
| `JWT_SECRET` | Yes | `<64-byte random hex>` | HMAC-SHA256 signing secret for JWTs |
| `JWT_ALGORITHM` | Yes | `HS256` | JWT signing algorithm |
| `ACCESS_TOKEN_EXPIRE_SECONDS` | Yes | `900` | Access token lifetime (15 minutes) |
| `REFRESH_TOKEN_EXPIRE_SECONDS` | Yes | `604800` | Refresh token lifetime (7 days) |
| `GITHUB_CLIENT_ID` | Yes | `Ov23li...` | GitHub OAuth App client ID |
| `GITHUB_CLIENT_SECRET` | Yes | `<secret>` | GitHub OAuth App client secret |
| `GITHUB_REDIRECT_URI` | Yes | `http://localhost:8000/auth/callback` | OAuth callback URL registered with GitHub |
| `GITHUB_TOKEN_ENCRYPTION_KEY` | Yes | `<Fernet.generate_key() output>` | URL-safe base64, 32 bytes of entropy |
| `FRONTEND_ORIGIN` | Yes | `http://localhost:5173` | Frontend origin for CORS and OAuth redirect |
| `ENVIRONMENT` | Yes | `development` | `development` \| `staging` \| `production`; controls cookie Secure flag (see §7) |
| `INTERNAL_SERVICE_SECRET` | Yes | `<64-byte random hex>` | Shared secret for ARQ worker → agent service calls |

### Generating Secrets

```bash
# JWT_SECRET and INTERNAL_SERVICE_SECRET
python -c "import secrets; print(secrets.token_hex(64))"

# GITHUB_TOKEN_ENCRYPTION_KEY
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### Pydantic Settings Model

```python
# src/config.py

from pydantic_settings import BaseSettings
from typing import Literal


class Settings(BaseSettings):
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_SECONDS: int = 900
    REFRESH_TOKEN_EXPIRE_SECONDS: int = 604800

    GITHUB_CLIENT_ID: str
    GITHUB_CLIENT_SECRET: str
    GITHUB_REDIRECT_URI: str
    GITHUB_TOKEN_ENCRYPTION_KEY: str

    FRONTEND_ORIGIN: str
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"

    INTERNAL_SERVICE_SECRET: str

    class Config:
        env_file = ".env"
```

---

## 5. GitHub Token Lifecycle & 1-Year Inactivity Revocation (Gap 4)

### GitHub's Inactivity Revocation Policy

PRD-008 states: "GitHub OAuth tokens for OAuth Apps do not expire by default." This is technically
correct but critically incomplete. **GitHub automatically revokes any OAuth App token that has not
been used for 1 year.** See [GitHub docs — OAuth token expiration](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/refreshing-user-access-tokens).

This matters because:

1. A user who authenticates once and then returns 12+ months later will have a revoked GitHub
   token in Redis (if the Redis key has not expired — see TTL discussion below).
2. A user whose **GitHub App authorization** is revoked (via GitHub → Settings → Applications →
   Authorized OAuth Apps → Revoke) will have an invalid token immediately.

### GitHub Token TTL Recommendation

PRD-008 stores the GitHub token with `7 * 24 * 3600` (7 days) TTL, matching the refresh token.
This creates a gap: a user who uses the app regularly (renewing their 7-day session) but whose
GitHub token expires from Redis after 7 days will silently lose write-back capability.

**Recommendation:** Set the GitHub token TTL to 365 days (or the maximum practical value). The
token is re-stored on every successful OAuth login, so a user who authenticates at all in a year
keeps it fresh. The 7-day TTL was presumably chosen to match the session, but write-back
operations are independent of session length.

```python
async def store_github_token(github_user_id: str, github_token: str, redis: Redis) -> None:
    """Encrypt and store GitHub OAuth token in Redis."""
    encrypted = fernet.encrypt(github_token.encode())
    await redis.setex(
        f"github_token:{github_user_id}",
        365 * 24 * 3600,   # 365-day TTL — re-stored on every OAuth login
        encrypted,
    )
```

### Handling GitHub API 401 in `POST /jobs/{id}/post-comment`

The current handler in PRD-008 handles `github_token is None` (token not in Redis), but not the
case where the stored token has been revoked by GitHub. A revoked token returns HTTP 401 from the
GitHub API. The full error path:

```python
@router.post("/jobs/{job_id}/post-comment")
async def post_comment(
    job_id: Annotated[str, Depends(get_job_and_verify_owner)],
    body: PostCommentRequest,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> PostCommentResponse:
    github_token = await get_github_token(current_user.github_id, redis)
    if github_token is None:
        raise HTTPException(
            status_code=401,
            detail="GitHub session expired — re-authenticate",
        )

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"https://api.github.com/repos/{body.owner}/{body.repo}/issues/{body.issue_number}/comments",
            json={"body": body.comment},
            headers={
                "Authorization": f"Bearer {github_token}",
                "Accept": "application/vnd.github+json",
            },
        )

    if resp.status_code == 401:
        # GitHub token was revoked (user removed app authorization or 1-year inactivity).
        # Delete the stale token so future calls fail fast with the cleaner "None" path.
        await redis.delete(f"github_token:{current_user.github_id}")
        raise HTTPException(
            status_code=401,
            detail="GitHub authorization revoked — re-authenticate via GitHub OAuth",
        )

    if not resp.is_success:
        raise HTTPException(
            status_code=502,
            detail=f"GitHub API error: {resp.status_code}",
        )

    return PostCommentResponse(comment_url=resp.json()["html_url"])
```

### Re-Authentication Flow

When `POST /jobs/{id}/post-comment` returns `401 GitHub authorization revoked`, the frontend
should:

1. Display a banner: "Your GitHub authorization has expired. Re-connect to post comments."
2. Provide a "Re-connect GitHub" button that initiates `GET /auth/login` (full OAuth flow).
3. On successful re-auth, the GitHub token is re-stored with a fresh 365-day TTL.

The user's session (JWT + refresh token) remains valid throughout — only the GitHub token needs
renewal. Do **not** call `DELETE /auth/github-token` here; that endpoint is for intentional
disconnection.

---

## 6. Content-Security-Policy (Gap 5)

### Why CSP is Critical Here

PRD-008's threat model names XSS as the vector for JWT theft from in-memory storage. The
`SecurityHeadersMiddleware` sets four headers but omits `Content-Security-Policy`. Without CSP,
an injected script can freely exfiltrate the in-memory access token, defeating the JWT storage
decision.

### CSP Value for Production

```
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https://avatars.githubusercontent.com; connect-src 'self'; frame-ancestors 'none'
```

Breakdown:

| Directive | Value | Rationale |
|-----------|-------|-----------|
| `default-src` | `'self'` | Deny all unlisted resource types from external origins |
| `script-src` | `'self'` | No inline scripts, no external script CDNs |
| `style-src` | `'self' 'unsafe-inline'` | React/Vite injects inline styles; tighten in v2 with nonce |
| `img-src` | `'self' data: https://avatars.githubusercontent.com` | GitHub avatar images |
| `connect-src` | `'self'` | API + SSE calls go to the same origin |
| `frame-ancestors` | `'none'` | Redundant with `X-Frame-Options: DENY` but defense-in-depth |

### Swagger UI Carve-Out

FastAPI's `/docs` and `/redoc` endpoints require `unsafe-inline` and `unsafe-eval` for their
bundled JavaScript. Two options:

- **Option A (recommended for v1):** Disable Swagger in production via `app = FastAPI(docs_url=None, redoc_url=None)` when `ENVIRONMENT == "production"`. PRD-009 (Documentation Standards) governs whether interactive docs are exposed in production.
- **Option B:** Apply a path-specific relaxed CSP only to `/docs` and `/redoc` by checking `request.url.path` in the middleware.

### Updated `SecurityHeadersMiddleware`

```python
from starlette.middleware.base import BaseHTTPMiddleware

PRODUCTION_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: https://avatars.githubusercontent.com; "
    "connect-src 'self'; "
    "frame-ancestors 'none'"
)

# Relaxed CSP for Swagger UI paths (Option B — only if docs are kept in production)
DOCS_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "connect-src 'self'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-Frame-Options"] = "DENY"

        # Apply relaxed CSP to Swagger/ReDoc paths; strict CSP everywhere else
        if request.url.path in ("/docs", "/redoc", "/openapi.json"):
            response.headers["Content-Security-Policy"] = DOCS_CSP
        else:
            response.headers["Content-Security-Policy"] = PRODUCTION_CSP

        return response
```

---

## 7. Cookie Secure Flag & Local Development (Gap 6)

### The Problem

`response.set_cookie(..., secure=True)` causes browsers to silently drop the cookie over HTTP.
In local development (localhost without HTTPS), the backend sets the cookie and returns 200, but
the browser never stores it. The result: the user can log in, but every page refresh forces
re-login because the refresh token cookie is never sent back.

This fails silently — there is no error in the browser console unless DevTools Network tab is
inspected carefully.

### Fix: Conditional Secure Flag

```python
response.set_cookie(
    key="refresh_token",
    value=refresh_token,
    httponly=True,
    secure=settings.ENVIRONMENT == "production",   # False in development
    samesite="strict",
    max_age=settings.REFRESH_TOKEN_EXPIRE_SECONDS,
    path="/auth",
)
```

The `ENVIRONMENT` env var (defined in §4) drives this decision. In `staging`, the cookie should
also use `secure=True` if staging is served over HTTPS.

Updated logic:

```python
secure_cookie = settings.ENVIRONMENT in ("staging", "production")
response.set_cookie(
    key="refresh_token",
    value=refresh_token,
    httponly=True,
    secure=secure_cookie,
    samesite="strict",
    max_age=settings.REFRESH_TOKEN_EXPIRE_SECONDS,
    path="/auth",
)
```

### Alternative: HTTPS on Localhost

If the team prefers to always use `secure=True` (keeping prod/dev parity), configure local HTTPS
using [mkcert](https://github.com/FiloSottile/mkcert) + Caddy. PRD-007 (Developer Tooling) is
the right place to document the local HTTPS setup if this path is chosen. Either approach is
valid; the conditional `ENVIRONMENT` flag is simpler for solo developers.

---

## 8. GitHub OAuth Scope Minimization (Gap 7)

### Corrected Guidance

PRD-008 states:

> "If the target repository is always public and write-back is not required, `repo` can be
> dropped to reduce the permission surface."

This is **backwards.** `repo` grants full read/write access to all private repositories the user
can access — a significant over-permission for a tool that only needs to comment on issues.
`public_repo` is the correct minimum scope for public repositories.

### Decision Table

| Repository visibility | Required operations | Recommended scope |
|-----------------------|---------------------|-------------------|
| Public only | Read issues, write comments | `read:user public_repo` |
| Private (any) | Read issues, write comments | `read:user repo` |
| Mixed / unknown at auth time | Read issues, write comments | `read:user repo` (simplest; explicit tradeoff) |

### v1 Default: `repo` with Documented Tradeoff

v1 always requests `read:user repo` for full private repository support. This is the correct
choice for a tool targeting developers who may work with private repos. The security tradeoff
(broad permission vs. UX simplicity) must be made explicit in the GitHub OAuth consent screen
description and in any user-facing setup documentation.

The scope request in `login()`:

```python
params = {
    "client_id": settings.GITHUB_CLIENT_ID,
    "redirect_uri": settings.GITHUB_REDIRECT_URI,
    # `repo` = private + public repos; `public_repo` = public only.
    # v1 requests `repo` for full functionality. See PRD-008-1 §8 for scope tradeoffs.
    "scope": "read:user repo",
    "state": state,
}
```

### v2 Path: Scope Selection in Settings

v2 can allow users to choose their repo type in Settings, requesting the minimum scope:

```python
scope = "read:user repo" if settings_page.has_private_repos else "read:user public_repo"
```

This requires storing the scope with the session and handling scope upgrade (re-auth) when a
user switches from public to private repos.

---

## 9. `@microsoft/fetch-event-source` Status & Alternatives (Gap 8)

### Maintenance Reality

PRD-008 describes the library as "maintained by Microsoft, used in Azure and VS Code." The
accurate status as of March 2026:

| Fact | Detail |
|------|--------|
| Last npm release | v2.0.1, April 2021 (5 years ago) |
| Repository | Renamed from `microsoft/fetch-event-source` → `Azure/fetch-event-source` |
| npm weekly downloads | ~1.1M (widely used despite no new releases) |
| Archive status | Not archived; source is stable |
| Open issues/PRs | Unmerged PRs exist; no active maintainer merging them |

The library is functionally correct for the SSE-over-Fetch use case and safe to use. It has not
had a security vulnerability. The risk is the absence of upstream patches for future issues.

### Decision for v1: Use and Pin

```json
"@microsoft/fetch-event-source": "^2.0.1"
```

Accept `^2.0.1` as a stable ceiling. Because npm semver `^` allows minor/patch bumps and the
package has had no releases since 2021, this resolves to exactly `2.0.1` in practice. Treat it
as a vendored dependency: if a bug is found, patch it in a local fork.

### Alternative: `eventsource-parser` + Custom Fetch Wrapper

If `@microsoft/fetch-event-source` needs to be replaced, the actively maintained
`eventsource-parser` package provides the SSE parsing layer. Wrap it with a Fetch call:

```typescript
import { createParser } from "eventsource-parser";

async function streamJob(jobId: string, accessToken: string, onEvent: (data: string) => void) {
    const parser = createParser((event) => {
        if (event.type === "event") onEvent(event.data);
    });

    const response = await fetch(`/jobs/${jobId}/stream`, {
        headers: { Authorization: `Bearer ${accessToken}` },
    });

    if (!response.ok) {
        throw new Error(`Stream request failed: ${response.status}`);
    }

    const reader = response.body!.getReader();
    const decoder = new TextDecoder();

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        parser.feed(decoder.decode(value, { stream: true }));
    }
}
```

This is ~30 lines versus the hook-based API of `@microsoft/fetch-event-source`, and
`eventsource-parser` is actively maintained. The tradeoff is manual retry/reconnect logic
(which `@microsoft/fetch-event-source` handles automatically).

### Alternative: Native `EventSource` + Stream Ticket

The stream ticket fallback documented in PRD-008 §Fallback: Short-Lived Stream Ticket eliminates
the library dependency entirely. Use this if both library options are unacceptable.

---

## 10. JWT Clock Skew Leeway (Gap 10)

### The Problem

`jwt.decode` with no `leeway` parameter defaults to 0 seconds of clock-skew tolerance. In a
multi-replica deployment where API servers have slightly different system clocks, a token issued
on one replica can appear expired on another if the clocks differ by even a few seconds.

### Fix

```python
from datetime import timedelta

payload = jwt.decode(
    token,
    settings.JWT_SECRET,
    algorithms=[settings.JWT_ALGORITHM],
    leeway=timedelta(seconds=30),   # tolerate 30s of clock skew between replicas
)
```

Updated `get_current_user` dependency:

```python
async def get_current_user(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthenticatedUser:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        raise credentials_exception
    token = authorization.removeprefix("Bearer ")
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
            leeway=timedelta(seconds=30),
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

### When This Matters

| Deployment | Risk |
|------------|------|
| Single server, v1 | Negligible — one clock, no skew |
| Multiple replicas behind load balancer | Real — NTP drift between hosts can exceed 5s |
| Kubernetes pod scheduling | Real — pods may run on different nodes with independent NTP sync |

This is a low-severity gap for v1 (single-server), but the 30-second leeway costs nothing and
eliminates a class of mysterious 401s in v1.1 horizontal scaling.

---

## Verification Checklist

- [x] `POST /auth/refresh` implementation shown with full code (§2)
- [x] Refresh token Redis format consistent: plain `github_id` string (§2)
- [x] All env vars used in code snippets appear in the env var table (§4): `GITHUB_REDIRECT_URI`, `FRONTEND_ORIGIN`, `ENVIRONMENT`
- [x] GitHub 1-year inactivity revocation documented with re-auth flow (§5)
- [x] `SecurityHeadersMiddleware` includes `Content-Security-Policy` (§6)
- [x] `set_cookie` Secure flag conditional on `ENVIRONMENT` (§7)
- [x] GitHub scope section correctly recommends `public_repo` vs `repo` (§8)
- [x] `@microsoft/fetch-event-source` maintenance status and alternatives noted (§9)
- [x] `AuthCodeRequest`, `AccessTokenResponse`, `UserInfoResponse` defined (§3)
- [x] `jwt.decode` leeway parameter shown (§10)
- [x] mkdocs.yml has Auth Detail section (see mkdocs.yml)
- [x] PRD-008 has cross-reference block (see PRD-008 §Overview)
