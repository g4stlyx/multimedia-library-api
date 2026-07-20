from __future__ import annotations

import uuid
from datetime import datetime
from pydantic import BaseModel, Field, field_validator

from app.schemas.content import COMMENT_BODY_MAX_LENGTH, validate_required_plain_text


class CommentCreate(BaseModel):
    target_type: str = Field(..., pattern="^(review|list|media)$")
    target_id: uuid.UUID
    parent_comment_id: uuid.UUID | None = None
    body: str = Field(..., min_length=1, max_length=COMMENT_BODY_MAX_LENGTH)

    _validate_body = field_validator("body")(validate_required_plain_text)


class CommentUpdate(BaseModel):
    body: str = Field(..., min_length=1, max_length=COMMENT_BODY_MAX_LENGTH)

    _validate_body = field_validator("body")(validate_required_plain_text)


class CommentPublic(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    target_type: str
    target_id: uuid.UUID
    parent_comment_id: uuid.UUID | None = None
    body: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
