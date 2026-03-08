from pydantic import BaseModel


class AuthCodeRequest(BaseModel):
    code: str


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105
    expires_in: int


class UserInfoResponse(BaseModel):
    github_id: str
    github_login: str
    avatar_url: str = ""
