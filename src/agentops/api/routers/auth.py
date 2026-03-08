import uuid

import httpx
from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse

from agentops.api.deps.redis import RedisDep
from agentops.api.deps.settings import SettingsDep
from agentops.auth.models import AccessTokenResponse, UserInfoResponse
from agentops.auth.service import create_access_token, decode_access_token

router = APIRouter(prefix="/auth", tags=["auth"])

_GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
_GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
_GITHUB_USER_URL = "https://api.github.com/user"


@router.get("/login")
async def login(settings: SettingsDep) -> RedirectResponse:
    """Redirect to GitHub OAuth login."""
    params = f"client_id={settings.github_client_id}&redirect_uri={settings.github_redirect_uri}&scope=repo,user"
    return RedirectResponse(url=f"{_GITHUB_AUTHORIZE_URL}?{params}")


@router.get("/callback")
async def callback(code: str, redis: RedisDep, settings: SettingsDep) -> RedirectResponse:
    """Handle GitHub OAuth callback."""
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
        github_access_token = token_data.get("access_token", "")

        user_response = await client.get(
            _GITHUB_USER_URL,
            headers={"Authorization": f"Bearer {github_access_token}"},
        )
        user_response.raise_for_status()
        user_data = user_response.json()

    github_id = str(user_data["id"])
    github_login = user_data["login"]

    # Generate one-time auth code
    auth_code = str(uuid.uuid4())
    auth_code_key = f"auth_code:{auth_code}"
    await redis.setex(auth_code_key, 300, f"{github_id}:{github_login}")

    return RedirectResponse(url=f"{settings.frontend_origin}/auth/callback?code={auth_code}")


@router.post("/token", response_model=AccessTokenResponse)
async def exchange_token(
    request: Request,
    response: Response,
    redis: RedisDep,
    settings: SettingsDep,
) -> AccessTokenResponse:
    """Exchange one-time auth code for JWT + refresh token."""
    body = await request.json()
    auth_code = body.get("code", "")

    auth_code_key = f"auth_code:{auth_code}"
    stored = await redis.get(auth_code_key)
    if stored is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired auth code")

    await redis.delete(auth_code_key)
    parts = stored.split(":", 1)
    github_id = parts[0]
    github_login = parts[1] if len(parts) > 1 else ""

    access_token = create_access_token(github_id, github_login, settings)

    refresh_token_id = str(uuid.uuid4())
    refresh_key = f"refresh_token:{refresh_token_id}"
    await redis.setex(refresh_key, settings.refresh_token_expire_seconds, f"{github_id}:{github_login}")

    response.set_cookie(
        key="refresh_token",
        value=refresh_token_id,
        httponly=True,
        secure=settings.environment != "development",
        samesite="strict",
        max_age=settings.refresh_token_expire_seconds,
    )

    return AccessTokenResponse(
        access_token=access_token,
        expires_in=settings.access_token_expire_seconds,
    )


@router.post("/refresh", response_model=AccessTokenResponse)
async def refresh_token(
    request: Request,
    response: Response,
    redis: RedisDep,
    settings: SettingsDep,
) -> AccessTokenResponse:
    """Refresh access token using refresh cookie."""
    refresh_token_id = request.cookies.get("refresh_token")
    if not refresh_token_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No refresh token")

    refresh_key = f"refresh_token:{refresh_token_id}"
    stored = await redis.get(refresh_key)
    if stored is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")

    parts = stored.split(":", 1)
    github_id = parts[0]
    github_login = parts[1] if len(parts) > 1 else ""

    access_token = create_access_token(github_id, github_login, settings)

    return AccessTokenResponse(
        access_token=access_token,
        expires_in=settings.access_token_expire_seconds,
    )


@router.get("/me", response_model=UserInfoResponse)
async def me(request: Request, settings: SettingsDep) -> UserInfoResponse:
    """Get current user info from JWT."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    token = auth_header[7:]
    payload = decode_access_token(token, settings)
    return UserInfoResponse(
        github_id=payload["sub"],
        github_login=payload["login"],
    )


@router.delete("/logout")
async def logout(request: Request, response: Response, redis: RedisDep) -> dict[str, str]:
    """Logout: delete refresh token and clear cookie."""
    refresh_token_id = request.cookies.get("refresh_token")
    if refresh_token_id:
        await redis.delete(f"refresh_token:{refresh_token_id}")

    response.delete_cookie("refresh_token")
    return {"status": "logged_out"}


@router.delete("/github-token")
async def delete_github_token(request: Request) -> dict[str, str]:
    """Placeholder: delete GitHub OAuth token from DB."""
    return {"status": "github_token_deleted"}
