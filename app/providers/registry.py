from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.media import MediaType
from app.providers.base import BaseProviderAdapter
from app.providers.google_books import GoogleBooksProviderAdapter
from app.providers.open_library import OpenLibraryProviderAdapter
from app.providers.rawg import RAWGProviderAdapter
from app.providers.spotify import SpotifyProviderAdapter
from app.providers.tmdb import TMDBProviderAdapter


class ProviderRegistry:
    def __init__(self, settings: Settings, db: Session | None = None) -> None:
        self.settings = settings
        self.db = db

    def get(self, provider: str) -> BaseProviderAdapter:
        providers = {
            "tmdb": TMDBProviderAdapter(self.settings.tmdb_api_key, self.db),
            "rawg": RAWGProviderAdapter(self.settings.rawg_api_key, self.settings, self.db),
            "google_books": GoogleBooksProviderAdapter(self.settings.google_books_api_key, self.settings, self.db),
            "open_library": OpenLibraryProviderAdapter(self.settings, self.db),
            "spotify": SpotifyProviderAdapter(self.settings.spotify_client_id, self.settings.spotify_client_secret, self.settings, self.db),
        }
        try:
            return providers[provider.strip().lower()]
        except KeyError as error:
            raise ValueError(f"Unsupported provider: {provider}") from error

    def providers_for_search(self, media_type: MediaType) -> list[BaseProviderAdapter]:
        if media_type in {MediaType.MOVIE, MediaType.SERIES}:
            return [self.get("tmdb")]
        if media_type == MediaType.GAME:
            return [self.get("rawg")]
        if media_type == MediaType.BOOK:
            return [self.get("google_books"), self.get("open_library")]
        if media_type in {MediaType.ALBUM, MediaType.TRACK}:
            return [self.get("spotify")]
        return []
