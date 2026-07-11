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


class OpenLibraryProviderAdapter(BaseProviderAdapter):
    BASE_URL = "https://openlibrary.org"
    ATTRIBUTION_TEXT = "Data provided by Open Library"
    ATTRIBUTION_URL = "https://openlibrary.org/"

    def __init__(self, settings: Settings, db: Session | None = None) -> None:
        self.settings = settings
        self.client = ProviderHttpClient(provider="open_library", base_url=self.BASE_URL, settings=settings, requests_per_second=1.0, db=db)

    def _headers(self) -> dict[str, str]:
        user_agent = self.settings.open_library_user_agent
        if not user_agent and self.settings.open_library_contact_email:
            user_agent = f"multi-media-library/1.0 ({self.settings.open_library_contact_email})"
        return {"User-Agent": user_agent or "multi-media-library/1.0"}

    def _request(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        return self.client.request("GET", path, params=params, headers=self._headers())

    @classmethod
    def _result(cls, item: dict[str, Any]) -> ProviderSearchResult:
        work_id = str(item.get("key", "")).removeprefix("/works/")
        if not work_id:
            raise ProviderError("Open Library result is missing a work ID")
        year = item.get("first_publish_year")
        cover_id = item.get("cover_i")
        return ProviderSearchResult(
            provider="open_library", external_id=work_id, media_type=MediaType.BOOK, title=item.get("title") or "Untitled book",
            original_title=(item.get("subtitle") or None), release_year=year if isinstance(year, int) else None,
            primary_language=(item.get("language") or [None])[0], poster_url=f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg" if cover_id else None,
            external_url=f"https://openlibrary.org/works/{work_id}", attribution_text=cls.ATTRIBUTION_TEXT, attribution_url=cls.ATTRIBUTION_URL, metadata_json=item,
        )

    async def search(self, query: str, media_type: MediaType, limit: int = 20) -> list[ProviderSearchResult]:
        if media_type != MediaType.BOOK:
            return []
        data = await asyncio.to_thread(self._request, "/search.json", {"q": query, "limit": min(limit, 100)})
        return [self._result(item) for item in data.get("docs", []) if item.get("key")]

    async def get_details(self, external_id: str, media_type: MediaType) -> ProviderMediaDetails:
        if media_type != MediaType.BOOK:
            raise ProviderError("Open Library only supports books")
        data = await asyncio.to_thread(self._request, f"/works/{external_id}.json", {})
        title = data.get("title") or "Untitled book"
        description = data.get("description")
        if isinstance(description, dict):
            description = description.get("value")
        covers = data.get("covers") or []
        cover = f"https://covers.openlibrary.org/b/id/{covers[0]}-L.jpg" if covers else None
        subject = [str(item) for item in data.get("subjects", [])[:20]]
        return ProviderMediaDetails(
            provider="open_library", external_id=external_id, media_type=MediaType.BOOK, title=title, description=description if isinstance(description, str) else None,
            poster_url=cover, external_url=f"https://openlibrary.org/works/{external_id}", attribution_text=self.ATTRIBUTION_TEXT,
            attribution_url=self.ATTRIBUTION_URL, genres=subject, images=[{"image_type": "poster", "url": cover}] if cover else [], metadata_json=data,
        )

    async def get_seed_page(self, *, seed_kind: str, media_type: MediaType, cursor: str | None = None, limit: int = 20) -> ProviderSeedPage:
        if media_type != MediaType.BOOK:
            raise ProviderError("Open Library only supports book seeding")
        page = max(int(cursor or "1"), 1)
        subject = {"classics": "fiction", "science": "science", "history": "history"}.get(seed_kind, "fiction")
        data = await asyncio.to_thread(self._request, "/search.json", {"subject": subject, "page": page, "limit": min(limit, 100)})
        results = [self._result(item) for item in data.get("docs", []) if item.get("key")]
        return ProviderSeedPage(provider="open_library", media_type=media_type, seed_kind=seed_kind, cursor=str(page), next_cursor=str(page + 1) if results else None, results=results)
