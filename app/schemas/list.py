from __future__ import annotations

import uuid
from datetime import datetime
from pydantic import BaseModel, Field

from app.schemas.media import MediaPublic


class ListItemBase(BaseModel):
    media_id: uuid.UUID
    note: str | None = None


class ListItemCreate(ListItemBase):
    position: int = Field(..., ge=0)


class ListItemAdd(ListItemBase):
    pass


class ListItemUpdate(BaseModel):
    note: str | None = None


class ListItemReorder(BaseModel):
    media_ids: list[uuid.UUID]


class ListItemPublic(ListItemBase):
    id: uuid.UUID
    list_id: uuid.UUID
    position: int
    created_at: datetime
    media: MediaPublic | None = None

    model_config = {"from_attributes": True}


class ListBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    visibility: str = Field("public", pattern="^(public|followers|private)$")


class ListCreate(ListBase):
    items: list[ListItemCreate] = []


class ListUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    visibility: str | None = Field(None, pattern="^(public|followers|private)$")


class ListPublic(ListBase):
    id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    items: list[ListItemPublic] = []

    model_config = {"from_attributes": True}
