from pydantic import BaseModel


class UserInfoResponse(BaseModel):
    github_id: str
    github_login: str


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
