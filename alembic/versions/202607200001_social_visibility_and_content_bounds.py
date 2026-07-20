"""add follower graph and user-authored content bounds

Revision ID: 202607200001
Revises: 202607190002
Create Date: 2026-07-20 00:00:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "202607200001"
down_revision: str | None = "202607190002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_follows",
        sa.Column("follower_id", sa.Uuid(), nullable=False),
        sa.Column("followed_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("follower_id <> followed_id", name="ck_user_follows_not_self"),
        sa.ForeignKeyConstraint(["follower_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["followed_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("follower_id", "followed_id"),
    )
    op.create_index(
        "ix_user_follows_followed_created", "user_follows", ["followed_id", "created_at"]
    )
    op.create_check_constraint("ck_reviews_body_length", "reviews", "body IS NULL OR length(body) <= 5000")
    op.create_check_constraint("ck_comments_body_length", "comments", "length(body) <= 2000")
    op.create_check_constraint(
        "ck_lists_description_length", "lists", "description IS NULL OR length(description) <= 5000"
    )
    op.create_check_constraint(
        "ck_list_items_note_length", "list_items", "note IS NULL OR length(note) <= 2000"
    )
    op.create_check_constraint(
        "ck_user_media_entries_notes_private_length",
        "user_media_entries",
        "notes_private IS NULL OR length(notes_private) <= 5000",
    )


def downgrade() -> None:
    op.drop_constraint("ck_user_media_entries_notes_private_length", "user_media_entries", type_="check")
    op.drop_constraint("ck_list_items_note_length", "list_items", type_="check")
    op.drop_constraint("ck_lists_description_length", "lists", type_="check")
    op.drop_constraint("ck_comments_body_length", "comments", type_="check")
    op.drop_constraint("ck_reviews_body_length", "reviews", type_="check")
    op.drop_index("ix_user_follows_followed_created", table_name="user_follows")
    op.drop_table("user_follows")
