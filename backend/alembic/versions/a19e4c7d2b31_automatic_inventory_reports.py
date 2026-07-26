"""automatic inventory PDF reports

Revision ID: a19e4c7d2b31
Revises: b7e19c4a2d63
Create Date: 2026-07-26 18:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a19e4c7d2b31"
down_revision: str | None = "b7e19c4a2d63"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "inventory_report_schedules",
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "frequency",
            sa.String(length=20),
            nullable=False,
            server_default="WEEKLY",
        ),
        sa.Column(
            "generation_time",
            sa.Time(),
            nullable=False,
            server_default="06:00:00",
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
            server_default="MONDAY",
        ),
        sa.Column(
            "monthly_rule",
            sa.String(length=16),
            nullable=False,
            server_default="LAST_DAY",
        ),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_document_id", sa.String(length=36), nullable=True),
        sa.Column("last_error_message", sa.String(length=500), nullable=True),
        sa.Column("updated_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["last_document_id"], ["documents.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("organization_id"),
    )
    op.create_table(
        "inventory_report_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.String(length=24),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("document_id", sa.String(length=36), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"], ["documents.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "scheduled_for",
            name="uq_inventory_report_run_org_scheduled",
        ),
    )
    op.create_index(
        "ix_inventory_report_runs_organization_id",
        "inventory_report_runs",
        ["organization_id"],
    )
    op.create_index(
        "ix_inventory_report_run_status_next",
        "inventory_report_runs",
        ["status", "next_attempt_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_inventory_report_run_status_next",
        table_name="inventory_report_runs",
    )
    op.drop_index(
        "ix_inventory_report_runs_organization_id",
        table_name="inventory_report_runs",
    )
    op.drop_table("inventory_report_runs")
    op.drop_table("inventory_report_schedules")
