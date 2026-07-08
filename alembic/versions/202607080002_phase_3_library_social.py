"""phase 3 library social

Revision ID: 202607080002
Revises: 202607080001
Create Date: 2026-07-08 00:00:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "202607080002"
down_revision: str | None = "202607080001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # 1. library_status enum
    if is_postgres:
        library_status = postgresql.ENUM(
            "PLANNED", "IN_PROGRESS", "COMPLETED", "PAUSED", "DROPPED",
            name="library_status"
        )
        library_status.create(bind, checkfirst=True)
        library_status_column = postgresql.ENUM(
            "PLANNED", "IN_PROGRESS", "COMPLETED", "PAUSED", "DROPPED",
            name="library_status",
            create_type=False,
        )
    else:
        library_status_column = sa.Enum(
            "PLANNED", "IN_PROGRESS", "COMPLETED", "PAUSED", "DROPPED",
            name="library_status",
        )

    # 2. user_media_entries table
    op.create_table(
        "user_media_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("media_id", sa.Uuid(), nullable=False),
        sa.Column("status", library_status_column, nullable=False),
        sa.Column("rating_value", sa.Integer(), nullable=True),
        sa.Column("progress_value", sa.Integer(), nullable=True),
        sa.Column("progress_total", sa.Integer(), nullable=True),
        sa.Column("progress_unit", sa.String(length=50), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes_private", sa.Text(), nullable=True),
        sa.Column("is_favorite", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("source", sa.String(length=50), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["media_id"], ["media.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Partial unique index for active library entry
    if is_postgres:
        op.create_index(
            "ix_user_media_entries_user_media_active",
            "user_media_entries",
            ["user_id", "media_id"],
            unique=True,
            postgresql_where="deleted_at IS NULL",
        )
    else:
        op.execute(
            "CREATE UNIQUE INDEX ix_user_media_entries_user_media_active "
            "ON user_media_entries (user_id, media_id) WHERE deleted_at IS NULL"
        )

    # 3. reviews table
    op.create_table(
        "reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("media_id", sa.Uuid(), nullable=False),
        sa.Column("rating_value", sa.Integer(), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("contains_spoilers", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("visibility", sa.String(length=50), nullable=False, server_default="public"),
        sa.Column("like_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("comment_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["media_id"], ["media.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Partial unique index for active review
    if is_postgres:
        op.create_index(
            "ix_reviews_user_media_active",
            "reviews",
            ["user_id", "media_id"],
            unique=True,
            postgresql_where="deleted_at IS NULL",
        )
    else:
        op.execute(
            "CREATE UNIQUE INDEX ix_reviews_user_media_active "
            "ON reviews (user_id, media_id) WHERE deleted_at IS NULL"
        )

    # 4. comments table
    op.create_table(
        "comments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("target_type", sa.String(length=50), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("parent_comment_id", sa.Uuid(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_comment_id"], ["comments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # 5. lists table
    op.create_table(
        "lists",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("visibility", sa.String(length=50), nullable=False, server_default="public"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # 6. list_items table
    op.create_table(
        "list_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("list_id", sa.Uuid(), nullable=False),
        sa.Column("media_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["list_id"], ["lists.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["media_id"], ["media.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_list_items_list_media", "list_items", ["list_id", "media_id"], unique=True)
    op.create_index("ix_list_items_list_position", "list_items", ["list_id", "position"], unique=True)


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    op.drop_table("list_items")
    op.drop_table("lists")
    op.drop_table("comments")

    if is_postgres:
        op.drop_index("ix_reviews_user_media_active", table_name="reviews")
    else:
        op.execute("DROP INDEX IF EXISTS ix_reviews_user_media_active")
    op.drop_table("reviews")

    if is_postgres:
        op.drop_index("ix_user_media_entries_user_media_active", table_name="user_media_entries")
    else:
        op.execute("DROP INDEX IF EXISTS ix_user_media_entries_user_media_active")
    op.drop_table("user_media_entries")

    if is_postgres:
        library_status = postgresql.ENUM("PLANNED", "IN_PROGRESS", "COMPLETED", "PAUSED", "DROPPED", name="library_status")
        library_status.drop(bind, checkfirst=True)
