"""phase 5 uploads and R2

Revision ID: 202607110002
Revises: 202607110001
Create Date: 2026-07-11 00:00:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "202607110002"
down_revision: str | None = "202607110001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        upload_status = postgresql.ENUM("ACTIVE", "REPLACED", "DELETED", name="upload_status")
        upload_status.create(bind, checkfirst=True)
        status_column = postgresql.ENUM("ACTIVE", "REPLACED", "DELETED", name="upload_status", create_type=False)
    else:
        status_column = sa.Enum("ACTIVE", "REPLACED", "DELETED", name="upload_status")

    op.create_table(
        "uploads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("upload_type", sa.String(length=50), nullable=False),
        sa.Column("r2_object_key", sa.String(length=1024), nullable=False),
        sa.Column("original_filename_sanitized", sa.String(length=255), nullable=True),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("status", status_column, nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_uploads_user_created_at", "uploads", ["user_id", "created_at"])
    op.create_index("ix_uploads_r2_object_key", "uploads", ["r2_object_key"], unique=True)
    op.add_column("users", sa.Column("profile_image_upload_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_users_profile_image_upload", "users", "uploads", ["profile_image_upload_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    bind = op.get_bind()
    op.drop_constraint("fk_users_profile_image_upload", "users", type_="foreignkey")
    op.drop_column("users", "profile_image_upload_id")
    op.drop_index("ix_uploads_r2_object_key", table_name="uploads")
    op.drop_index("ix_uploads_user_created_at", table_name="uploads")
    op.drop_table("uploads")
    if bind.dialect.name == "postgresql":
        postgresql.ENUM(name="upload_status").drop(bind, checkfirst=True)
