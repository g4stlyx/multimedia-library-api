from __future__ import annotations

import uuid
from datetime import datetime
from pydantic import BaseModel, Field


class CommentCreate(BaseModel):
    target_type: str = Field(..., pattern="^(review|list|media)$")
    target_id: uuid.UUID
    parent_comment_id: uuid.UUID | None = None
    body: str = Field(..., min_length=1)


class CommentUpdate(BaseModel):
    body: str = Field(..., min_length=1)


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
