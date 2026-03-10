from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from agentops.api.deps.redis import RedisDep
from agentops.api.deps.settings import SettingsDep
from agentops.auth.service import decode_access_token
from agentops.graphql.types import UserInfo

_scheme = HTTPBearer()


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_scheme)],
    settings: SettingsDep,
    redis: RedisDep,
) -> UserInfo:
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

    jti = str(payload["jti"])
    revoked = await redis.get(f"jti_blacklist:{jti}")
    if revoked is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    github_id = str(payload["sub"])
    avatar_url = await redis.get(f"avatar:{github_id}") or ""
    return UserInfo(
        github_id=github_id,
        github_login=str(payload["login"]),
        avatar_url=avatar_url,
        jti=jti,
    )


_optional_scheme = HTTPBearer(auto_error=False)


async def get_optional_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_optional_scheme)],
    settings: SettingsDep,
    redis: RedisDep,
) -> UserInfo | None:
    if credentials is None:
        return None
    try:
        payload = decode_access_token(credentials.credentials, settings)
    except jwt.InvalidTokenError:
        return None

    jti = str(payload["jti"])
    revoked = await redis.get(f"jti_blacklist:{jti}")
    if revoked is not None:
        return None

    github_id = str(payload["sub"])
    avatar_url = await redis.get(f"avatar:{github_id}") or ""
    return UserInfo(
        github_id=github_id,
        github_login=str(payload["login"]),
        avatar_url=avatar_url,
        jti=jti,
    )


CurrentUserDep = Annotated[UserInfo, Depends(get_current_user)]
OptionalUserDep = Annotated[UserInfo | None, Depends(get_optional_user)]
