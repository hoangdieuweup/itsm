"""create_notification_channels_schema

Revision ID: 7e2d9a4c8b1f
Revises: 9b4d2e7f5c1a
Create Date: 2026-08-24 00:00:00.000000
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "7e2d9a4c8b1f"
down_revision = "9b4d2e7f5c1a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notification_channels",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("environment_id", sa.UUID(), nullable=True),
        sa.Column(
            "type",
            sa.Enum(
                "email", "base_vn", "telegram", "other", name="notificationchanneltype", native_enum=False
            ),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("notification_channels_project_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["environment_id"],
            ["environments.id"],
            name=op.f("notification_channels_environment_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("notification_channels_pkey")),
    )
    op.create_index(
        op.f("notification_channels_project_id_idx"), "notification_channels", ["project_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("notification_channels_project_id_idx"), table_name="notification_channels")
    op.drop_table("notification_channels")
