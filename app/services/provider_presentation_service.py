from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from app.models.media import Media, MediaExternalId
from app.schemas.media import ProviderPresentationPublic, ProviderTrackPublic


class ProviderPresentationService:
    """Projects provider data into the stable, public media details contract."""

    _DISPLAYABLE_PROVIDERS = {
        "tmdb_movie",
        "tmdb_tv",
        "rawg",
        "google_books",
        "open_library",
        "spotify",
    }

    @classmethod
    def build(cls, media: Media) -> list[ProviderPresentationPublic]:
        metadata = media.metadata_json if isinstance(media.metadata_json, dict) else {}
        metadata_provider = cls._metadata_provider(metadata)
        isbn_10, isbn_13 = cls._isbn_values(media.external_ids, metadata)

        presentations: list[ProviderPresentationPublic] = []
        for external_id in media.external_ids:
            if external_id.provider not in cls._DISPLAYABLE_PROVIDERS:
                continue
            if not (external_id.attribution_text or external_id.attribution_url or external_id.external_url):
                continue

            presentation = ProviderPresentationPublic(
                provider=external_id.provider,
                external_url=external_id.external_url,
                attribution_text=external_id.attribution_text,
                attribution_url=external_id.attribution_url,
            )
            if external_id.provider == metadata_provider:
                cls._apply_metadata(presentation, metadata, isbn_10, isbn_13)
            presentations.append(presentation)
        return presentations

    @staticmethod
    def _metadata_provider(metadata: dict[str, Any]) -> str | None:
        if isinstance(metadata.get("volumeInfo"), dict):
            return "google_books"
        if "metacritic" in metadata or isinstance(metadata.get("platforms"), list):
            return "rawg"
        if isinstance(metadata.get("album"), dict) and isinstance(metadata.get("artists"), list):
            return "spotify"
        if isinstance(metadata.get("title"), str) and isinstance(metadata.get("covers"), list):
            return "open_library"
        return None

    @classmethod
    def _apply_metadata(
        cls,
        presentation: ProviderPresentationPublic,
        metadata: dict[str, Any],
        isbn_10: list[str],
        isbn_13: list[str],
    ) -> None:
        if presentation.provider == "rawg":
            presentation.publisher = cls._first_name(metadata.get("publishers"))
            presentation.platforms = cls._names(metadata.get("platforms"), nested_key="platform")
            score = metadata.get("metacritic")
            presentation.metacritic_score = score if isinstance(score, int) and 0 <= score <= 100 else None
        elif presentation.provider in {"google_books", "open_library"}:
            presentation.isbn_10 = isbn_10
            presentation.isbn_13 = isbn_13
        elif presentation.provider == "spotify":
            presentation.artists = cls._names(metadata.get("artists"))
            album = metadata.get("album")
            if isinstance(album, dict):
                tracks = album.get("tracks")
                items = tracks.get("items") if isinstance(tracks, dict) else []
                presentation.tracklist = cls._tracks(items)

    @classmethod
    def _isbn_values(cls, external_ids: Iterable[MediaExternalId], metadata: dict[str, Any]) -> tuple[list[str], list[str]]:
        isbn_10 = cls._external_id_values(external_ids, "isbn_10")
        isbn_13 = cls._external_id_values(external_ids, "isbn_13")
        volume_info = metadata.get("volumeInfo")
        if isinstance(volume_info, dict):
            for identifier in volume_info.get("industryIdentifiers", []):
                if not isinstance(identifier, dict):
                    continue
                value = identifier.get("identifier")
                if not isinstance(value, str) or not value.strip():
                    continue
                if identifier.get("type") == "ISBN_10":
                    isbn_10.append(value.strip())
                elif identifier.get("type") == "ISBN_13":
                    isbn_13.append(value.strip())
        return cls._unique(isbn_10), cls._unique(isbn_13)

    @staticmethod
    def _external_id_values(external_ids: Iterable[MediaExternalId], provider: str) -> list[str]:
        return [item.external_id for item in external_ids if item.provider == provider and item.external_id]

    @staticmethod
    def _unique(values: Iterable[str]) -> list[str]:
        return list(dict.fromkeys(value for value in values if value))

    @staticmethod
    def _first_name(items: object) -> str | None:
        names = ProviderPresentationService._names(items)
        return names[0] if names else None

    @staticmethod
    def _names(items: object, nested_key: str | None = None) -> list[str]:
        if not isinstance(items, list):
            return []
        names: list[str] = []
        for item in items:
            if nested_key and isinstance(item, dict):
                item = item.get(nested_key)
            if isinstance(item, dict) and isinstance(item.get("name"), str) and item["name"].strip():
                names.append(item["name"].strip())
        return ProviderPresentationService._unique(names)

    @staticmethod
    def _tracks(items: object) -> list[ProviderTrackPublic]:
        if not isinstance(items, list):
            return []
        tracks: list[ProviderTrackPublic] = []
        for item in items[:50]:
            if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not item["name"].strip():
                continue
            duration = item.get("duration_ms")
            tracks.append(ProviderTrackPublic(
                name=item["name"].strip(),
                duration_ms=duration if isinstance(duration, int) and duration >= 0 else None,
            ))
        return tracks
