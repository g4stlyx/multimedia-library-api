from __future__ import annotations

import asyncio
import threading
import time
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.media import MediaType
from app.providers.base import BaseProviderAdapter, ProviderMediaDetails, ProviderSearchResult
from app.providers.http import ProviderError, ProviderHttpClient


class SpotifyProviderAdapter(BaseProviderAdapter):
    API_BASE_URL = "https://api.spotify.com/v1"
    TOKEN_BASE_URL = "https://accounts.spotify.com/api"
    ATTRIBUTION_TEXT = "Music metadata provided by Spotify"
    ATTRIBUTION_URL = "https://open.spotify.com/"

    def __init__(self, client_id: str | None, client_secret: str | None, settings: Settings, db: Session | None = None) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.api_client = ProviderHttpClient(provider="spotify", base_url=self.API_BASE_URL, settings=settings, requests_per_second=5.0, db=db)
        self.token_client = ProviderHttpClient(provider="spotify", base_url=self.TOKEN_BASE_URL, settings=settings, requests_per_second=1.0, db=db)
        self._access_token: str | None = None
        self._expires_at = 0.0
        self._token_lock = threading.Lock()

    def _token(self) -> str:
        if not self.client_id or not self.client_secret:
            raise ProviderError("Spotify client credentials are not configured")
        with self._token_lock:
            if self._access_token and time.monotonic() < self._expires_at:
                return self._access_token
            import base64
            encoded = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
            data = self.token_client.request("POST", "/token", headers={"Authorization": f"Basic {encoded}", "Content-Type": "application/x-www-form-urlencoded"}, form_data={"grant_type": "client_credentials"})
            token = data.get("access_token")
            if not isinstance(token, str):
                raise ProviderError("Spotify token response did not contain an access token")
            self._access_token = token
            self._expires_at = time.monotonic() + max(int(data.get("expires_in", 3600)) - 60, 60)
            return token

    def _request(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.api_client.request("GET", path, params=params, headers={"Authorization": f"Bearer {self._token()}"})

    @classmethod
    def _result(cls, item: dict[str, Any], media_type: MediaType) -> ProviderSearchResult:
        album = item.get("album") if media_type == MediaType.TRACK else item
        images = (album or {}).get("images") or []
        release = (album or {}).get("release_date")
        artists = item.get("artists") or (album or {}).get("artists") or []
        return ProviderSearchResult(
            provider="spotify", external_id=str(item["id"]), media_type=media_type, title=item.get("name") or "Untitled",
            release_year=int(release[:4]) if isinstance(release, str) and release[:4].isdigit() else None,
            poster_url=images[0].get("url") if images else None, popularity_score=item.get("popularity"),
            external_url=(item.get("external_urls") or {}).get("spotify"), attribution_text=cls.ATTRIBUTION_TEXT,
            attribution_url=cls.ATTRIBUTION_URL, metadata_json={"artists": artists, "album": album},
        )

    async def search(self, query: str, media_type: MediaType, limit: int = 20) -> list[ProviderSearchResult]:
        if media_type not in {MediaType.ALBUM, MediaType.TRACK} or not self.client_id or not self.client_secret:
            return []
        spotify_type = "album" if media_type == MediaType.ALBUM else "track"
        data = await asyncio.to_thread(self._request, "/search", {"q": query, "type": spotify_type, "limit": min(limit, 50)})
        items = (data.get(f"{spotify_type}s") or {}).get("items", [])
        return [self._result(item, media_type) for item in items if item.get("id")]

    async def get_details(self, external_id: str, media_type: MediaType) -> ProviderMediaDetails:
        if media_type not in {MediaType.ALBUM, MediaType.TRACK}:
            raise ProviderError("Spotify only supports albums and tracks")
        path = f"/albums/{external_id}" if media_type == MediaType.ALBUM else f"/tracks/{external_id}"
        data = await asyncio.to_thread(self._request, path)
        result = self._result(data, media_type)
        artists = (data.get("artists") or (data.get("album") or {}).get("artists") or [])
        image = result.poster_url
        additional_ids = []
        external_ids = data.get("external_ids") or {}
        if external_ids.get("isrc"):
            additional_ids.append({"provider": "isrc", "external_id": external_ids["isrc"]})
        return ProviderMediaDetails(
            provider="spotify", external_id=result.external_id, media_type=media_type, title=result.title,
            release_year=result.release_year, runtime_minutes=(int(data["duration_ms"] / 60000) if data.get("duration_ms") else None),
            poster_url=image, popularity_score=result.popularity_score, external_url=result.external_url,
            attribution_text=self.ATTRIBUTION_TEXT, attribution_url=self.ATTRIBUTION_URL, additional_external_ids=additional_ids,
            alternate_titles=[{"title": artist["name"], "language": None, "region": None} for artist in artists if artist.get("name")],
            images=[{"image_type": "poster", "url": image}] if image else [], metadata_json=result.metadata_json,
        )
