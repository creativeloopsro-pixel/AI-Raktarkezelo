"""organization AI API keys

Revision ID: b7e19c4a2d63
Revises: f18b7d2a6c40
Create Date: 2026-07-26 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b7e19c4a2d63"
down_revision: str | None = "f18b7d2a6c40"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "organization_ai_settings",
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column(
            "provider",
            sa.String(length=40),
            nullable=False,
            server_default="ollama",
        ),
        sa.Column("api_key_encrypted", sa.String(length=4096), nullable=True),
        sa.Column("api_key_last_four", sa.String(length=4), nullable=True),
        sa.Column("updated_by", sa.String(length=36), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("organization_id"),
    )


def downgrade() -> None:
    op.drop_table("organization_ai_settings")
