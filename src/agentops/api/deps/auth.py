from typing import Annotated

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
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_access_token(credentials.credentials, settings)
    return UserInfoResponse(
        github_id=payload["sub"],
        github_login=payload["login"],
    )


CurrentUserDep = Annotated[UserInfoResponse, Depends(get_current_user)]
