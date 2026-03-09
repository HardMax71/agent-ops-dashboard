"""Authentication dependencies for FastAPI routes."""

from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from agentops.api.deps.settings import SettingsDep
from agentops.auth.models import UserInfoResponse
from agentops.auth.service import decode_access_token

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    settings: SettingsDep,
) -> UserInfoResponse:
    """Extract and validate the current user from the JWT Bearer token.

    JWT decode exceptions are caught here (infrastructure layer, not business logic).
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_access_token(credentials.credentials, settings)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    return UserInfoResponse(
        github_id=str(payload["sub"]),
        github_login=str(payload.get("login", "")),
        jti=str(payload.get("jti", "")),
    )


async def get_optional_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    settings: SettingsDep,
) -> UserInfoResponse | None:
    """Like get_current_user but returns None when no credentials are present."""
    if credentials is None:
        return None
    try:
        payload = decode_access_token(credentials.credentials, settings)
    except jwt.InvalidTokenError:
        return None
    return UserInfoResponse(
        github_id=str(payload["sub"]),
        github_login=str(payload.get("login", "")),
        jti=str(payload.get("jti", "")),
    )


CurrentUserDep = Annotated[UserInfoResponse, Depends(get_current_user)]
OptionalUserDep = Annotated[UserInfoResponse | None, Depends(get_optional_user)]
