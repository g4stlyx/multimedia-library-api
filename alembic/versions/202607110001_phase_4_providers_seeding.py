"""phase 4 providers and seeding

Revision ID: 202607110001
Revises: 202607080002
Create Date: 2026-07-11 00:00:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "202607110001"
down_revision: str | None = "202607080002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enum(bind, name: str, values: tuple[str, ...]):
    if bind.dialect.name == "postgresql":
        enum = postgresql.ENUM(*values, name=name)
        enum.create(bind, checkfirst=True)
        return postgresql.ENUM(*values, name=name, create_type=False)
    return sa.Enum(*values, name=name)


def upgrade() -> None:
    bind = op.get_bind()
    media_type = _enum(bind, "media_type", ("MOVIE", "SERIES", "BOOK", "GAME", "ALBUM", "TRACK"))
    seed_run_status = _enum(bind, "seed_run_status", ("PENDING", "RUNNING", "COMPLETED", "FAILED"))
    seed_item_status = _enum(bind, "seed_item_status", ("PENDING", "COMPLETED", "FAILED"))

    op.add_column("media_external_ids", sa.Column("attribution_text", sa.String(length=255), nullable=True))
    op.add_column("media_external_ids", sa.Column("attribution_url", sa.String(length=2048), nullable=True))
    op.create_table(
        "seed_runs",
        sa.Column("id", sa.Uuid(), nullable=False), sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("media_type", media_type, nullable=False), sa.Column("seed_kind", sa.String(length=100), nullable=False),
        sa.Column("cursor", sa.String(length=255), nullable=False, server_default="initial"), sa.Column("status", seed_run_status, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True), sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_seen", sa.Integer(), nullable=False, server_default="0"), sa.Column("total_inserted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_updated", sa.Integer(), nullable=False, server_default="0"), sa.Column("total_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_seed_runs_provider_type_kind_cursor", "seed_runs", ["provider", "media_type", "seed_kind", "cursor"], unique=True)
    op.create_table(
        "seed_items",
        sa.Column("id", sa.Uuid(), nullable=False), sa.Column("seed_run_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False), sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("raw_payload_json", sa.JSON(), nullable=True), sa.Column("normalized_payload_json", sa.JSON(), nullable=True),
        sa.Column("status", seed_item_status, nullable=False), sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["seed_run_id"], ["seed_runs.id"], ondelete="CASCADE"), sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_seed_items_run_provider_external", "seed_items", ["seed_run_id", "provider", "external_id"], unique=True)
    op.create_index("ix_seed_items_run_status", "seed_items", ["seed_run_id", "status"])
    op.create_table(
        "provider_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False), sa.Column("seed_item_id", sa.Uuid(), nullable=True),
        sa.Column("provider", sa.String(length=50), nullable=False), sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["seed_item_id"], ["seed_items.id"], ondelete="SET NULL"), sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_provider_snapshots_provider_external_created", "provider_snapshots", ["provider", "external_id", "created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    op.drop_index("ix_provider_snapshots_provider_external_created", table_name="provider_snapshots")
    op.drop_table("provider_snapshots")
    op.drop_index("ix_seed_items_run_status", table_name="seed_items")
    op.drop_index("ix_seed_items_run_provider_external", table_name="seed_items")
    op.drop_table("seed_items")
    op.drop_index("ix_seed_runs_provider_type_kind_cursor", table_name="seed_runs")
    op.drop_table("seed_runs")
    op.drop_column("media_external_ids", "attribution_url")
    op.drop_column("media_external_ids", "attribution_text")
    if bind.dialect.name == "postgresql":
        postgresql.ENUM(name="seed_item_status").drop(bind, checkfirst=True)
        postgresql.ENUM(name="seed_run_status").drop(bind, checkfirst=True)
