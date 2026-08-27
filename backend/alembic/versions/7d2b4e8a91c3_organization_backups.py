"""organization backups

Revision ID: 7d2b4e8a91c3
Revises: a19e4c7d2b31
Create Date: 2026-07-29 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "7d2b4e8a91c3"
down_revision: str | None = "a19e4c7d2b31"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "backup_schedules",
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "frequency",
            sa.String(length=20),
            nullable=False,
            server_default="WEEKLY",
        ),
        sa.Column(
            "backup_time",
            sa.Time(),
            nullable=False,
            server_default="02:00:00",
        ),
        sa.Column(
            "timezone",
            sa.String(length=80),
            nullable=False,
            server_default="Europe/Bratislava",
        ),
        sa.Column(
            "weekly_day",
            sa.String(length=16),
            nullable=False,
            server_default="SUNDAY",
        ),
        sa.Column(
            "monthly_rule",
            sa.String(length=16),
            nullable=False,
            server_default="LAST_DAY",
        ),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "last_status",
            sa.String(length=24),
            nullable=False,
            server_default="NEVER",
        ),
        sa.Column("last_error_message", sa.String(length=500), nullable=True),
        sa.Column("last_object_key", sa.String(length=500), nullable=True),
        sa.Column("last_filename", sa.String(length=255), nullable=True),
        sa.Column("last_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("last_sha256", sa.String(length=64), nullable=True),
        sa.Column("updated_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("organization_id"),
    )


def downgrade() -> None:
    op.drop_table("backup_schedules")
