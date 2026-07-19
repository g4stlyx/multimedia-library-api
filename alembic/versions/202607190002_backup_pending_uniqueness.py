"""add durable backup worker state and enforce one active backup

Revision ID: 202607190002
Revises: 202607190001
Create Date: 2026-07-19 00:10:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "202607190002"
down_revision: str | None = "202607190001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    op.add_column("backup_metadata", sa.Column("worker_id", sa.String(length=128), nullable=True))
    op.add_column("backup_metadata", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "backup_metadata",
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
    )
    metadata = sa.table(
        "backup_metadata",
        sa.column("id", sa.Uuid()),
        sa.column("status", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("finished_at", sa.DateTime(timezone=True)),
        sa.column("error_message", sa.Text()),
        sa.column("worker_id", sa.String()),
        sa.column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.column("attempt_count", sa.Integer()),
    )
    active_ids = list(
        bind.execute(
            sa.select(metadata.c.id)
            .where(metadata.c.status.in_(["pending", "processing"]))
            .order_by(metadata.c.created_at.desc())
        ).scalars()
    )
    for stale_id in active_ids[1:]:
        bind.execute(
            sa.update(metadata)
            .where(metadata.c.id == stale_id)
            .values(
                status="failed",
                error_message="Superseded stale active backup during uniqueness migration",
            )
        )
    op.create_index(
        "uq_backup_metadata_active",
        "backup_metadata",
        ["status"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'processing')"),
        sqlite_where=sa.text("status IN ('pending', 'processing')"),
    )


def downgrade() -> None:
    op.drop_index("uq_backup_metadata_active", table_name="backup_metadata")
    op.drop_column("backup_metadata", "attempt_count")
    op.drop_column("backup_metadata", "lease_expires_at")
    op.drop_column("backup_metadata", "worker_id")
