"""scope_notification_channel_alert_rule_and_traffic

Revision ID: a1d4f7b28e63
Revises: 657dbaf371cc
Create Date: 2026-08-27 16:20:00.000000

A notification channel belongs to exactly one project, and an alert rule to
exactly one environment. Neither had that reflected in RBAC.

notification_channel.* was a GLOBAL resource string checked through
ProjectsApi.resolve_effective_permissions, whose semantics are
`global_keys | project_keys` (see ProjectRoleRules.effective_permissions -
a union, never a narrowing). A global role holding notification_channel.create
therefore held it on EVERY project, including projects the holder is not a
member of - the project scope was decorative. Every other project-scoped
surface in this codebase already uses a `project_`-prefixed twin; this one did
not. It is the last resource still checked under a bare global name on a
project-scoped route.

alert_rule.read was a second, redundant gate on
GET /cloudflare-accounts/{id}/available-alerts. That route already requires a
real cloudflare_account_managers grant via require_account_access, and FastAPI
runs both dependencies (an AND), so the global permission never widened access
- it only made the catalog claim an account-level alert_rule concept that no
other route uses. Alert rule CRUD is, and stays, project_alert_rule.

Grant movement:

  * project_role_permissions on notification_channel.*: MOVED to
    project_notification_channel.*. A project role keeps exactly the
    capability it had.
  * role_permissions (global roles) on notification_channel.*: DELETED, not
    copied. Copying is what would preserve the escalation this migration
    exists to remove. The seeded admin role is affected: after this migration
    an admin manages notification channels through a project role like anyone
    else. Re-grant globally only if you consciously want the old behavior.
  * alert_rule.read: row deleted outright; role_permissions cascade.
  * cloudflare_traffic.read and project_cloudflare_traffic.read: both
    collapse into environment_cloudflare_traffic.read. The traffic route
    is environment-keyed and now checks only the project-role path, so
    the account-manager resource has no call site left.

Downgrade restores both rows and re-grants them to whichever roles held the
project-scoped equivalents, which is the closest recoverable approximation -
the exact pre-migration global grant list is not reconstructible.
"""

import uuid

import sqlalchemy as sa

from alembic import op

revision: str = "a1d4f7b28e63"
down_revision: str | None = "657dbaf371cc"
branch_labels: str | None = None
depends_on: str | None = None


# (old_resource, new_resource, action) - project-role grants move, global ones do not.
MOVED_TO_PROJECT_SCOPE = [
    ("notification_channel", "project_notification_channel", action)
    for action in ("create", "read", "update", "delete", "test_send")
] + [
    # Traffic stats only ever gated ONE route, and that route is
    # environment-keyed. Both old names collapse into a single scoped
    # resource: the account-manager branch is dropped from the route, so the
    # global name has no call site left.
    ("cloudflare_traffic", "environment_cloudflare_traffic", "read"),
    ("project_cloudflare_traffic", "environment_cloudflare_traffic", "read"),
]

# Retired outright: no twin, no replacement route.
RETIRED = [("alert_rule", "read")]


_INSERT_PERMISSION = sa.text(
    """
    INSERT INTO permissions (id, resource, action, description_key)
    SELECT :new_id, CAST(:resource AS VARCHAR(100)), CAST(:action AS VARCHAR(50)), CAST(:description_key AS VARCHAR(255))
    WHERE NOT EXISTS (
        SELECT 1 FROM permissions
        WHERE resource = CAST(:resource AS VARCHAR(100)) AND action = CAST(:action AS VARCHAR(50))
    )
    """
)

_COPY_PROJECT_ROLE_GRANTS = sa.text(
    """
    INSERT INTO project_role_permissions (project_role_id, permission_id)
    SELECT prp.project_role_id, new_p.id
    FROM project_role_permissions prp
    JOIN permissions old_p ON old_p.id = prp.permission_id
    JOIN permissions new_p
        ON new_p.resource = CAST(:new_resource AS VARCHAR(100))
        AND new_p.action = CAST(:action AS VARCHAR(50))
    WHERE old_p.resource = CAST(:old_resource AS VARCHAR(100)) AND old_p.action = CAST(:action AS VARCHAR(50))
    ON CONFLICT DO NOTHING
    """
)

