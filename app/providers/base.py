from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from pydantic import BaseModel

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
    genres: list[str] = []
    alternate_titles: list[dict] = []  # dict containing title, language, region
    images: list[dict] = []  # dict containing image_type, url, width, height, content_type
    metadata_json: dict | None = None


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
