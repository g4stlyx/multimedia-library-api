from __future__ import annotations

import uuid
from datetime import datetime
from pydantic import BaseModel, Field

from app.schemas.media import MediaPublic


class ReviewBase(BaseModel):
    rating_value: int | None = Field(None, ge=1, le=100, description="Rating from 1 to 100")
    body: str | None = None
    contains_spoilers: bool = False
    visibility: str = Field("public", pattern="^(public|followers|private)$")


class ReviewCreate(ReviewBase):
    media_id: uuid.UUID


class ReviewUpdate(BaseModel):
    rating_value: int | None = Field(None, ge=1, le=100, description="Rating from 1 to 100")
    body: str | None = None
    contains_spoilers: bool | None = None
    visibility: str | None = Field(None, pattern="^(public|followers|private)$")


class ReviewPublic(ReviewBase):
    id: uuid.UUID
    user_id: uuid.UUID
    media_id: uuid.UUID
    like_count: int
    comment_count: int
    created_at: datetime
    updated_at: datetime
    media: MediaPublic | None = None

    model_config = {"from_attributes": True}
