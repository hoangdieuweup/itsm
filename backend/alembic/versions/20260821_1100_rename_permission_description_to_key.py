"""rename permissions.description to description_key

Revision ID: c4e8a1f92d36
Revises: 9a1f3c6de072
Create Date: 2026-08-21 11:00:00.000000
"""

from alembic import op

revision = "c4e8a1f92d36"
down_revision = "9a1f3c6de072"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("permissions", "description", new_column_name="description_key")


def downgrade() -> None:
    op.alter_column("permissions", "description_key", new_column_name="description")
