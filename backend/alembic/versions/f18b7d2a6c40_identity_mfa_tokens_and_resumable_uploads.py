"""identity, MFA, API tokens and resumable uploads

Revision ID: f18b7d2a6c40
Revises: e47a1c9d5f02
Create Date: 2026-07-25 22:15:00.000000
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision: str = "f18b7d2a6c40"
down_revision: str | None = "e47a1c9d5f02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


PERMISSIONS = (
    ("system.admin", "Rendszeradminisztráció", "identity"),
    ("users.read", "Felhasználók megtekintése", "identity"),
    ("users.write", "Felhasználók kezelése", "identity"),
    ("roles.read", "Szerepkörök megtekintése", "identity"),
    ("roles.write", "Szerepkörök kezelése", "identity"),
    ("sessions.read", "Munkamenetek megtekintése", "identity"),
    ("sessions.revoke", "Munkamenetek visszavonása", "identity"),
    ("tokens.read", "API-tokenek megtekintése", "identity"),
    ("tokens.create", "API-tokenek létrehozása", "identity"),
    ("tokens.revoke", "API-tokenek visszavonása", "identity"),
    ("products.read", "Termékek megtekintése", "catalog"),
    ("products.write", "Termékek kezelése", "catalog"),
    ("stock.read", "Készlet megtekintése", "inventory"),
    ("stock.receive", "Bevételezés", "inventory"),
    ("stock.correct", "Készletkorrekció", "inventory"),
    ("stock.reverse", "Készletmozgás visszavonása", "inventory"),
    ("inventory.count", "Kézi leltár", "inventory"),
    ("inventory.approve", "Leltár jóváhagyása", "inventory"),
    ("documents.read", "Dokumentumok megtekintése", "documents"),
    ("documents.upload", "Dokumentumfeltöltés", "documents"),
    ("documents.process", "Dokumentumfeldolgozás", "documents"),
    ("receipts.read", "Bevételezési tervezetek megtekintése", "documents"),
    ("receipts.confirm", "Bevételezés jóváhagyása", "documents"),
    ("reviews.read", "Ellenőrzések megtekintése", "reviews"),
    ("reviews.resolve", "Ellenőrzések lezárása", "reviews"),
    ("vrp.read", "VRP-importok megtekintése", "vrp"),
    ("vrp.upload", "VRP-fájlok feltöltése", "vrp"),
    ("vrp.process", "VRP-importok feldolgozása", "vrp"),
    ("vrp.settings", "VRP-beállítások kezelése", "vrp"),
    ("email.read", "E-mailes beérkezés megtekintése", "email"),
    ("email.manage", "E-mailes beérkezés kezelése", "email"),
    ("plugins.read", "Pluginok megtekintése", "plugins"),
    ("plugins.manage", "Pluginok kezelése", "plugins"),
    ("reports.read", "Riportok megtekintése", "reports"),
    ("reports.generate", "Riportok létrehozása", "reports"),
    ("notifications.read", "Értesítések megtekintése", "system"),
    ("settings.read", "Beállítások megtekintése", "system"),
    ("settings.write", "Beállítások kezelése", "system"),
)

MANAGER_PERMISSIONS = {
    "products.read",
    "products.write",
    "stock.read",
    "stock.receive",
    "stock.correct",
    "stock.reverse",
    "inventory.count",
    "inventory.approve",
    "documents.read",
    "documents.upload",
    "documents.process",
    "receipts.read",
    "receipts.confirm",
    "reviews.read",
    "reviews.resolve",
    "vrp.read",
    "vrp.upload",
    "vrp.process",
    "reports.read",
    "reports.generate",
    "notifications.read",
    "sessions.read",
}
WAREHOUSE_PERMISSIONS = {
    "products.read",
    "stock.read",
    "stock.receive",
    "inventory.count",
    "documents.read",
    "documents.upload",
    "documents.process",
    "receipts.read",
    "receipts.confirm",
    "reviews.read",
    "vrp.read",
    "vrp.upload",
}
VIEWER_PERMISSIONS = {
    "products.read",
    "stock.read",
    "documents.read",
    "receipts.read",
    "reviews.read",
    "vrp.read",
    "reports.read",
    "notifications.read",
}
SERVICE_PERMISSIONS = {
    "products.read",
    "stock.read",
    "documents.read",
}


def upgrade() -> None:
    op.create_table(
        "roles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "slug", name="uq_role_org_slug"),
    )
    op.create_index("ix_roles_organization_id", "roles", ["organization_id"])

    op.create_table(
        "permissions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("code", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_permissions_code", "permissions", ["code"], unique=True)

    op.create_table(
        "role_permissions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("role_id", sa.String(length=36), nullable=False),
        sa.Column("permission_id", sa.String(length=36), nullable=False),
        sa.Column("granted_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["granted_by"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["permission_id"], ["permissions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),
    )
    op.create_index(
        "ix_role_permissions_organization_id",
        "role_permissions",
        ["organization_id"],
    )
    op.create_index("ix_role_permissions_role_id", "role_permissions", ["role_id"])
    op.create_index(
        "ix_role_permissions_permission_id",
        "role_permissions",
        ["permission_id"],
    )

    op.create_table(
        "user_roles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("role_id", sa.String(length=36), nullable=False),
        sa.Column("assigned_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["assigned_by"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "role_id", name="uq_user_role"),
    )
    op.create_index("ix_user_roles_organization_id", "user_roles", ["organization_id"])
    op.create_index("ix_user_roles_user_id", "user_roles", ["user_id"])
    op.create_index("ix_user_roles_role_id", "user_roles", ["role_id"])

    op.create_table(
        "user_mfa_methods",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("secret_encrypted", sa.String(length=500), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("last_used_counter", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_user_mfa_methods_user_id",
        "user_mfa_methods",
        ["user_id"],
        unique=True,
    )

    op.create_table(
        "mfa_recovery_codes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("mfa_method_id", sa.String(length=36), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["mfa_method_id"], ["user_mfa_methods.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "mfa_method_id", "code_hash", name="uq_mfa_recovery_code"
        ),
    )
    op.create_index(
        "ix_mfa_recovery_codes_mfa_method_id",
        "mfa_recovery_codes",
        ["mfa_method_id"],
    )

    op.add_column(
        "refresh_sessions",
        sa.Column("organization_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "refresh_sessions",
        sa.Column("family_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "refresh_sessions",
        sa.Column("replaced_by_session_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "refresh_sessions",
        sa.Column("mfa_verified", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "refresh_sessions",
        sa.Column("user_agent", sa.String(length=500), server_default="", nullable=False),
    )
    op.add_column(
        "refresh_sessions",
        sa.Column("ip_address", sa.String(length=64), server_default="", nullable=False),
    )
    op.add_column(
        "refresh_sessions",
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "refresh_sessions",
        sa.Column("revoke_reason", sa.String(length=120), nullable=True),
    )
    connection = op.get_bind()
    existing_sessions = connection.execute(
        sa.text("SELECT id, user_id, created_at FROM refresh_sessions")
    ).mappings()
    for row in existing_sessions:
        organization_id = connection.execute(
            sa.text("SELECT organization_id FROM users WHERE id = :user_id"),
            {"user_id": row["user_id"]},
        ).scalar_one()
        connection.execute(
            sa.text(
                """
                UPDATE refresh_sessions
                   SET organization_id = :organization_id,
                       family_id = :family_id,
                       last_seen_at = :last_seen_at
                 WHERE id = :session_id
                """
            ),
            {
                "organization_id": organization_id,
                "family_id": str(uuid4()),
                "last_seen_at": row["created_at"],
                "session_id": row["id"],
            },
        )
    op.alter_column("refresh_sessions", "organization_id", nullable=False)
    op.alter_column("refresh_sessions", "family_id", nullable=False)
    op.alter_column("refresh_sessions", "last_seen_at", nullable=False)
    op.create_foreign_key(
        "fk_refresh_sessions_organization_id",
        "refresh_sessions",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_refresh_sessions_replaced_by",
        "refresh_sessions",
        "refresh_sessions",
        ["replaced_by_session_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_refresh_sessions_organization_id",
        "refresh_sessions",
        ["organization_id"],
    )
    op.create_index(
        "ix_refresh_sessions_family_id",
        "refresh_sessions",
        ["family_id"],
    )

    op.create_table(
        "api_tokens",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("token_prefix", sa.String(length=20), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "token_hash", name="uq_api_token_org_hash"
        ),
    )
    op.create_index("ix_api_tokens_organization_id", "api_tokens", ["organization_id"])
    op.create_index("ix_api_tokens_user_id", "api_tokens", ["user_id"])
    op.create_index("ix_api_tokens_token_prefix", "api_tokens", ["token_prefix"])

    op.create_table(
        "resumable_upload_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("client_upload_id", sa.String(length=80), nullable=False),
        sa.Column("target_type", sa.String(length=24), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("declared_content_type", sa.String(length=160), nullable=True),
        sa.Column("total_size", sa.BigInteger(), nullable=False),
        sa.Column("chunk_size", sa.Integer(), nullable=False),
        sa.Column("total_chunks", sa.Integer(), nullable=False),
        sa.Column("received_chunks", sa.JSON(), nullable=False),
        sa.Column("chunk_hashes", sa.JSON(), nullable=False),
        sa.Column("file_sha256", sa.String(length=64), nullable=True),
        sa.Column("upload_metadata", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("result_entity_type", sa.String(length=40), nullable=True),
        sa.Column("result_entity_id", sa.String(length=36), nullable=True),
        sa.Column("last_error_code", sa.String(length=120), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "client_upload_id",
            name="uq_resumable_upload_org_client",
        ),
    )
    op.create_index(
        "ix_resumable_upload_sessions_organization_id",
        "resumable_upload_sessions",
        ["organization_id"],
    )
    op.create_index(
        "ix_resumable_upload_sessions_created_by",
        "resumable_upload_sessions",
        ["created_by"],
    )
    op.create_index(
        "ix_resumable_upload_org_status_updated",
        "resumable_upload_sessions",
        ["organization_id", "status", "updated_at"],
    )

    now = sa.func.now()
    permission_rows = []
    permission_ids: dict[str, str] = {}
    for code, name, category in PERMISSIONS:
        permission_id = str(uuid4())
        permission_ids[code] = permission_id
        permission_rows.append(
            {
                "id": permission_id,
                "code": code,
                "name": name,
                "description": "",
                "category": category,
            }
        )
    permissions_table = sa.table(
        "permissions",
        sa.column("id", sa.String),
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.String),
        sa.column("category", sa.String),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        permissions_table,
        [
            {
                **row,
                "created_at": connection.execute(sa.select(now)).scalar_one(),
            }
            for row in permission_rows
        ],
    )

    organizations = connection.execute(sa.text("SELECT id FROM organizations")).scalars()
    all_permission_codes = set(permission_ids)
    role_specs = (
        ("admin", "Tulajdonos / Admin", all_permission_codes),
        ("manager", "Üzletvezető", MANAGER_PERMISSIONS),
        ("warehouse", "Eladó / Raktári felhasználó", WAREHOUSE_PERMISSIONS),
        ("viewer", "Ellenőr / Megtekintő", VIEWER_PERMISSIONS),
        ("service", "Plugin szolgáltatásfiók", SERVICE_PERMISSIONS),
    )
    for organization_id in organizations:
        role_ids: dict[str, str] = {}
        timestamp = connection.execute(sa.select(now)).scalar_one()
        for slug, name, permission_codes in role_specs:
            role_id = str(uuid4())
            role_ids[slug] = role_id
            connection.execute(
                sa.text(
                    """
                    INSERT INTO roles
                        (id, organization_id, name, slug, description,
                         is_system, created_at, updated_at)
                    VALUES
                        (:id, :organization_id, :name, :slug, '',
                         true, :created_at, :updated_at)
                    """
                ),
                {
                    "id": role_id,
                    "organization_id": organization_id,
                    "name": name,
                    "slug": slug,
                    "created_at": timestamp,
                    "updated_at": timestamp,
                },
            )
            for code in permission_codes:
                connection.execute(
                    sa.text(
                        """
                        INSERT INTO role_permissions
                            (id, organization_id, role_id, permission_id,
                             granted_by, created_at)
                        VALUES
                            (:id, :organization_id, :role_id, :permission_id,
                             NULL, :created_at)
                        """
                    ),
                    {
                        "id": str(uuid4()),
                        "organization_id": organization_id,
                        "role_id": role_id,
                        "permission_id": permission_ids[code],
                        "created_at": timestamp,
                    },
                )

        users = connection.execute(
            sa.text(
                "SELECT id, role FROM users WHERE organization_id = :organization_id"
            ),
            {"organization_id": organization_id},
        ).mappings()
        for user in users:
            legacy_slug = str(user["role"]).lower()
            if legacy_slug in {"plugin", "plugin_service"}:
                legacy_slug = "service"
            if legacy_slug not in role_ids:
                legacy_slug = "warehouse"
            connection.execute(
                sa.text(
                    """
                    INSERT INTO user_roles
                        (id, organization_id, user_id, role_id, assigned_by, created_at)
                    VALUES
                        (:id, :organization_id, :user_id, :role_id, NULL, :created_at)
                    """
                ),
                {
                    "id": str(uuid4()),
                    "organization_id": organization_id,
                    "user_id": user["id"],
                    "role_id": role_ids[legacy_slug],
                    "created_at": timestamp,
                },
            )


def downgrade() -> None:
    op.drop_index(
        "ix_resumable_upload_org_status_updated",
        table_name="resumable_upload_sessions",
    )
    op.drop_index(
        "ix_resumable_upload_sessions_created_by",
        table_name="resumable_upload_sessions",
    )
    op.drop_index(
        "ix_resumable_upload_sessions_organization_id",
        table_name="resumable_upload_sessions",
    )
    op.drop_table("resumable_upload_sessions")

    op.drop_index("ix_api_tokens_token_prefix", table_name="api_tokens")
    op.drop_index("ix_api_tokens_user_id", table_name="api_tokens")
    op.drop_index("ix_api_tokens_organization_id", table_name="api_tokens")
    op.drop_table("api_tokens")

    op.drop_index("ix_refresh_sessions_family_id", table_name="refresh_sessions")
    op.drop_index(
        "ix_refresh_sessions_organization_id", table_name="refresh_sessions"
    )
    op.drop_constraint(
        "fk_refresh_sessions_replaced_by", "refresh_sessions", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_refresh_sessions_organization_id",
        "refresh_sessions",
        type_="foreignkey",
    )
    op.drop_column("refresh_sessions", "revoke_reason")
    op.drop_column("refresh_sessions", "last_seen_at")
    op.drop_column("refresh_sessions", "ip_address")
    op.drop_column("refresh_sessions", "user_agent")
    op.drop_column("refresh_sessions", "mfa_verified")
    op.drop_column("refresh_sessions", "replaced_by_session_id")
    op.drop_column("refresh_sessions", "family_id")
    op.drop_column("refresh_sessions", "organization_id")

    op.drop_index(
        "ix_mfa_recovery_codes_mfa_method_id", table_name="mfa_recovery_codes"
    )
    op.drop_table("mfa_recovery_codes")
    op.drop_index("ix_user_mfa_methods_user_id", table_name="user_mfa_methods")
    op.drop_table("user_mfa_methods")
    op.drop_index("ix_user_roles_role_id", table_name="user_roles")
    op.drop_index("ix_user_roles_user_id", table_name="user_roles")
    op.drop_index("ix_user_roles_organization_id", table_name="user_roles")
    op.drop_table("user_roles")
    op.drop_index(
        "ix_role_permissions_permission_id", table_name="role_permissions"
    )
    op.drop_index("ix_role_permissions_role_id", table_name="role_permissions")
    op.drop_index(
        "ix_role_permissions_organization_id", table_name="role_permissions"
    )
    op.drop_table("role_permissions")
    op.drop_index("ix_permissions_code", table_name="permissions")
    op.drop_table("permissions")
    op.drop_index("ix_roles_organization_id", table_name="roles")
    op.drop_table("roles")
