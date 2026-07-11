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


class RAWGProviderAdapter(BaseProviderAdapter):
    """Primary MVP game provider. Use only within RAWG's current caching and attribution terms."""

    BASE_URL = "https://api.rawg.io/api"
    ATTRIBUTION_TEXT = "Data provided by RAWG"
    ATTRIBUTION_URL = "https://rawg.io/"

    def __init__(self, api_key: str | None, settings: Settings, db: Session | None = None) -> None:
        self.api_key = api_key
        self.client = ProviderHttpClient(provider="rawg", base_url=self.BASE_URL, settings=settings, requests_per_second=1.0, db=db)

    def _request(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self.api_key:
            raise ProviderError("RAWG API key is not configured")
        return self.client.request("GET", path, params={**params, "key": self.api_key})

    @staticmethod
    def _result(item: dict[str, Any]) -> ProviderSearchResult:
        released = item.get("released")
        return ProviderSearchResult(
            provider="rawg", external_id=str(item["id"]), media_type=MediaType.GAME,
            title=item.get("name") or "Untitled game", release_date=parse_date(released), release_year=extract_year(released),
            poster_url=item.get("background_image"), popularity_score=item.get("added"),
            external_url=item.get("slug") and f"https://rawg.io/games/{item['slug']}", attribution_text=RAWGProviderAdapter.ATTRIBUTION_TEXT,
            attribution_url=RAWGProviderAdapter.ATTRIBUTION_URL, metadata_json=item,
        )

    async def search(self, query: str, media_type: MediaType, limit: int = 20) -> list[ProviderSearchResult]:
        if media_type != MediaType.GAME or not self.api_key:
            return []
        data = await asyncio.to_thread(self._request, "/games", {"search": query, "page_size": min(limit, 40)})
        return [self._result(item) for item in data.get("results", [])[:limit] if item.get("id") is not None]

    async def get_details(self, external_id: str, media_type: MediaType) -> ProviderMediaDetails:
        if media_type != MediaType.GAME:
            raise ProviderError("RAWG only supports games")
        data = await asyncio.to_thread(self._request, f"/games/{external_id}", {})
        released = data.get("released")
        stores = [store.get("store", {}).get("url") for store in data.get("stores", []) if store.get("store", {}).get("url")]
        image = data.get("background_image")
        return ProviderMediaDetails(
            provider="rawg", external_id=str(data["id"]), media_type=MediaType.GAME, title=data.get("name") or "Untitled game",
            description=data.get("description_raw"), release_date=parse_date(released), release_year=extract_year(released),
            poster_url=image, backdrop_url=image, popularity_score=data.get("added"), external_url=data.get("slug") and f"https://rawg.io/games/{data['slug']}",
            attribution_text=self.ATTRIBUTION_TEXT, attribution_url=self.ATTRIBUTION_URL,
            genres=[genre["name"] for genre in data.get("genres", []) if genre.get("name")],
            images=[{"image_type": "poster", "url": image}] if image else [], metadata_json={**data, "store_urls": stores},
        )

    async def get_seed_page(self, *, seed_kind: str, media_type: MediaType, cursor: str | None = None, limit: int = 20) -> ProviderSeedPage:
        if media_type != MediaType.GAME:
            raise ProviderError("RAWG only supports game seeding")
        page = max(int(cursor or "1"), 1)
        ordering = {"popular": "-added", "top_rated": "-rating", "metacritic": "-metacritic"}.get(seed_kind, "-added")
        data = await asyncio.to_thread(self._request, "/games", {"ordering": ordering, "page": page, "page_size": min(limit, 40)})
        return ProviderSeedPage(provider="rawg", media_type=media_type, seed_kind=seed_kind, cursor=str(page), next_cursor=str(page + 1) if data.get("next") else None, results=[self._result(item) for item in data.get("results", []) if item.get("id") is not None])
