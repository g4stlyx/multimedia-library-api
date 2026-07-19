"""add durable import worker leases

Revision ID: 202607190001
Revises: 17ea7ca9755a
Create Date: 2026-07-19 00:00:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "202607190001"
down_revision: str | None = "17ea7ca9755a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("import_jobs", sa.Column("worker_id", sa.String(length=128), nullable=True))
    op.add_column("import_jobs", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "import_jobs",
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_import_jobs_status_lease_expires_at",
        "import_jobs",
        ["status", "lease_expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_import_jobs_status_lease_expires_at", table_name="import_jobs")
    op.drop_column("import_jobs", "attempt_count")
    op.drop_column("import_jobs", "lease_expires_at")
    op.drop_column("import_jobs", "worker_id")
