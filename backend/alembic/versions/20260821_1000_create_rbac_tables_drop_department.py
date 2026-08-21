"""create rbac tables, drop department and user role

Revision ID: 9a1f3c6de072
Revises: 5ebc211a92a1
Create Date: 2026-08-21 10:00:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "9a1f3c6de072"
down_revision = "5ebc211a92a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(op.f("users_department_id_fkey"), "users", type_="foreignkey")
    op.drop_index(op.f("users_department_id_idx"), table_name="users")
    op.drop_column("users", "department_id")
    op.drop_column("users", "role")
    op.drop_index(op.f("departments_code_idx"), table_name="departments")
    op.drop_table("departments")

    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("is_system", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("roles_pkey")),
    )
    op.create_index(op.f("roles_name_idx"), "roles", ["name"], unique=True)

    op.create_table(
        "permissions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("resource", sa.String(length=100), nullable=False),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("permissions_pkey")),
        sa.UniqueConstraint("resource", "action", name=op.f("permissions_resource_key")),
    )

    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("permission_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["role_id"], ["roles.id"], name=op.f("role_permissions_role_id_fkey"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["permission_id"],
            ["permissions.id"],
            name=op.f("role_permissions_permission_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("role_id", "permission_id", name=op.f("role_permissions_pkey")),
    )

    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("user_roles_user_id_fkey"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["role_id"], ["roles.id"], name=op.f("user_roles_role_id_fkey"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("user_roles_pkey")),
    )
    op.create_index(op.f("user_roles_role_id_idx"), "user_roles", ["role_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("user_roles_role_id_idx"), table_name="user_roles")
    op.drop_table("user_roles")
    op.drop_table("role_permissions")
    op.drop_table("permissions")
    op.drop_index(op.f("roles_name_idx"), table_name="roles")
    op.drop_table("roles")

    op.add_column("users", sa.Column("role", sa.String(length=20), nullable=True))
    op.execute("UPDATE users SET role = 'member'")
    op.alter_column("users", "role", nullable=False)
    op.add_column("users", sa.Column("department_id", sa.Integer(), nullable=True))
    op.create_table(
        "departments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("departments_pkey")),
    )
    op.create_index(op.f("departments_code_idx"), "departments", ["code"], unique=True)
    op.create_index(op.f("users_department_id_idx"), "users", ["department_id"], unique=False)
    op.create_foreign_key(
        op.f("users_department_id_fkey"), "users", "departments", ["department_id"], ["id"], ondelete="SET NULL"
    )
