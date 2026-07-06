from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError, VerificationError
from argon2.low_level import Type
from jwt import InvalidTokenError

from app.core.config import Settings

JWT_ALGORITHM = "HS256"
PASSWORD_HASH_ALGORITHM = "argon2id"

password_hasher = PasswordHasher(
    time_cost=2,
    memory_cost=19 * 1024,
    parallelism=1,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def generate_opaque_token() -> str:
    return secrets.token_urlsafe(48)


def generate_uuid() -> uuid.UUID:
    return uuid.uuid4()


def hash_with_secret(value: str, secret: str) -> str:
    return hmac.new(
        secret.encode("utf-8"),
        value.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def hash_token(token: str, settings: Settings) -> str:
    return hash_with_secret(token, settings.jwt_secret_key)


def hash_auth_identifier(identifier: str, settings: Settings) -> str:
    return hash_with_secret(identifier.strip().casefold(), settings.password_pepper)


def hash_user_agent(user_agent: str | None, settings: Settings) -> str | None:
    if not user_agent:
        return None
    return hash_with_secret(user_agent, settings.password_pepper)


def _peppered_password(password: str, settings: Settings) -> str:
    return hash_with_secret(password, settings.password_pepper)


def hash_password(password: str, settings: Settings) -> str:
    return password_hasher.hash(_peppered_password(password, settings))


def verify_password(password: str, password_hash: str, settings: Settings) -> bool:
    try:
        return password_hasher.verify(password_hash, _peppered_password(password, settings))
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    return password_hasher.check_needs_rehash(password_hash)


def password_hash_params() -> dict[str, Any]:
    return {
        "time_cost": password_hasher.time_cost,
        "memory_cost": password_hasher.memory_cost,
        "parallelism": password_hasher.parallelism,
        "hash_len": password_hasher.hash_len,
        "salt_len": password_hasher.salt_len,
    }


def create_access_token(
    *,
    user_id: uuid.UUID,
    role: str,
    admin_level: int | None,
    settings: Settings,
) -> tuple[str, datetime, str]:
    now = utcnow()
    expires_at = now + timedelta(minutes=settings.jwt_access_ttl_minutes)
    jti = str(generate_uuid())
    payload = {
        "sub": str(user_id),
        "role": role,
        "admin_level": admin_level,
        "jti": jti,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=JWT_ALGORITHM)
    return token, expires_at, jti


def decode_access_token(token: str, settings: Settings) -> dict[str, Any]:
    payload = jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[JWT_ALGORITHM],
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
        options={
            "require": ["aud", "exp", "iat", "iss", "jti", "sub", "type"],
        },
    )
    if payload.get("type") != "access":
        raise InvalidTokenError("invalid token type")
    return payload
