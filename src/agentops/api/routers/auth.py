"""OAuth 2.0 authentication router (GitHub provider)."""

import uuid

import httpx
from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse

from agentops.api.deps.auth import CurrentUserDep
from agentops.api.deps.redis import RedisDep
from agentops.api.deps.settings import SettingsDep
from agentops.auth.models import AccessTokenResponse, AuthCodeRequest, UserInfoResponse
from agentops.auth.service import create_access_token, encrypt_github_token

router = APIRouter(prefix="/auth", tags=["auth"])

_GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
_GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"  # noqa: S105
_GITHUB_USER_URL = "https://api.github.com/user"

_CSRF_STATE_TTL = 600  # 10 minutes
_AUTH_CODE_TTL = 300  # 5 minutes
_GITHUB_TOKEN_TTL = 365 * 24 * 3600  # 365 days (PRD-008-1 §5)


@router.get("/login")
async def login(settings: SettingsDep, redis: RedisDep) -> RedirectResponse:
    """Redirect to GitHub OAuth login with CSRF state param."""
    state = str(uuid.uuid4())
    await redis.setex(f"oauth_state:{state}", _CSRF_STATE_TTL, "1")

    params = (
        f"client_id={settings.github_client_id}"
        f"&redirect_uri={settings.github_redirect_uri}"
        f"&scope=read:user repo"
        f"&state={state}"
    )
    return RedirectResponse(url=f"{_GITHUB_AUTHORIZE_URL}?{params}")


@router.get("/callback")
async def callback(
    code: str,
    state: str,
    redis: RedisDep,
    settings: SettingsDep,
) -> RedirectResponse:
    """Handle GitHub OAuth callback — verify CSRF state and exchange code."""
    # Verify CSRF state
    state_key = f"oauth_state:{state}"
    stored = await redis.get(state_key)
    if stored is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or expired OAuth state",
        )
    await redis.delete(state_key)

    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            _GITHUB_TOKEN_URL,
            headers={"Accept": "application/json"},
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": code,
            },
        )
        token_response.raise_for_status()
        token_data = token_response.json()

        if "error" in token_data:
            description = token_data.get("error_description", token_data["error"])
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"GitHub OAuth error: {description}",
            )

        github_access_token: str = token_data.get("access_token", "")
        if not github_access_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="GitHub OAuth token exchange returned no access token",
            )

        user_response = await client.get(
            _GITHUB_USER_URL,
            headers={"Authorization": f"Bearer {github_access_token}"},
        )
        user_response.raise_for_status()
        user_data = user_response.json()

    github_id = str(user_data["id"])
    github_login: str = user_data["login"]

    # Store encrypted GitHub token (PRD-008-1 §5 — 365-day TTL)
    if settings.github_token_encryption_key and github_access_token:
        encrypted = encrypt_github_token(github_access_token, settings)
        await redis.setex(f"github_token:{github_id}", _GITHUB_TOKEN_TTL, encrypted)

    # Generate one-time auth code
    auth_code = str(uuid.uuid4())
    await redis.setex(f"auth_code:{auth_code}", _AUTH_CODE_TTL, f"{github_id}:{github_login}")

    return RedirectResponse(url=f"{settings.frontend_origin}/auth/callback?code={auth_code}")


@router.post("/token", response_model=AccessTokenResponse)
async def exchange_token(
    body: AuthCodeRequest,
    response: Response,
    redis: RedisDep,
    settings: SettingsDep,
) -> AccessTokenResponse:
    """Exchange one-time auth code for JWT + refresh token cookie."""
    auth_code_key = f"auth_code:{body.code}"
    stored = await redis.get(auth_code_key)
    if stored is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired auth code",
        )

    await redis.delete(auth_code_key)
    parts = stored.split(":", 1)
    github_id = parts[0]
    github_login = parts[1] if len(parts) > 1 else ""

    access_token = create_access_token(github_id, github_login, settings)

    # Create refresh token in Redis
    refresh_token_id = str(uuid.uuid4())
    refresh_key = f"refresh_token:{refresh_token_id}"
    await redis.setex(
        refresh_key, settings.refresh_token_expire_seconds, f"{github_id}:{github_login}"
    )

    # Set cookie with path="/auth" (PRD-008-1 §7)
    secure_cookie = settings.environment not in ("development", "test")
    response.set_cookie(
        key="refresh_token",
        value=refresh_token_id,
        httponly=True,
        secure=secure_cookie,
        samesite="strict",
        max_age=settings.refresh_token_expire_seconds,
        path="/auth",
    )

    return AccessTokenResponse(
        access_token=access_token,
        expires_in=settings.access_token_expire_seconds,
    )


@router.post("/refresh", response_model=AccessTokenResponse)
async def refresh_token(
    request: Request,
    redis: RedisDep,
    settings: SettingsDep,
) -> AccessTokenResponse:
    """Refresh access token using refresh cookie."""
    refresh_token_id = request.cookies.get("refresh_token")
    if not refresh_token_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No refresh token",
        )

    refresh_key = f"refresh_token:{refresh_token_id}"
    stored = await redis.get(refresh_key)
    if stored is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    parts = stored.split(":", 1)
    github_id = parts[0]
    github_login = parts[1] if len(parts) > 1 else ""

    access_token = create_access_token(github_id, github_login, settings)

    return AccessTokenResponse(
        access_token=access_token,
        expires_in=settings.access_token_expire_seconds,
    )


@router.get("/me", response_model=UserInfoResponse)
async def me(current_user: CurrentUserDep) -> UserInfoResponse:
    """Get current user info from JWT via CurrentUserDep."""
    return current_user


@router.delete("/logout")
async def logout(
    request: Request,
    response: Response,
    redis: RedisDep,
) -> dict[str, str]:
    """Delete refresh token from Redis and clear cookie."""
    refresh_token_id = request.cookies.get("refresh_token")
    if refresh_token_id:
        await redis.delete(f"refresh_token:{refresh_token_id}")

    response.delete_cookie("refresh_token", path="/auth")
    return {"status": "logged_out"}


@router.delete("/github-token")
async def delete_github_token(
    current_user: CurrentUserDep,
    redis: RedisDep,
) -> dict[str, str]:
    """Delete encrypted GitHub token from Redis."""
    await redis.delete(f"github_token:{current_user.github_id}")
    return {"status": "github_token_deleted"}
