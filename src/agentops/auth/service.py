import uuid
from datetime import UTC, datetime, timedelta

import jwt
from cryptography.fernet import Fernet

from agentops.config import Settings


def create_access_token(github_id: str, github_login: str, settings: Settings) -> str:
    """Create a JWT access token with sub, login, jti, iat, exp."""
    now = datetime.now(UTC)
    payload = {
        "sub": github_id,
        "login": github_login,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + timedelta(seconds=settings.access_token_expire_seconds),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str, settings: Settings) -> dict[str, object]:
    """Decode and validate a JWT access token (30s leeway per PRD-008-1 §10)."""
    return jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        leeway=timedelta(seconds=30),
        options={"require": ["exp", "sub", "iat"]},
    )


def encrypt_github_token(token: str, settings: Settings) -> str:
    """Encrypt a GitHub OAuth token using Fernet."""
    fernet = Fernet(settings.github_token_encryption_key.encode())
    return fernet.encrypt(token.encode()).decode()


def decrypt_github_token(encrypted: str, settings: Settings) -> str:
    """Decrypt a GitHub OAuth token."""
    fernet = Fernet(settings.github_token_encryption_key.encode())
    return fernet.decrypt(encrypted.encode()).decode()
