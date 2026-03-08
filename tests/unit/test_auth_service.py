import pytest

from agentops.auth.service import create_access_token, decode_access_token
from agentops.config import Settings


def make_settings() -> Settings:
    return Settings(
        environment="test",
        jwt_secret="test-secret-at-least-32-chars-long!!",
        jwt_algorithm="HS256",
        access_token_expire_seconds=900,
        github_token_encryption_key="",
    )


def test_create_and_decode_access_token() -> None:
    settings = make_settings()
    token = create_access_token("12345", "testuser", settings)
    payload = decode_access_token(token, settings)
    assert payload["sub"] == "12345"
    assert payload["login"] == "testuser"
    assert "jti" in payload
    assert "exp" in payload


def test_token_has_jti() -> None:
    settings = make_settings()
    token1 = create_access_token("123", "user1", settings)
    token2 = create_access_token("123", "user1", settings)
    p1 = decode_access_token(token1, settings)
    p2 = decode_access_token(token2, settings)
    assert p1["jti"] != p2["jti"]  # each token has unique jti


def test_invalid_token_raises() -> None:
    import jwt
    settings = make_settings()
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token("invalid.token.here", settings)
