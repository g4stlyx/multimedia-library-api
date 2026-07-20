from __future__ import annotations

import logging
import uuid
import asyncio
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.normalization import normalize_title
from app.models.media import Media, MediaType
from app.providers.base import ProviderSearchResult
from app.providers.http import ProviderError
from app.providers.registry import ProviderRegistry
from app.repositories.media_repository import MediaRepository
from app.schemas.media import MediaDetailPublic, MediaPublic, MediaSearchResponse
from app.services.provider_presentation_service import ProviderPresentationService

logger = logging.getLogger(__name__)


class MediaService:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.repo = MediaRepository(db)

    def _get_db_provider(self, provider: str, media_type: MediaType) -> str:
        prov = provider.strip().lower()
        if prov == "tmdb":
            return "tmdb_movie" if media_type == MediaType.MOVIE else "tmdb_tv"
        return prov

    def _registry(self) -> ProviderRegistry:
        return ProviderRegistry(self.settings, self.db)

    def list_popular(
        self,
        media_type: MediaType | None = None,
        limit: int = 20,
    ) -> list[Media]:
        return self.repo.list_popular(media_type=media_type, limit=limit)

    def get_media_details(self, media_id: uuid.UUID) -> MediaDetailPublic | None:
        media = self.repo.get_by_id(media_id)
        if not media:
            return None
        average_rating, rating_count = self.repo.get_rating_aggregation(media.id)
        media_data = MediaPublic.model_validate(media).model_dump()
        return MediaDetailPublic(
            **media_data,
            average_rating=average_rating,
            rating_count=rating_count,
            provider_attributions=ProviderPresentationService.build(media),
        )


    async def search_media(
        self,
        query: str,
        media_type: MediaType | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> list[MediaSearchResponse]:
        query_normalized = normalize_title(query)
        if not query_normalized:
            return []

        # 1. Search locally
        local_results = self.repo.search_local(
            query=query,
            media_type=media_type,
            limit=limit,
        )

        # Check if we have an exact title match locally
        has_exact_local_match = any(
            m.normalized_title == query_normalized for m in local_results
        )

        # If we have an exact match OR enough local results, return them immediately
        if has_exact_local_match or len(local_results) >= 3:
            return [
                MediaSearchResponse(
                    id=m.id,
                    media_type=m.media_type,
                    canonical_title=m.canonical_title,
                    normalized_title=m.normalized_title,
                    original_title=m.original_title,
                    description=m.description,
                    release_date=m.release_date,
                    release_year=m.release_year,
                    runtime_minutes=m.runtime_minutes,
                    primary_language=m.primary_language,
                    country_code=m.country_code,
                    poster_url=m.poster_url,
                    backdrop_url=m.backdrop_url,
                    popularity_score=m.popularity_score,
                    is_persisted=True,
                )
                for m in local_results
            ]

        # 2. Local miss/sparse results -> query only providers for the requested media type.
        # An untyped search remains movie/series-first to avoid fan-out to every provider.
        external_results: list[ProviderSearchResult] = []
        types_to_search = [media_type] if media_type else [MediaType.MOVIE, MediaType.SERIES]
        searches = [adapter.search(query, target_type, limit) for target_type in types_to_search for adapter in self._registry().providers_for_search(target_type)]
        if searches:
            provider_responses = await asyncio.gather(*searches, return_exceptions=True)
            for response in provider_responses:
                if isinstance(response, Exception):
                    logger.warning("provider_search_failed", exc_info=response)
                else:
                    external_results.extend(response)

        # Merge local and external results
        combined_responses: list[MediaSearchResponse] = []
        seen_external_keys = set()  # (provider, external_id)

        # Map local results first
        for m in local_results:
            combined_responses.append(
                MediaSearchResponse(
                    id=m.id,
                    media_type=m.media_type,
                    canonical_title=m.canonical_title,
                    normalized_title=m.normalized_title,
                    original_title=m.original_title,
                    description=m.description,
                    release_date=m.release_date,
                    release_year=m.release_year,
                    runtime_minutes=m.runtime_minutes,
                    primary_language=m.primary_language,
                    country_code=m.country_code,
                    poster_url=m.poster_url,
                    backdrop_url=m.backdrop_url,
                    popularity_score=m.popularity_score,
                    is_persisted=True,
                )
            )
            # Find associated external IDs to avoid adding duplicate external records later
            for ext in m.external_ids:
                seen_external_keys.add((ext.provider, ext.external_id))

        # Add external results if they aren't already represented locally
        for ext in external_results:
            db_provider = self._get_db_provider(ext.provider, ext.media_type)
            # Check if this external ID already mapped to a local item during the local search
            if (db_provider, ext.external_id) in seen_external_keys:
                continue

            # Double check database for existing matches (that may not have appeared in local search)
            existing_media = self.repo.get_by_external_id(db_provider, ext.external_id)
            if existing_media:
                combined_responses.append(
                    MediaSearchResponse(
                        id=existing_media.id,
                        media_type=existing_media.media_type,
                        canonical_title=existing_media.canonical_title,
                        normalized_title=existing_media.normalized_title,
                        original_title=existing_media.original_title,
                        description=existing_media.description,
                        release_date=existing_media.release_date,
                        release_year=existing_media.release_year,
                        runtime_minutes=existing_media.runtime_minutes,
                        primary_language=existing_media.primary_language,
                        country_code=existing_media.country_code,
                        poster_url=existing_media.poster_url,
                        backdrop_url=existing_media.backdrop_url,
                        popularity_score=existing_media.popularity_score,
                        is_persisted=True,
                    )
                )
                seen_external_keys.add((ext.provider, ext.external_id))
                continue

            # Keep as unpersisted external result
            combined_responses.append(
                MediaSearchResponse(
                    media_type=ext.media_type,
                    canonical_title=ext.title,
                    normalized_title=normalize_title(ext.title),
                    original_title=ext.original_title,
                    description=ext.description,
                    release_date=ext.release_date,
                    release_year=ext.release_year,
                    runtime_minutes=ext.runtime_minutes,
                    primary_language=ext.primary_language,
                    country_code=ext.country_code,
                    poster_url=ext.poster_url,
                    backdrop_url=ext.backdrop_url,
                    popularity_score=ext.popularity_score,
                    provider=ext.provider,
                    external_id=ext.external_id,
                    external_url=ext.external_url,
                    attribution_text=ext.attribution_text,
                    attribution_url=ext.attribution_url,
                    is_persisted=False,
                )
            )
            seen_external_keys.add((db_provider, ext.external_id))

        return combined_responses[:limit]

    async def upsert_by_external_id(
        self,
        provider: str,
        external_id: str,
        media_type: MediaType,
    ) -> Media:
        provider_clean = provider.strip().lower()
        external_id_clean = external_id.strip()
        db_provider = self._get_db_provider(provider_clean, media_type)

        # 1. Exact external provider ID match wins
        existing_media = self.repo.get_by_external_id(db_provider, external_id_clean)
        if existing_media:
            return existing_media
        if self.repo.get_by_external_id(db_provider, external_id_clean, include_deleted=True):
            raise ValueError("Media is unavailable")

        # Fetch detailed metadata through the provider registry, never trusting client supplied fields.
        try:
            details = await self._registry().get(provider_clean).get_details(external_id_clean, media_type)
        except ProviderError as error:
            raise ValueError(str(error)) from error

        # 2. Strong cross-provider ID match wins (e.g. IMDb ID mapping)
        strong_ids = list(details.additional_external_ids)
        if details.imdb_id:
            strong_ids.append({"provider": "imdb", "external_id": details.imdb_id})
        for strong_id in strong_ids:
            existing = self.repo.get_by_external_id(strong_id["provider"], strong_id["external_id"])
            if existing:
                self.repo.add_external_id(
                    media_id=existing.id, provider=db_provider, external_id=external_id_clean,
                    provider_media_type=media_type.value, external_url=details.external_url,
                    attribution_text=details.attribution_text, attribution_url=details.attribution_url, confidence=1.0,
                )
                self.db.commit()
                return existing

        # 3. Fuzzy match by normalized title and media type
        normalized_title = normalize_title(details.title)
        stmt = select(Media).where(
            Media.media_type == media_type,
            Media.normalized_title == normalized_title,
            Media.deleted_at.is_(None),
        )
        candidates = self.db.scalars(stmt).all()

        high_confidence_match: Media | None = None
        potential_duplicates: list[Media] = []

        for candidate in candidates:
            # If both have a release year and they match exactly, we merge
            if candidate.release_year is not None and details.release_year is not None:
                if candidate.release_year == details.release_year:
                    high_confidence_match = candidate
                    break
                elif abs(candidate.release_year - details.release_year) <= 1:
                    potential_duplicates.append(candidate)
            else:
                # If one of the release years is null, count as a potential duplicate candidate
                potential_duplicates.append(candidate)

        # Merge if high confidence match found
        if high_confidence_match:
            self.repo.add_external_id(
                media_id=high_confidence_match.id,
                provider=db_provider,
                external_id=external_id_clean,
                provider_media_type=media_type.value,
                external_url=details.external_url,
                attribution_text=details.attribution_text,
                attribution_url=details.attribution_url,
                confidence=0.9,
            )
            self.db.commit()
            return high_confidence_match

        # 4. If confidence is below threshold (no exact/high-confidence match),
        # create a new record and flag duplicate candidate IDs in metadata.
        metadata_json = details.metadata_json or {}
        if potential_duplicates:
            metadata_json["duplicate_candidates"] = [str(m.id) for m in potential_duplicates]

        media = self.repo.create_media(
            media_type=media_type,
            canonical_title=details.title,
            original_title=details.original_title,
            description=details.description,
            release_date=details.release_date,
            release_year=details.release_year,
            runtime_minutes=details.runtime_minutes,
            primary_language=details.primary_language,
            country_code=details.country_code,
            poster_url=details.poster_url,
            backdrop_url=details.backdrop_url,
            popularity_score=details.popularity_score,
            metadata_json=metadata_json,
        )

        # Link current provider ID
        self.repo.add_external_id(
            media_id=media.id,
            provider=db_provider,
            external_id=external_id_clean,
            provider_media_type=media_type.value,
            external_url=details.external_url,
            attribution_text=details.attribution_text,
            attribution_url=details.attribution_url,
            confidence=1.0,
        )

        # Link strong cross-provider identifiers (IMDb, ISBN, ISRC) for future deduplication.
        for strong_id in strong_ids:
            if not self.repo.get_by_external_id(strong_id["provider"], strong_id["external_id"]):
                self.repo.add_external_id(
                    media_id=media.id, provider=strong_id["provider"], external_id=strong_id["external_id"],
                    external_url=strong_id.get("external_url"), confidence=1.0,
                )

        # Add primary title
        self.repo.add_title(
            media_id=media.id,
            title=details.title,
            language=details.primary_language,
            is_primary=True,
        )

        # Add alternate titles
        for alt in details.alternate_titles:
            self.repo.add_title(
                media_id=media.id,
                title=alt["title"],
                language=alt.get("language"),
                region=alt.get("region"),
                is_primary=False,
            )

        # Add image URLs
        for img in details.images:
            self.repo.add_image(
                media_id=media.id,
                image_type=img["image_type"],
                source=db_provider,
                external_url=img["url"],
                width=img.get("width"),
                height=img.get("height"),
            )

        # Map and associate genres
        for g_name in details.genres:
            genre = self.repo.get_or_create_genre(g_name)
            self.repo.associate_genre(media, genre)

        # Write audit log if potential duplicate candidates were flagged
        if potential_duplicates:
            try:
                from app.repositories.audit_repository import AuditRepository
                audit_repo = AuditRepository(self.db)
                audit_repo.create_audit_log(
                    action="media.duplicate_candidate",
                    resource_type="media",
                    resource_id=str(media.id),
                    metadata={
                        "candidate_ids": [str(m.id) for m in potential_duplicates],
                        "reason": f"Fuzzy title match on '{normalized_title}' with different/near release year",
                    },
                    created_at=datetime.now(timezone.utc),
                )
            except Exception as e:
                logger.exception("Failed to write duplicate candidate audit log: %s", e)

        self.db.commit()
        return media

    async def refresh_media(
        self,
        media_id: uuid.UUID,
        *,
        actor_user_id: uuid.UUID,
        request_id: str | None,
    ) -> Media:
        media = self.repo.get_by_id(media_id)
        if not media:
            raise LookupError("Media not found")

        now = datetime.now(timezone.utc)
        last_synced_at = media.last_synced_at
        if last_synced_at and last_synced_at.tzinfo is None:
            last_synced_at = last_synced_at.replace(tzinfo=timezone.utc)
        if last_synced_at and (now - last_synced_at).total_seconds() < 900:
            raise RuntimeError("This media was refreshed recently. Please try again later.")

        provider_id = next((external_id for external_id in media.external_ids if external_id.provider in {"tmdb_movie", "tmdb_tv", "rawg", "google_books", "open_library", "spotify"}), None)
        if provider_id is None:
            raise ValueError("No supported metadata provider is linked to this media")

        provider_name = "tmdb" if provider_id.provider in {"tmdb_movie", "tmdb_tv"} else provider_id.provider
        try:
            details = await self._registry().get(provider_name).get_details(provider_id.external_id, media.media_type)
        except ProviderError as error:
            raise ValueError("Metadata provider refresh failed") from error
        refreshed = self.repo.update_from_provider(
            media,
            canonical_title=details.title,
            normalized_title=normalize_title(details.title),
            original_title=details.original_title,
            description=details.description,
            release_date=details.release_date,
            release_year=details.release_year,
            runtime_minutes=details.runtime_minutes,
            primary_language=details.primary_language,
            country_code=details.country_code,
            poster_url=details.poster_url,
            backdrop_url=details.backdrop_url,
            popularity_score=details.popularity_score,
            metadata_json=details.metadata_json or {},
            last_synced_at=now,
        )
        refreshed.genres = [self.repo.get_or_create_genre(name) for name in details.genres]

        from app.repositories.audit_repository import AuditRepository

        AuditRepository(self.db).create_audit_log(
            action="media.metadata_refreshed",
            actor_user_id=actor_user_id,
            resource_type="media",
            resource_id=str(media.id),
            request_id=request_id,
            created_at=now,
        )
        self.db.commit()
        self.db.refresh(refreshed)
        return refreshed
