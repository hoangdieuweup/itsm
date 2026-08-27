"""rename_cloudflare_audit_to_traffic

Revision ID: 657dbaf371cc
Revises: c5e1b8a47d92
Create Date: 2026-08-26 11:00:00.000000

The Cloudflare Audit Log feature (account-wide Cloudflare config-change
history, GET .../audit_logs) has been removed entirely - Cloudflare's audit
log endpoint has no way to filter by environment/project, so a shared zone
across multiple projects would show one project's config changes to every
other project on that same zone, with no way to narrow it down.

The `cloudflare_audit`/`project_cloudflare_audit` permission pair was reused,
unmodified, to gate the new Cloudflare Traffic Stats feature (GraphQL
Analytics - an aggregated request-volume view of the same environment-owned
hostname) since it sits at the same read-only, zone-scoped trust tier as the
audit log did. Leaving the permission literally named "audit" once the audit
feature itself is gone would be a misleading identifier for anyone reading
the RBAC catalog or the Roles admin UI, so this migration renames both rows
in place - a plain UPDATE, not delete+recreate - so every existing
role_permissions and project_role_permissions grant is preserved
automatically via the FK to permissions.id. Nothing to copy or move.
"""

import sqlalchemy as sa

from alembic import op

revision = "657dbaf371cc"
down_revision = "c5e1b8a47d92"
branch_labels = None
depends_on = None

_RENAMES: list[tuple[str, str, str]] = [
    ("cloudflare_audit", "cloudflare_traffic", "read"),
    ("project_cloudflare_audit", "project_cloudflare_traffic", "read"),
]

_RENAME_PERMISSION = sa.text(
    """
    UPDATE permissions
    SET resource = CAST(:new_resource AS VARCHAR(100)),
        description_key = CAST(:description_key AS VARCHAR(255))
    WHERE resource = CAST(:old_resource AS VARCHAR(100)) AND action = CAST(:action AS VARCHAR(50))
    """
)


def upgrade() -> None:
    bind = op.get_bind()
    for old_resource, new_resource, action in _RENAMES:
        bind.execute(
            _RENAME_PERMISSION,
            {
                "old_resource": old_resource,
                "new_resource": new_resource,
                "action": action,
                "description_key": f"permissions.{new_resource}.{action}",
            },
        )


def downgrade() -> None:
    bind = op.get_bind()
    for old_resource, new_resource, action in _RENAMES:
        bind.execute(
            _RENAME_PERMISSION,
            {
                "old_resource": new_resource,
                "new_resource": old_resource,
                "action": action,
                "description_key": f"permissions.{old_resource}.{action}",
            },
        )
