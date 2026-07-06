from __future__ import annotations

import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.user import UserRole

USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_]{3,32}$")


class UserPublic(BaseModel):
    id: uuid.UUID
    email: str
    username: str
    display_name: str | None
    role: UserRole
    admin_level: int | None
    email_verified_at: datetime | None
    is_active: bool
    is_banned: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RegisterRequest(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=32)
    display_name: str | None = Field(default=None, max_length=80)
    password: str = Field(min_length=12, max_length=1024)

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        value = value.strip()
        if not USERNAME_PATTERN.fullmatch(value):
            raise ValueError("username must be 3-32 characters and contain only letters, numbers, or underscores")
        return value

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        return value or None


class LoginRequest(BaseModel):
    identifier: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class RefreshRequest(BaseModel):
    refresh_token: str | None = Field(default=None, min_length=1, max_length=512)


class LogoutRequest(BaseModel):
    refresh_token: str | None = Field(default=None, min_length=1, max_length=512)


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=1, max_length=512)


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirmRequest(BaseModel):
    token: str = Field(min_length=1, max_length=512)
    new_password: str = Field(min_length=12, max_length=1024)


class AuthTokensResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    access_expires_at: datetime
    access_expires_in: int
    refresh_token: str
    refresh_expires_at: datetime
    refresh_expires_in: int
    user: UserPublic
    email_verification_token: str | None = None


class MessageResponse(BaseModel):
    message: str
    token: str | None = None
