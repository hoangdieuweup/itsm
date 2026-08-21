"""migrate user_roles to composite primary key for multi-role support

Revision ID: 3e8f1b2c4d5a
Revises: c4e8a1f92d36
Create Date: 2026-08-21 18:00:00.000000
"""

from alembic import op

revision = "3e8f1b2c4d5a"
down_revision = "c4e8a1f92d36"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("user_roles_pkey", "user_roles", type_="primary")
    op.create_primary_key("user_roles_pkey", "user_roles", ["user_id", "role_id"])


def downgrade() -> None:
    op.drop_constraint("user_roles_pkey", "user_roles", type_="primary")
    op.create_primary_key("user_roles_pkey", "user_roles", ["user_id"])
