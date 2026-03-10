"""Tests for auth service: JWT and token encryption."""

import jwt
import pytest
from cryptography.fernet import Fernet

from agentops.auth.service import (
    create_access_token,
    decode_access_token,
    decrypt_github_token,
    encrypt_github_token,
)
from agentops.config import Settings


@pytest.fixture
def fernet_key() -> str:
    return Fernet.generate_key().decode()


@pytest.fixture
def auth_settings(fernet_key: str) -> Settings:
    return Settings(
        environment="test",
        jwt_secret="test-placeholder-secret-32characters!!",
        github_token_encryption_key=fernet_key,
        openai_api_key="sk-test",
    )


class TestJWT:
    def test_roundtrip(self, auth_settings: Settings) -> None:
        token = create_access_token("12345", "testuser", auth_settings)
        payload = decode_access_token(token, auth_settings)
        assert payload["sub"] == "12345"
        assert payload["login"] == "testuser"
        assert "jti" in payload
        assert "exp" in payload
        assert "iat" in payload

    def test_unique_jti(self, auth_settings: Settings) -> None:
        t1 = create_access_token("1", "a", auth_settings)
        t2 = create_access_token("1", "a", auth_settings)
        p1 = decode_access_token(t1, auth_settings)
        p2 = decode_access_token(t2, auth_settings)
        assert p1["jti"] != p2["jti"]

    def test_invalid_token_raises(self, auth_settings: Settings) -> None:
        with pytest.raises(jwt.InvalidTokenError):
            decode_access_token("not.a.valid.token", auth_settings)

    def test_wrong_secret_raises(self, auth_settings: Settings) -> None:
        token = create_access_token("1", "a", auth_settings)
        bad_settings = Settings(
            environment="test",
            jwt_secret="different-secret-that-is-32-characters!!",
            openai_api_key="sk-test",
        )
        with pytest.raises(jwt.InvalidTokenError):
            decode_access_token(token, bad_settings)


class TestGitHubTokenEncryption:
    def test_roundtrip(self, auth_settings: Settings) -> None:
        original = "ghp_test_token_12345"
        encrypted = encrypt_github_token(original, auth_settings)
        assert encrypted != original
        decrypted = decrypt_github_token(encrypted, auth_settings)
        assert decrypted == original

    def test_different_tokens_encrypt_differently(self, auth_settings: Settings) -> None:
        e1 = encrypt_github_token("token_a", auth_settings)
        e2 = encrypt_github_token("token_b", auth_settings)
        assert e1 != e2
