from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from pydantic import BaseModel, Field

from app.models.media import MediaType


class ProviderSearchResult(BaseModel):
    provider: str
    external_id: str
    media_type: MediaType
    title: str
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
    external_url: str | None = None
    attribution_text: str | None = None
    attribution_url: str | None = None
    metadata_json: dict | None = None


class ProviderMediaDetails(BaseModel):
    provider: str
    external_id: str
    media_type: MediaType
    title: str
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
    imdb_id: str | None = None
    external_url: str | None = None
    attribution_text: str | None = None
    attribution_url: str | None = None
    additional_external_ids: list[dict] = Field(default_factory=list)  # provider, external_id, external_url
    genres: list[str] = Field(default_factory=list)
    alternate_titles: list[dict] = Field(default_factory=list)  # dict containing title, language, region
    images: list[dict] = Field(default_factory=list)  # dict containing image_type, url, width, height, content_type
    metadata_json: dict | None = None


class ProviderSeedPage(BaseModel):
    provider: str
    media_type: MediaType
    seed_kind: str
    cursor: str | None = None
    next_cursor: str | None = None
    results: list[ProviderSearchResult] = Field(default_factory=list)


class BaseProviderAdapter(ABC):
    @abstractmethod
    async def search(
        self,
        query: str,
        media_type: MediaType,
        limit: int = 20,
    ) -> list[ProviderSearchResult]:
        pass

    @abstractmethod
    async def get_details(
        self,
        external_id: str,
        media_type: MediaType,
    ) -> ProviderMediaDetails:
        pass

    async def get_seed_page(
        self,
        *,
        seed_kind: str,
        media_type: MediaType,
        cursor: str | None = None,
        limit: int = 20,
    ) -> ProviderSeedPage:
        raise NotImplementedError(f"{type(self).__name__} does not support seeding")
