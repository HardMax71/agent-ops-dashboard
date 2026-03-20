from typing import TypedDict


class JwtPayload(TypedDict):
    sub: str
    login: str
    jti: str
    iat: int
    exp: int
