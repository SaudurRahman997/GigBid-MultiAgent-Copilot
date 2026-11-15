"""Password hashing (scrypt), JWT sessions (HS256) and the Fernet-encrypted OAuth token vault."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from datetime import UTC, datetime, timedelta

import jwt
from cryptography.fernet import Fernet, InvalidToken

SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}
COOKIE = "gigbid_session"


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **SCRYPT)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt_b64, digest_b64 = stored.split("$")
        digest = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt_b64), **SCRYPT)
        return hmac.compare_digest(digest, base64.b64decode(digest_b64))
    except (ValueError, TypeError):
        return False


def jwt_secret() -> str:
    return os.environ.get("JWT_SECRET") or "dev-only-secret-change-me-0123456789abcdef"


def issue_token(user_id: str, hours: int = 12) -> str:
    payload = {"sub": user_id, "exp": datetime.now(UTC) + timedelta(hours=hours), "iat": datetime.now(UTC)}
    return jwt.encode(payload, jwt_secret(), algorithm="HS256")


def read_token(token: str) -> str | None:
    try:
        return jwt.decode(token, jwt_secret(), algorithms=["HS256"])["sub"]
    except jwt.PyJWTError:
        return None


class TokenVault:
    """Encrypts OAuth tokens at rest with a Fernet key from the environment (TOKEN_ENCRYPTION_KEY)."""

    def __init__(self, key: str | None = None):
        key = key or os.environ.get("TOKEN_ENCRYPTION_KEY")
        if not key:  # dev fallback derived from the JWT secret, never used when the env key is set
            key = base64.urlsafe_b64encode(hashlib.sha256(jwt_secret().encode()).digest()).decode()
        self.fernet = Fernet(key)

    def seal(self, data: dict) -> str:
        return self.fernet.encrypt(json.dumps(data).encode()).decode()

    def open(self, ciphertext: str) -> dict | None:
        try:
            return json.loads(self.fernet.decrypt(ciphertext.encode()))
        except InvalidToken:
            return None
