from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.models.media import MediaType


class GenrePublic(BaseModel):
    id: uuid.UUID
    name: str
    normalized_name: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MediaPublic(BaseModel):
    id: uuid.UUID
    media_type: MediaType
    canonical_title: str
    normalized_title: str
    original_title: str | None = None
    description: str | None = None
    release_date: date | None = None
    release_year: int | None = None
    runtime_minutes: int | None = None
    primary_language: str | None = None
    country_code: str | None = None
    poster_url: str | None = None
    backdrop_url: str | None = None
    popularity_score: float | None = None
    genres: list[GenrePublic] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MediaSearchResponse(BaseModel):
    id: uuid.UUID | None = None  # None if not yet persisted locally
    media_type: MediaType
    canonical_title: str
    normalized_title: str
    original_title: str | None = None
    description: str | None = None
    release_date: date | None = None
    release_year: int | None = None
    runtime_minutes: int | None = None
    primary_language: str | None = None
    country_code: str | None = None
    poster_url: str | None = None
    backdrop_url: str | None = None
    popularity_score: float | None = None
    provider: str | None = None  # Provider source (e.g. 'tmdb') if external
    external_id: str | None = None  # Provider external ID if external
    is_persisted: bool = False

    model_config = {"from_attributes": True}


class MediaExternalAddRequest(BaseModel):
    provider: str = Field(..., min_length=2, max_length=50)
    external_id: str = Field(..., min_length=1, max_length=255)
    media_type: MediaType
