from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from agentops.api.deps.settings import SettingsDep
from agentops.auth.models import UserInfoResponse
from agentops.auth.service import decode_access_token

_scheme = HTTPBearer()


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_scheme)],
    settings: SettingsDep,
) -> UserInfoResponse:
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
        github_login=str(payload["login"]),
        jti=str(payload["jti"]),
    )


_optional_scheme = HTTPBearer(auto_error=False)


async def get_optional_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_optional_scheme)],
    settings: SettingsDep,
) -> UserInfoResponse | None:
    if credentials is None:
        return None
    try:
        payload = decode_access_token(credentials.credentials, settings)
    except jwt.InvalidTokenError:
        return None
    return UserInfoResponse(
        github_id=str(payload["sub"]),
        github_login=str(payload["login"]),
        jti=str(payload["jti"]),
    )


CurrentUserDep = Annotated[UserInfoResponse, Depends(get_current_user)]
OptionalUserDep = Annotated[UserInfoResponse | None, Depends(get_optional_user)]
