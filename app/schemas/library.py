from __future__ import annotations

import uuid
from datetime import datetime
from pydantic import BaseModel, Field

from app.models.media import LibraryStatus
from app.schemas.media import MediaPublic


class LibraryEntryBase(BaseModel):
    status: LibraryStatus = LibraryStatus.PLANNED
    rating_value: int | None = Field(None, ge=1, le=100, description="Rating from 1 to 100")
    progress_value: int | None = Field(None, ge=0)
    progress_total: int | None = Field(None, ge=0)
    progress_unit: str | None = Field(None, max_length=50)
    notes_private: str | None = None
    is_favorite: bool = False


class LibraryEntryCreate(LibraryEntryBase):
    media_id: uuid.UUID


class LibraryEntryUpdate(BaseModel):
    status: LibraryStatus | None = None
    rating_value: int | None = Field(None, ge=1, le=100, description="Rating from 1 to 100")
    progress_value: int | None = Field(None, ge=0)
    progress_total: int | None = Field(None, ge=0)
    progress_unit: str | None = Field(None, max_length=50)
    notes_private: str | None = None
    is_favorite: bool | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class LibraryEntryPublic(LibraryEntryBase):
    id: uuid.UUID
    user_id: uuid.UUID
    media_id: uuid.UUID
    started_at: datetime | None = None
    completed_at: datetime | None = None
    source: str | None = None
    created_at: datetime
    updated_at: datetime
    media: MediaPublic | None = None

    model_config = {"from_attributes": True}
