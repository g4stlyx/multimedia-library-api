"""phase 2 media catalog

Revision ID: 202607080001
Revises: 202607060001
Create Date: 2026-07-08 00:00:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "202607080001"
down_revision: str | None = "202607060001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # Handle media_type Enum creation for PostgreSQL
    if is_postgres:
        media_type = postgresql.ENUM(
            "MOVIE", "SERIES", "BOOK", "GAME", "ALBUM", "TRACK",
            name="media_type"
        )
        media_type.create(bind, checkfirst=True)
        media_type_column = postgresql.ENUM(
            "MOVIE", "SERIES", "BOOK", "GAME", "ALBUM", "TRACK",
            name="media_type",
            create_type=False,
        )
    else:
        media_type_column = sa.Enum(
            "MOVIE", "SERIES", "BOOK", "GAME", "ALBUM", "TRACK",
            name="media_type",
        )

    # 1. genres
    op.create_table(
        "genres",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("normalized_name", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_genres_normalized_name", "genres", ["normalized_name"], unique=True)

    # 2. media
    op.create_table(
        "media",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("media_type", media_type_column, nullable=False),
        sa.Column("canonical_title", sa.String(length=512), nullable=False),
        sa.Column("normalized_title", sa.String(length=512), nullable=False),
        sa.Column("original_title", sa.String(length=512), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("release_date", sa.Date(), nullable=True),
        sa.Column("release_year", sa.Integer(), nullable=True),
        sa.Column("runtime_minutes", sa.Integer(), nullable=True),
        sa.Column("primary_language", sa.String(length=10), nullable=True),
        sa.Column("country_code", sa.String(length=10), nullable=True),
        sa.Column("poster_url", sa.String(length=2048), nullable=True),
        sa.Column("backdrop_url", sa.String(length=2048), nullable=True),
        sa.Column("source_priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("data_quality_score", sa.Float(), nullable=True),
        sa.Column("popularity_score", sa.Float(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_media_media_type_release_year", "media", ["media_type", "release_year"], unique=False)

    # Conditionally create pg_trgm extension and trigram indexes on PostgreSQL
    if is_postgres:
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        op.create_index(
            "ix_media_normalized_title_trgm",
            "media",
            ["normalized_title"],
            postgresql_using="gin",
            postgresql_ops={"normalized_title": "gin_trgm_ops"},
        )
    else:
        op.create_index(
            "ix_media_normalized_title_trgm",
            "media",
            ["normalized_title"],
        )

    # 3. media_genres
    op.create_table(
        "media_genres",
        sa.Column("media_id", sa.Uuid(), nullable=False),
        sa.Column("genre_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["media_id"], ["media.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["genre_id"], ["genres.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("media_id", "genre_id"),
    )

    # 4. media_external_ids
    op.create_table(
        "media_external_ids",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("media_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("provider_media_type", sa.String(length=50), nullable=True),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("external_url", sa.String(length=2048), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["media_id"], ["media.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_media_external_ids_provider_external_id",
        "media_external_ids",
        ["provider", "external_id"],
        unique=True,
    )
    op.create_index(
        "ix_media_external_ids_media_id_provider",
        "media_external_ids",
        ["media_id", "provider"],
        unique=False,
    )

    # 5. media_titles
    op.create_table(
        "media_titles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("media_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("normalized_title", sa.String(length=512), nullable=False),
        sa.Column("language", sa.String(length=10), nullable=True),
        sa.Column("region", sa.String(length=10), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["media_id"], ["media.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_media_titles_media_id", "media_titles", ["media_id"], unique=False)
    if is_postgres:
        op.create_index(
            "ix_media_titles_normalized_title_trgm",
            "media_titles",
            ["normalized_title"],
            postgresql_using="gin",
            postgresql_ops={"normalized_title": "gin_trgm_ops"},
        )
    else:
        op.create_index(
            "ix_media_titles_normalized_title_trgm",
            "media_titles",
            ["normalized_title"],
        )

    # 6. media_images
    op.create_table(
        "media_images",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("media_id", sa.Uuid(), nullable=False),
        sa.Column("image_type", sa.String(length=50), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("external_url", sa.String(length=2048), nullable=True),
        sa.Column("r2_object_key", sa.String(length=1024), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("content_type", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["media_id"], ["media.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_media_images_media_id", "media_images", ["media_id"], unique=False)

    # 7. provider_requests
    op.create_table(
        "provider_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("endpoint", sa.String(length=255), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("rate_limited", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    op.drop_table("provider_requests")

    op.drop_index("ix_media_images_media_id", table_name="media_images")
    op.drop_table("media_images")

    op.drop_index("ix_media_titles_normalized_title_trgm", table_name="media_titles")
    op.drop_index("ix_media_titles_media_id", table_name="media_titles")
    op.drop_table("media_titles")

    op.drop_index("ix_media_external_ids_media_id_provider", table_name="media_external_ids")
    op.drop_index("ix_media_external_ids_provider_external_id", table_name="media_external_ids")
    op.drop_table("media_external_ids")

    op.drop_table("media_genres")

    op.drop_index("ix_media_normalized_title_trgm", table_name="media")
    op.drop_index("ix_media_media_type_release_year", table_name="media")
    op.drop_table("media")

    op.drop_index("ix_genres_normalized_name", table_name="genres")
    op.drop_table("genres")

    if is_postgres:
        media_type = postgresql.ENUM("MOVIE", "SERIES", "BOOK", "GAME", "ALBUM", "TRACK", name="media_type")
        media_type.drop(bind, checkfirst=True)
