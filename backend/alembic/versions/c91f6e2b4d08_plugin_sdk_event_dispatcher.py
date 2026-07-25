"""plugin sdk and event dispatcher

Revision ID: c91f6e2b4d08
Revises: a84d83f4e7b1
Create Date: 2026-07-25 19:10:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c91f6e2b4d08"
down_revision: Union[str, None] = "a84d83f4e7b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "plugins",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("plugin_key", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("active_version", sa.String(length=40), nullable=False),
        sa.Column("is_builtin", sa.Boolean(), nullable=False),
        sa.Column("service_user_id", sa.String(length=36), nullable=False),
        sa.Column("installed_by", sa.String(length=36), nullable=True),
        sa.Column("enabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("installed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["installed_by"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["service_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "plugin_key", name="uq_plugin_org_key"
        ),
    )
    op.create_index(
        op.f("ix_plugins_organization_id"),
        "plugins",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_plugins_service_user_id"),
        "plugins",
        ["service_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_plugin_org_status",
        "plugins",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_table(
        "plugin_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("plugin_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.String(length=40), nullable=False),
        sa.Column("api_version", sa.String(length=20), nullable=False),
        sa.Column("manifest", sa.JSON(), nullable=False),
        sa.Column("installed_by", sa.String(length=36), nullable=True),
        sa.Column("installed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["installed_by"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["plugin_id"], ["plugins.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plugin_id", "version", name="uq_plugin_version"),
    )
    op.create_index(
        op.f("ix_plugin_versions_organization_id"),
        "plugin_versions",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_plugin_versions_plugin_id"),
        "plugin_versions",
        ["plugin_id"],
        unique=False,
    )
    op.create_table(
        "plugin_permissions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("plugin_id", sa.String(length=36), nullable=False),
        sa.Column("permission", sa.String(length=100), nullable=False),
        sa.Column("granted", sa.Boolean(), nullable=False),
        sa.Column("granted_by", sa.String(length=36), nullable=True),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["granted_by"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["plugin_id"], ["plugins.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "plugin_id", "permission", name="uq_plugin_permission"
        ),
    )
    op.create_index(
        op.f("ix_plugin_permissions_organization_id"),
        "plugin_permissions",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_plugin_permissions_plugin_id"),
        "plugin_permissions",
        ["plugin_id"],
        unique=False,
    )
    op.create_table(
        "plugin_settings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("plugin_id", sa.String(length=36), nullable=False),
        sa.Column("setting_key", sa.String(length=100), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("is_secret", sa.Boolean(), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["plugin_id"], ["plugins.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "plugin_id", "setting_key", name="uq_plugin_setting_key"
        ),
    )
    op.create_index(
        op.f("ix_plugin_settings_organization_id"),
        "plugin_settings",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_plugin_settings_plugin_id"),
        "plugin_settings",
        ["plugin_id"],
        unique=False,
    )
    op.create_table(
        "plugin_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("plugin_id", sa.String(length=36), nullable=False),
        sa.Column("outbox_event_id", sa.String(length=36), nullable=False),
        sa.Column("plugin_version", sa.String(length=40), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("aggregate_type", sa.String(length=80), nullable=False),
        sa.Column("aggregate_id", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.String(length=1000), nullable=True),
        sa.Column("correlation_id", sa.String(length=80), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["outbox_event_id"], ["outbox_events.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["plugin_id"], ["plugins.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_plugin_job_org_idempotency",
        ),
        sa.UniqueConstraint(
            "plugin_id", "outbox_event_id", name="uq_plugin_job_event"
        ),
    )
    op.create_index(
        op.f("ix_plugin_jobs_correlation_id"),
        "plugin_jobs",
        ["correlation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_plugin_jobs_organization_id"),
        "plugin_jobs",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_plugin_jobs_outbox_event_id"),
        "plugin_jobs",
        ["outbox_event_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_plugin_jobs_plugin_id"),
        "plugin_jobs",
        ["plugin_id"],
        unique=False,
    )
    op.create_index(
        "ix_plugin_job_status_due",
        "plugin_jobs",
        ["status", "next_attempt_at", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_plugin_job_status_due", table_name="plugin_jobs")
    op.drop_index(
        op.f("ix_plugin_jobs_plugin_id"), table_name="plugin_jobs"
    )
    op.drop_index(
        op.f("ix_plugin_jobs_outbox_event_id"), table_name="plugin_jobs"
    )
    op.drop_index(
        op.f("ix_plugin_jobs_organization_id"), table_name="plugin_jobs"
    )
    op.drop_index(
        op.f("ix_plugin_jobs_correlation_id"), table_name="plugin_jobs"
    )
    op.drop_table("plugin_jobs")
    op.drop_index(
        op.f("ix_plugin_settings_plugin_id"), table_name="plugin_settings"
    )
    op.drop_index(
        op.f("ix_plugin_settings_organization_id"), table_name="plugin_settings"
    )
    op.drop_table("plugin_settings")
    op.drop_index(
        op.f("ix_plugin_permissions_plugin_id"),
        table_name="plugin_permissions",
    )
    op.drop_index(
        op.f("ix_plugin_permissions_organization_id"),
        table_name="plugin_permissions",
    )
    op.drop_table("plugin_permissions")
    op.drop_index(
        op.f("ix_plugin_versions_plugin_id"), table_name="plugin_versions"
    )
    op.drop_index(
        op.f("ix_plugin_versions_organization_id"),
        table_name="plugin_versions",
    )
    op.drop_table("plugin_versions")
    op.drop_index("ix_plugin_org_status", table_name="plugins")
    op.drop_index(op.f("ix_plugins_service_user_id"), table_name="plugins")
    op.drop_index(op.f("ix_plugins_organization_id"), table_name="plugins")
    op.drop_table("plugins")
