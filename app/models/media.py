from __future__ import annotations

import enum
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Table,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class MediaType(str, enum.Enum):
    MOVIE = "MOVIE"
    SERIES = "SERIES"
    BOOK = "BOOK"
    GAME = "GAME"
    ALBUM = "ALBUM"
    TRACK = "TRACK"


class LibraryStatus(str, enum.Enum):
    PLANNED = "PLANNED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    PAUSED = "PAUSED"
    DROPPED = "DROPPED"


# Many-to-many association table mapping Media to Genres
media_genres = Table(
    "media_genres",
    Base.metadata,
    Column(
        "media_id",
        ForeignKey("media.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "genre_id",
        ForeignKey("genres.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Genre(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "genres"
    __table_args__ = (
        Index("ix_genres_normalized_name", "normalized_name", unique=True),
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(100), nullable=False)

    # Relationships
    media: Mapped[list[Media]] = relationship(
        secondary="media_genres",
        back_populates="genres",
    )


class Media(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "media"
    __table_args__ = (
        Index("ix_media_media_type_release_year", "media_type", "release_year"),
        Index(
            "ix_media_normalized_title_trgm",
            "normalized_title",
            postgresql_using="gin",
            postgresql_ops={"normalized_title": "gin_trgm_ops"},
        ),
    )

    media_type: Mapped[MediaType] = mapped_column(
        Enum(MediaType, name="media_type"),
        nullable=False,
    )
    canonical_title: Mapped[str] = mapped_column(String(512), nullable=False)
    normalized_title: Mapped[str] = mapped_column(String(512), nullable=False)
    original_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    release_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    release_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    runtime_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    primary_language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    poster_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    backdrop_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    source_priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    data_quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    popularity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    external_ids: Mapped[list[MediaExternalId]] = relationship(
        back_populates="media",
        cascade="all, delete-orphan",
    )
    titles: Mapped[list[MediaTitle]] = relationship(
        back_populates="media",
        cascade="all, delete-orphan",
    )
    images: Mapped[list[MediaImage]] = relationship(
        back_populates="media",
        cascade="all, delete-orphan",
    )
    genres: Mapped[list[Genre]] = relationship(
        secondary="media_genres",
        back_populates="media",
    )
    media_entries: Mapped[list[UserMediaEntry]] = relationship(
        "UserMediaEntry",
        back_populates="media",
        cascade="all, delete-orphan",
    )
    reviews: Mapped[list[Review]] = relationship(
        "Review",
        back_populates="media",
        cascade="all, delete-orphan",
    )
    list_items: Mapped[list[ListItem]] = relationship(
        "ListItem",
        back_populates="media",
        cascade="all, delete-orphan",
    )


class MediaExternalId(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "media_external_ids"
    __table_args__ = (
        Index(
            "ix_media_external_ids_provider_external_id",
            "provider",
            "external_id",
            unique=True,
        ),
        Index("ix_media_external_ids_media_id_provider", "media_id", "provider"),
    )

    media_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("media.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_media_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    external_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    attribution_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    attribution_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)

    # Relationships
    media: Mapped[Media] = relationship(back_populates="external_ids")


class MediaTitle(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "media_titles"
    __table_args__ = (
        Index("ix_media_titles_media_id", "media_id"),
        Index(
            "ix_media_titles_normalized_title_trgm",
            "normalized_title",
            postgresql_using="gin",
            postgresql_ops={"normalized_title": "gin_trgm_ops"},
        ),
    )

    media_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("media.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    normalized_title: Mapped[str] = mapped_column(String(512), nullable=False)
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    region: Mapped[str | None] = mapped_column(String(10), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    media: Mapped[Media] = relationship(back_populates="titles")


class MediaImage(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "media_images"
    __table_args__ = (
        Index("ix_media_images_media_id", "media_id"),
    )

    media_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("media.id", ondelete="CASCADE"),
        nullable=False,
    )
    image_type: Mapped[str] = mapped_column(String(50), nullable=False)  # poster, backdrop, etc.
    source: Mapped[str] = mapped_column(String(50), nullable=False)  # tmdb, rawg, etc.
    external_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    r2_object_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    media: Mapped[Media] = relationship(back_populates="images")
