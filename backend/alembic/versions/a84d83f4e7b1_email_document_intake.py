"""email document intake

Revision ID: a84d83f4e7b1
Revises: d32d2adc9a69
Create Date: 2026-07-25 18:25:00.000000
"""

from secrets import token_hex
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a84d83f4e7b1"
down_revision: Union[str, None] = "d32d2adc9a69"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "email_inbound_settings",
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("routing_token", sa.String(length=48), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("auto_process", sa.Boolean(), nullable=False),
        sa.Column("allowed_sender_domains", sa.JSON(), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("organization_id"),
    )
    op.create_index(
        op.f("ix_email_inbound_settings_routing_token"),
        "email_inbound_settings",
        ["routing_token"],
        unique=True,
    )
    op.create_table(
        "inbound_emails",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("provider_message_id", sa.String(length=255), nullable=False),
        sa.Column("sender", sa.String(length=254), nullable=False),
        sa.Column("recipients", sa.JSON(), nullable=False),
        sa.Column("subject", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attachment_count", sa.Integer(), nullable=False),
        sa.Column("accepted_count", sa.Integer(), nullable=False),
        sa.Column("duplicate_count", sa.Integer(), nullable=False),
        sa.Column("rejected_count", sa.Integer(), nullable=False),
        sa.Column("error_summary", sa.JSON(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "provider",
            "provider_message_id",
            name="uq_inbound_email_org_provider_message",
        ),
    )
    op.create_index(
        op.f("ix_inbound_emails_organization_id"),
        "inbound_emails",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_inbound_email_org_status_received",
        "inbound_emails",
        ["organization_id", "status", "received_at"],
        unique=False,
    )
    op.create_table(
        "inbound_email_attachments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("email_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("declared_content_type", sa.String(length=120), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=True),
        sa.Column("rejection_code", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"], ["documents.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["email_id"], ["inbound_emails.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "email_id", "position", name="uq_inbound_attachment_position"
        ),
    )
    op.create_index(
        op.f("ix_inbound_email_attachments_content_sha256"),
        "inbound_email_attachments",
        ["content_sha256"],
        unique=False,
    )
    op.create_index(
        op.f("ix_inbound_email_attachments_document_id"),
        "inbound_email_attachments",
        ["document_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_inbound_email_attachments_email_id"),
        "inbound_email_attachments",
        ["email_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_inbound_email_attachments_organization_id"),
        "inbound_email_attachments",
        ["organization_id"],
        unique=False,
    )

    connection = op.get_bind()
    organizations = connection.execute(
        sa.text("SELECT id FROM organizations")
    ).fetchall()
    now = sa.func.now()
    settings_table = sa.table(
        "email_inbound_settings",
        sa.column("organization_id", sa.String),
        sa.column("routing_token", sa.String),
        sa.column("enabled", sa.Boolean),
        sa.column("auto_process", sa.Boolean),
        sa.column("allowed_sender_domains", sa.JSON),
        sa.column("updated_by", sa.String),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    for organization in organizations:
        connection.execute(
            settings_table.insert().values(
                organization_id=organization.id,
                routing_token=token_hex(12),
                enabled=True,
                auto_process=True,
                allowed_sender_domains=[],
                updated_by=None,
                created_at=now,
                updated_at=now,
            )
        )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_inbound_email_attachments_organization_id"),
        table_name="inbound_email_attachments",
    )
    op.drop_index(
        op.f("ix_inbound_email_attachments_email_id"),
        table_name="inbound_email_attachments",
    )
    op.drop_index(
        op.f("ix_inbound_email_attachments_document_id"),
        table_name="inbound_email_attachments",
    )
    op.drop_index(
        op.f("ix_inbound_email_attachments_content_sha256"),
        table_name="inbound_email_attachments",
    )
    op.drop_table("inbound_email_attachments")
    op.drop_index(
        "ix_inbound_email_org_status_received", table_name="inbound_emails"
    )
    op.drop_index(
        op.f("ix_inbound_emails_organization_id"), table_name="inbound_emails"
    )
    op.drop_table("inbound_emails")
    op.drop_index(
        op.f("ix_email_inbound_settings_routing_token"),
        table_name="email_inbound_settings",
    )
    op.drop_table("email_inbound_settings")
