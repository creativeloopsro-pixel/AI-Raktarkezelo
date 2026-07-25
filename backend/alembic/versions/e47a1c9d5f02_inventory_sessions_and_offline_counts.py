"""inventory sessions and offline counts

Revision ID: e47a1c9d5f02
Revises: c91f6e2b4d08
Create Date: 2026-07-25 20:05:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e47a1c9d5f02"
down_revision: Union[str, None] = "c91f6e2b4d08"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "inventory_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("client_session_id", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("approval_required", sa.Boolean(), nullable=False),
        sa.Column("started_by", sa.String(length=36), nullable=True),
        sa.Column("completed_by", sa.String(length=36), nullable=True),
        sa.Column("approved_by", sa.String(length=36), nullable=True),
        sa.Column("review_task_id", sa.String(length=36), nullable=True),
        sa.Column("completion_note", sa.String(length=1000), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["approved_by"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["completed_by"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["review_task_id"], ["review_tasks.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["started_by"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "client_session_id",
            name="uq_inventory_session_org_client",
        ),
    )
    op.create_index(
        op.f("ix_inventory_sessions_organization_id"),
        "inventory_sessions",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_inventory_session_org_status",
        "inventory_sessions",
        ["organization_id", "status", "started_at"],
        unique=False,
    )
    op.create_table(
        "inventory_counts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("product_id", sa.String(length=36), nullable=False),
        sa.Column("client_operation_id", sa.String(length=80), nullable=False),
        sa.Column(
            "expected_quantity", sa.Numeric(precision=18, scale=3), nullable=False
        ),
        sa.Column(
            "client_expected_quantity",
            sa.Numeric(precision=18, scale=3),
            nullable=True,
        ),
        sa.Column(
            "counted_quantity", sa.Numeric(precision=18, scale=3), nullable=False
        ),
        sa.Column(
            "quantity_difference",
            sa.Numeric(precision=18, scale=3),
            nullable=False,
        ),
        sa.Column("scanned_code", sa.String(length=128), nullable=True),
        sa.Column("reason_code", sa.String(length=60), nullable=True),
        sa.Column("reason_note", sa.String(length=500), nullable=True),
        sa.Column("recorded_by", sa.String(length=36), nullable=True),
        sa.Column(
            "client_recorded_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["product_id"], ["products.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["inventory_sessions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "client_operation_id",
            name="uq_inventory_count_org_operation",
        ),
    )
    op.create_index(
        op.f("ix_inventory_counts_organization_id"),
        "inventory_counts",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_inventory_counts_product_id"),
        "inventory_counts",
        ["product_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_inventory_counts_session_id"),
        "inventory_counts",
        ["session_id"],
        unique=False,
    )
    op.create_index(
        "ix_inventory_count_session_product_recorded",
        "inventory_counts",
        ["session_id", "product_id", "client_recorded_at"],
        unique=False,
    )
    op.create_table(
        "stock_corrections",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("count_id", sa.String(length=36), nullable=False),
        sa.Column("product_id", sa.String(length=36), nullable=False),
        sa.Column("movement_id", sa.String(length=36), nullable=False),
        sa.Column(
            "expected_quantity", sa.Numeric(precision=18, scale=3), nullable=False
        ),
        sa.Column(
            "counted_quantity", sa.Numeric(precision=18, scale=3), nullable=False
        ),
        sa.Column(
            "quantity_delta", sa.Numeric(precision=18, scale=3), nullable=False
        ),
        sa.Column("reason_code", sa.String(length=60), nullable=False),
        sa.Column("reason_note", sa.String(length=500), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("approved_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["approved_by"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["count_id"], ["inventory_counts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["movement_id"], ["stock_movements.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["product_id"], ["products.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["inventory_sessions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("count_id", name="uq_stock_correction_count"),
        sa.UniqueConstraint("movement_id"),
    )
    op.create_index(
        op.f("ix_stock_corrections_count_id"),
        "stock_corrections",
        ["count_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_stock_corrections_organization_id"),
        "stock_corrections",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_stock_corrections_product_id"),
        "stock_corrections",
        ["product_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_stock_corrections_session_id"),
        "stock_corrections",
        ["session_id"],
        unique=False,
    )
    op.create_index(
        "ix_stock_correction_org_created",
        "stock_corrections",
        ["organization_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_stock_correction_org_created", table_name="stock_corrections"
    )
    op.drop_index(
        op.f("ix_stock_corrections_session_id"),
        table_name="stock_corrections",
    )
    op.drop_index(
        op.f("ix_stock_corrections_product_id"),
        table_name="stock_corrections",
    )
    op.drop_index(
        op.f("ix_stock_corrections_organization_id"),
        table_name="stock_corrections",
    )
    op.drop_index(
        op.f("ix_stock_corrections_count_id"),
        table_name="stock_corrections",
    )
    op.drop_table("stock_corrections")
    op.drop_index(
        "ix_inventory_count_session_product_recorded",
        table_name="inventory_counts",
    )
    op.drop_index(
        op.f("ix_inventory_counts_session_id"),
        table_name="inventory_counts",
    )
    op.drop_index(
        op.f("ix_inventory_counts_product_id"),
        table_name="inventory_counts",
    )
    op.drop_index(
        op.f("ix_inventory_counts_organization_id"),
        table_name="inventory_counts",
    )
    op.drop_table("inventory_counts")
    op.drop_index(
        "ix_inventory_session_org_status",
        table_name="inventory_sessions",
    )
    op.drop_index(
        op.f("ix_inventory_sessions_organization_id"),
        table_name="inventory_sessions",
    )
    op.drop_table("inventory_sessions")
