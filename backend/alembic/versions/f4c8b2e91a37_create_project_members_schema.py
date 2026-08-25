"""create_project_members_schema

Revision ID: f4c8b2e91a37
Revises: 8a79eab65342
Create Date: 2026-08-25 10:00:00.000000

Adds binary project membership: a user must have a row in
`project_members` (or hold the new `project:manage_all` bypass
permission) to see or act on a project and its environments/links.
Previously `project:read` was a single global RBAC permission with no
per-project scoping — anyone whose role held it could see every project
in the system, by original design (see
docs/tasks/devops-control-panel-schema.md §8, which only ever designed a
2-layer ACL for cloudflare_accounts, never projects). This migration is
purely additive — no existing column changes, no backfill needed since
project creation now auto-adds the creator as the first member going
forward; existing projects simply have no members until an admin
(project:manage_all) or existing member adds one.
"""

import sqlalchemy as sa

from alembic import op

revision = "f4c8b2e91a37"
down_revision = "8a79eab65342"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_members",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("project_members_project_id_fkey"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("project_members_user_id_fkey"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("project_id", "user_id", name=op.f("project_members_pkey")),
    )
    op.create_index(op.f("project_members_user_id_idx"), "project_members", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("project_members_user_id_idx"), table_name="project_members")
    op.drop_table("project_members")
