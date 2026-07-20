from __future__ import annotations

import uuid
from datetime import datetime
from pydantic import BaseModel, Field, field_validator

from app.schemas.content import PRIVATE_NOTE_MAX_LENGTH, validate_optional_plain_text
from app.models.media import LibraryStatus
from app.schemas.media import MediaPublic


class LibraryEntryBase(BaseModel):
    status: LibraryStatus = LibraryStatus.PLANNED
    rating_value: int | None = Field(None, ge=1, le=100, description="Rating from 1 to 100")
    progress_value: int | None = Field(None, ge=0)
    progress_total: int | None = Field(None, ge=0)
    progress_unit: str | None = Field(None, max_length=50)
    notes_private: str | None = Field(None, max_length=PRIVATE_NOTE_MAX_LENGTH)
    is_favorite: bool = False

    _validate_notes_private = field_validator("notes_private")(validate_optional_plain_text)


class LibraryEntryCreate(LibraryEntryBase):
    media_id: uuid.UUID


class LibraryEntryUpdate(BaseModel):
    status: LibraryStatus | None = None
    rating_value: int | None = Field(None, ge=1, le=100, description="Rating from 1 to 100")
    progress_value: int | None = Field(None, ge=0)
    progress_total: int | None = Field(None, ge=0)
    progress_unit: str | None = Field(None, max_length=50)
    notes_private: str | None = Field(None, max_length=PRIVATE_NOTE_MAX_LENGTH)
    is_favorite: bool | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    _validate_notes_private = field_validator("notes_private")(validate_optional_plain_text)


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
