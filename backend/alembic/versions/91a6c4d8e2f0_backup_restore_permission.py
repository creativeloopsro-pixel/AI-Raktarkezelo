"""backup restore permission

Revision ID: 91a6c4d8e2f0
Revises: 7d2b4e8a91c3
Create Date: 2026-07-29 14:00:00.000000
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision: str = "91a6c4d8e2f0"
down_revision: str | None = "7d2b4e8a91c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    permission_id = connection.scalar(
        sa.text("SELECT id FROM permissions WHERE code = :code"),
        {"code": "backups.restore"},
    )
    if permission_id is None:
        permission_id = str(uuid4())
        connection.execute(
            sa.text(
                """
                INSERT INTO permissions
                    (id, code, name, description, category, created_at)
                VALUES
                    (:id, :code, :name, :description, :category, :created_at)
                """
            ),
            {
                "id": permission_id,
                "code": "backups.restore",
                "name": "Biztonsági mentés visszaállítása",
                "description": "",
                "category": "system",
                "created_at": datetime.now(UTC),
            },
        )

    admin_roles = connection.execute(
        sa.text("SELECT id, organization_id FROM roles WHERE slug = :slug"),
        {"slug": "admin"},
    ).mappings()
    for role in admin_roles:
        existing = connection.scalar(
            sa.text(
                """
                SELECT id
                FROM role_permissions
                WHERE role_id = :role_id AND permission_id = :permission_id
                """
            ),
            {"role_id": role["id"], "permission_id": permission_id},
        )
        if existing is None:
            connection.execute(
                sa.text(
                    """
                    INSERT INTO role_permissions
                        (id, organization_id, role_id, permission_id, granted_by, created_at)
                    VALUES
                        (:id, :organization_id, :role_id, :permission_id, NULL, :created_at)
                    """
                ),
                {
                    "id": str(uuid4()),
                    "organization_id": role["organization_id"],
                    "role_id": role["id"],
                    "permission_id": permission_id,
                    "created_at": datetime.now(UTC),
                },
            )


def downgrade() -> None:
    connection = op.get_bind()
    permission_id = connection.scalar(
        sa.text("SELECT id FROM permissions WHERE code = :code"),
        {"code": "backups.restore"},
    )
    if permission_id is None:
        return
    connection.execute(
        sa.text("DELETE FROM role_permissions WHERE permission_id = :permission_id"),
        {"permission_id": permission_id},
    )
    connection.execute(
        sa.text("DELETE FROM permissions WHERE id = :permission_id"),
        {"permission_id": permission_id},
    )
