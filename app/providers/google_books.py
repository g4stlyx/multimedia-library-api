from __future__ import annotations

import asyncio
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.media import MediaType
from app.providers.base import BaseProviderAdapter, ProviderMediaDetails, ProviderSearchResult, ProviderSeedPage
from app.providers.http import ProviderError, ProviderHttpClient
from app.providers.tmdb import extract_year, parse_date


class GoogleBooksProviderAdapter(BaseProviderAdapter):
    BASE_URL = "https://www.googleapis.com/books/v1"
    ATTRIBUTION_TEXT = "Data provided by Google Books"
    ATTRIBUTION_URL = "https://books.google.com/"

    def __init__(self, api_key: str | None, settings: Settings, db: Session | None = None) -> None:
        self.api_key = api_key
        self.client = ProviderHttpClient(provider="google_books", base_url=self.BASE_URL, settings=settings, requests_per_second=2.0, db=db)

    def _request(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        auth_params = {**params}
        if self.api_key:
            auth_params["key"] = self.api_key
        return self.client.request("GET", path, params=auth_params)

    @staticmethod
    def _published_date(volume_info: dict[str, Any]) -> str | None:
        value = volume_info.get("publishedDate")
        if not value:
            return None
        return value if len(value) == 10 else None

    @classmethod
    def _result(cls, item: dict[str, Any]) -> ProviderSearchResult:
        info = item.get("volumeInfo", {})
        published = cls._published_date(info)
        images = info.get("imageLinks", {})
        return ProviderSearchResult(
            provider="google_books", external_id=str(item["id"]), media_type=MediaType.BOOK,
            title=info.get("title") or "Untitled book", original_title=info.get("subtitle"), description=info.get("description"),
            release_date=parse_date(published), release_year=extract_year(info.get("publishedDate")), primary_language=info.get("language"),
            poster_url=images.get("thumbnail") or images.get("smallThumbnail"), popularity_score=None,
            external_url=info.get("infoLink"), attribution_text=cls.ATTRIBUTION_TEXT, attribution_url=cls.ATTRIBUTION_URL, metadata_json=item,
        )

    async def search(self, query: str, media_type: MediaType, limit: int = 20) -> list[ProviderSearchResult]:
        if media_type != MediaType.BOOK:
            return []
        data = await asyncio.to_thread(self._request, "/volumes", {"q": query, "maxResults": min(limit, 40), "printType": "books"})
        return [self._result(item) for item in data.get("items", []) if item.get("id")]

    async def get_details(self, external_id: str, media_type: MediaType) -> ProviderMediaDetails:
        if media_type != MediaType.BOOK:
            raise ProviderError("Google Books only supports books")
        data = await asyncio.to_thread(self._request, f"/volumes/{external_id}", {})
        info = data.get("volumeInfo", {})
        published = self._published_date(info)
        image = (info.get("imageLinks") or {}).get("thumbnail")
        identifiers = [
            {"provider": "isbn_13" if identifier.get("type") == "ISBN_13" else "isbn_10", "external_id": identifier["identifier"]}
            for identifier in info.get("industryIdentifiers", []) if identifier.get("type") in {"ISBN_10", "ISBN_13"} and identifier.get("identifier")
        ]
        return ProviderMediaDetails(
            provider="google_books", external_id=str(data["id"]), media_type=MediaType.BOOK, title=info.get("title") or "Untitled book",
            original_title=info.get("subtitle"), description=info.get("description"), release_date=parse_date(published),
            release_year=extract_year(info.get("publishedDate")), primary_language=info.get("language"), poster_url=image,
            external_url=info.get("infoLink"), attribution_text=self.ATTRIBUTION_TEXT, attribution_url=self.ATTRIBUTION_URL,
            additional_external_ids=identifiers, genres=[str(item) for item in info.get("categories", [])],
            images=[{"image_type": "poster", "url": image}] if image else [], metadata_json=data,
        )

    async def get_seed_page(self, *, seed_kind: str, media_type: MediaType, cursor: str | None = None, limit: int = 20) -> ProviderSeedPage:
        if media_type != MediaType.BOOK:
            raise ProviderError("Google Books only supports book seeding")
        start_index = max(int(cursor or "0"), 0)
        query = {"classics": "subject:fiction", "science": "subject:science", "history": "subject:history"}.get(seed_kind, "subject:fiction")
        data = await asyncio.to_thread(self._request, "/volumes", {"q": query, "startIndex": start_index, "maxResults": min(limit, 40), "printType": "books"})
        results = [self._result(item) for item in data.get("items", []) if item.get("id")]
        return ProviderSeedPage(provider="google_books", media_type=media_type, seed_kind=seed_kind, cursor=str(start_index), next_cursor=str(start_index + len(results)) if results else None, results=results)