_COPY_ROLE_GRANTS = sa.text(
    """
    INSERT INTO role_permissions (role_id, permission_id)
    SELECT rp.role_id, new_p.id
    FROM role_permissions rp
    JOIN permissions old_p ON old_p.id = rp.permission_id
    JOIN permissions new_p
        ON new_p.resource = CAST(:new_resource AS VARCHAR(100))
        AND new_p.action = CAST(:action AS VARCHAR(50))
    WHERE old_p.resource = CAST(:old_resource AS VARCHAR(100)) AND old_p.action = CAST(:action AS VARCHAR(50))
    ON CONFLICT DO NOTHING
    """
)

_DELETE_PERMISSION = sa.text(
    "DELETE FROM permissions WHERE resource = CAST(:resource AS VARCHAR(100)) AND action = CAST(:action AS VARCHAR(50))"
)


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Create the project_-prefixed rows.
    for _old_resource, new_resource, action in MOVED_TO_PROJECT_SCOPE:
        bind.execute(
            _INSERT_PERMISSION,
            {
                "new_id": uuid.uuid4(),
                "resource": new_resource,
                "action": action,
                "description_key": f"permissions.{new_resource}.{action}",
            },
        )

    # 2. Move project-role grants onto the new name BEFORE deleting anything.
    #    Global role_permissions are deliberately NOT copied - that grant is
    #    the escalation being removed.
    for old_resource, new_resource, action in MOVED_TO_PROJECT_SCOPE:
        bind.execute(
            _COPY_PROJECT_ROLE_GRANTS,
            {"old_resource": old_resource, "new_resource": new_resource, "action": action},
        )

    # 3. Retire the old rows. role_permissions and project_role_permissions
    #    rows cascade (FK ondelete=CASCADE); step 2 already re-granted the
    #    project side under the new name.
    for old_resource, _new_resource, action in MOVED_TO_PROJECT_SCOPE:
        bind.execute(_DELETE_PERMISSION, {"resource": old_resource, "action": action})

    for resource, action in RETIRED:
        bind.execute(_DELETE_PERMISSION, {"resource": resource, "action": action})


def downgrade() -> None:
    """Restores notification_channel.* and alert_rule.read.

    NOT restored: the global role_permissions grants on notification_channel.*
    that upgrade() deleted. Those were removed as a security fix and the
    pre-fix grant list is deliberately unrecoverable. What downgrade does
    restore is the project-role side, remapped back onto the old resource
    name, so a downgraded database keeps every project role working.
    """
    bind = op.get_bind()

    for old_resource, _new_resource, action in MOVED_TO_PROJECT_SCOPE:
        bind.execute(
            _INSERT_PERMISSION,
            {
                "new_id": uuid.uuid4(),
                "resource": old_resource,
                "action": action,
                "description_key": f"permissions.{old_resource}.{action}",
            },
        )

    for resource, action in RETIRED:
        bind.execute(
            _INSERT_PERMISSION,
            {
                "new_id": uuid.uuid4(),
                "resource": resource,
                "action": action,
                "description_key": f"permissions.{resource}.{action}",
            },
        )

    # Remap project-role grants back onto the old name, then drop the twin.
    for old_resource, new_resource, action in MOVED_TO_PROJECT_SCOPE:
        bind.execute(
            _COPY_PROJECT_ROLE_GRANTS,
            {"old_resource": new_resource, "new_resource": old_resource, "action": action},
        )
        bind.execute(
            _COPY_ROLE_GRANTS,
            {"old_resource": new_resource, "new_resource": old_resource, "action": action},
        )
        bind.execute(_DELETE_PERMISSION, {"resource": new_resource, "action": action})
