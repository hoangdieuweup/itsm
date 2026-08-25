"""create_project_roles_schema

Revision ID: a3f7d9c2e5b1
Revises: f4c8b2e91a37
Create Date: 2026-08-25 12:00:00.000000

Adds project-scoped roles: a ProjectRole is an assignable bundle of the
existing global permission catalog's atoms (FK'd by id, no duplicate
catalog), restricted at the service layer to
ProjectScopedPermissionCatalog.ASSIGNABLE. A member's effective
permission set in a project becomes the UNION of their global
permissions and their assigned project role's permissions (see
docs/superpowers/plans/2026-08-25-project-scoped-permissions.md) —
project_role_id is nullable and additive, so every existing
project_members row keeps today's exact behavior until someone
explicitly creates and assigns a role.
"""

import sqlalchemy as sa

from alembic import op

revision = "a3f7d9c2e5b1"
down_revision = "f4c8b2e91a37"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_roles",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("project_roles_project_id_fkey"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("project_roles_pkey")),
        sa.UniqueConstraint("project_id", "name", name="project_roles_project_id_name_key"),
    )
    op.create_index(op.f("project_roles_project_id_idx"), "project_roles", ["project_id"], unique=False)

    op.create_table(
        "project_role_permissions",
        sa.Column("project_role_id", sa.UUID(), nullable=False),
        sa.Column("permission_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_role_id"],
            ["project_roles.id"],
            name=op.f("project_role_permissions_project_role_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["permission_id"],
            ["permissions.id"],
            name=op.f("project_role_permissions_permission_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "project_role_id", "permission_id", name=op.f("project_role_permissions_pkey")
        ),
    )

    op.add_column("project_members", sa.Column("project_role_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f("project_members_project_role_id_fkey"),
        "project_members",
        "project_roles",
        ["project_role_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("project_members_project_role_id_fkey"), "project_members", type_="foreignkey")
    op.drop_column("project_members", "project_role_id")
    op.drop_table("project_role_permissions")
    op.drop_index(op.f("project_roles_project_id_idx"), table_name="project_roles")
    op.drop_table("project_roles")
