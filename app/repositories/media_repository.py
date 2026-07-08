from __future__ import annotations

import uuid
from datetime import datetime, timezone
from sqlalchemy import select, case, exists
from sqlalchemy.orm import Session

from app.core.normalization import normalize_title
from app.models.media import Genre, Media, MediaExternalId, MediaImage, MediaTitle, MediaType
from app.models.provider import ProviderRequest


class MediaRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, media_id: uuid.UUID) -> Media | None:
        return self.db.get(Media, media_id)

    def get_by_external_id(self, provider: str, external_id: str) -> Media | None:
        stmt = (
            select(Media)
            .join(MediaExternalId, Media.id == MediaExternalId.media_id)
            .where(
                MediaExternalId.provider == provider.strip().lower(),
                MediaExternalId.external_id == external_id.strip(),
            )
        )
        return self.db.scalar(stmt)

    def get_by_imdb_id(self, imdb_id: str) -> Media | None:
        return self.get_by_external_id("imdb", imdb_id)

    def search_local(
        self,
        query: str,
        media_type: MediaType | None = None,
        limit: int = 20,
    ) -> list[Media]:
        query_normalized = normalize_title(query)
        if not query_normalized:
            return []

        title_exists = exists().where(
            MediaTitle.media_id == Media.id,
            MediaTitle.normalized_title.like(f"%{query_normalized}%")
        )

        stmt = select(Media).where(
            (Media.normalized_title.like(f"%{query_normalized}%"))
            | title_exists
        )

        if media_type:
            stmt = stmt.where(Media.media_type == media_type)

        # Priority: Exact match on canonical normalized title comes first,
        # followed by popularity score desc
        exact_match_case = case(
            (Media.normalized_title == query_normalized, 0),
            else_=1,
        )

        stmt = (
            stmt.order_by(
                exact_match_case,
                Media.popularity_score.desc().nullslast(),
            )
            .limit(limit)
        )

        return list(self.db.scalars(stmt).all())


    def create_media(self, media_type: MediaType, canonical_title: str, **kwargs) -> Media:
        normalized = normalize_title(canonical_title)
        media = Media(
            media_type=media_type,
            canonical_title=canonical_title.strip(),
            normalized_title=normalized,
            **kwargs,
        )
        self.db.add(media)
        self.db.flush()
        return media

    def add_external_id(
        self,
        media_id: uuid.UUID,
        provider: str,
        external_id: str,
        provider_media_type: str | None = None,
        external_url: str | None = None,
        confidence: float = 1.0,
    ) -> MediaExternalId:
        ext_id = MediaExternalId(
            media_id=media_id,
            provider=provider.strip().lower(),
            provider_media_type=provider_media_type.strip().lower() if provider_media_type else None,
            external_id=external_id.strip(),
            external_url=external_url.strip() if external_url else None,
            confidence=confidence,
        )
        self.db.add(ext_id)
        self.db.flush()
        return ext_id

    def add_title(
        self,
        media_id: uuid.UUID,
        title: str,
        language: str | None = None,
        region: str | None = None,
        is_primary: bool = False,
    ) -> MediaTitle:
        normalized = normalize_title(title)
        media_title = MediaTitle(
            media_id=media_id,
            title=title.strip(),
            normalized_title=normalized,
            language=language.strip().lower() if language else None,
            region=region.strip().upper() if region else None,
            is_primary=is_primary,
        )
        self.db.add(media_title)
        self.db.flush()
        return media_title

    def add_image(
        self,
        media_id: uuid.UUID,
        image_type: str,
        source: str,
        external_url: str | None = None,
        r2_object_key: str | None = None,
        width: int | None = None,
        height: int | None = None,
        content_type: str | None = None,
    ) -> MediaImage:
        media_image = MediaImage(
            media_id=media_id,
            image_type=image_type.strip().lower(),
            source=source.strip().lower(),
            external_url=external_url.strip() if external_url else None,
            r2_object_key=r2_object_key.strip() if r2_object_key else None,
            width=width,
            height=height,
            content_type=content_type.strip().lower() if content_type else None,
        )
        self.db.add(media_image)
        self.db.flush()
        return media_image

    def get_or_create_genre(self, name: str) -> Genre:
        name_clean = name.strip()
        normalized = normalize_title(name_clean)
        
        # Check existing
        stmt = select(Genre).where(Genre.normalized_name == normalized)
        genre = self.db.scalar(stmt)
        if genre:
            return genre

        # Create new
        genre = Genre(
            name=name_clean,
            normalized_name=normalized,
        )
        self.db.add(genre)
        self.db.flush()
        return genre

    def associate_genre(self, media: Media, genre: Genre) -> None:
        if genre not in media.genres:
            media.genres.append(genre)
            self.db.flush()

    def log_provider_request(
        self,
        provider: str,
        endpoint: str,
        request_hash: str,
        status_code: int,
        duration_ms: int,
        rate_limited: bool = False,
    ) -> ProviderRequest:
        req = ProviderRequest(
            provider=provider.strip().lower(),
            endpoint=endpoint.strip(),
            request_hash=request_hash.strip(),
            status_code=status_code,
            duration_ms=duration_ms,
            rate_limited=rate_limited,
        )
        self.db.add(req)
        self.db.flush()
        return req
