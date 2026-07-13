"""phase 6 imports

Revision ID: 202607130001
Revises: 202607110002
Create Date: 2026-07-13 00:00:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "202607130001"
down_revision: str | None = "202607110002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enum(name: str, *values: str):
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        enum = postgresql.ENUM(*values, name=name)
        enum.create(bind, checkfirst=True)
        return postgresql.ENUM(*values, name=name, create_type=False)
    return sa.Enum(*values, name=name)


def upgrade() -> None:
    source = _enum("import_source", "LETTERBOXD", "GENERIC", "STEAM", "SPOTIFY")
    job_status = _enum("import_job_status", "PENDING", "PROCESSING", "AWAITING_RESOLUTION", "COMPLETED", "FAILED", "CANCELLED")
    item_status = _enum("import_item_status", "PENDING", "MATCHED", "CONFLICT", "IMPORTED", "SKIPPED", "FAILED")
    op.create_table(
        "import_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("source_platform", source, nullable=False),
        sa.Column("status", job_status, nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=True),
        sa.Column("file_r2_object_key", sa.String(length=1024), nullable=True),
        sa.Column("file_sha256", sa.String(length=64), nullable=False),
        sa.Column("total_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("successful_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_import_jobs_user_created_at", "import_jobs", ["user_id", "created_at"])
    op.create_index("ix_import_jobs_user_source_sha256", "import_jobs", ["user_id", "source_platform", "file_sha256"], unique=True)
    op.create_index("ix_import_jobs_status_created_at", "import_jobs", ["status", "created_at"])
    op.create_table(
        "import_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("import_job_id", sa.Uuid(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("raw_payload_json", sa.JSON(), nullable=False),
        sa.Column("matched_media_id", sa.Uuid(), nullable=True),
        sa.Column("match_confidence", sa.Float(), nullable=True),
        sa.Column("match_candidates_json", sa.JSON(), nullable=False),
        sa.Column("resolution_action", sa.String(length=20), nullable=True),
        sa.Column("status", item_status, nullable=False),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["import_job_id"], ["import_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["matched_media_id"], ["media.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_import_items_job_row", "import_items", ["import_job_id", "row_number"], unique=True)
    op.create_index("ix_import_items_job_status", "import_items", ["import_job_id", "status"])


def downgrade() -> None:
    bind = op.get_bind()
    op.drop_table("import_items")
    op.drop_table("import_jobs")
    if bind.dialect.name == "postgresql":
        for name in ("import_item_status", "import_job_status", "import_source"):
            postgresql.ENUM(name=name).drop(bind, checkfirst=True)
