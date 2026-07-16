from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.auth import UserPublic
from app.models.user import UserRole


class AuditLogPublic(BaseModel):
    id: uuid.UUID
    actor_user_id: uuid.UUID | None = None
    action: str
    resource_type: str | None = None
    resource_id: str | None = None
    metadata_json: dict[str, Any] | None = Field(None, serialization_alias="metadata")
    ip_address: str | None = None
    user_agent_hash: str | None = None
    request_id: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True
        populate_by_name = True


class AuthErrorLogPublic(BaseModel):
    id: uuid.UUID
    error_type: str
    email_or_username_hash: str | None = None
    user_id: uuid.UUID | None = None
    ip_address: str | None = None
    user_agent_hash: str | None = None
    request_id: str | None = None
    metadata_json: dict[str, Any] | None = Field(None, serialization_alias="metadata")
    created_at: datetime

    class Config:
        from_attributes = True
        populate_by_name = True


class BackupMetadataPublic(BaseModel):
    id: uuid.UUID
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    size_bytes: int | None = None
    sha256: str | None = None
    storage_key: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MediaMergeInput(BaseModel):
    source_id: uuid.UUID
    target_id: uuid.UUID


class UserModerationInput(BaseModel):
    banned: bool


class UserRoleUpdateInput(BaseModel):
    role: UserRole
    admin_level: int | None = None


class AuditLogListResponse(BaseModel):
    total: int
    items: list[AuditLogPublic]


class AuthErrorListResponse(BaseModel):
    total: int
    items: list[AuthErrorLogPublic]


class UserListResponse(BaseModel):
    total: int
    items: list[UserPublic]


class BackupListResponse(BaseModel):
    total: int
    items: list[BackupMetadataPublic]
