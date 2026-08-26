"""split_project_scoped_permission_resources

Revision ID: c5e1b8a47d92
Revises: a3f7d9c2e5b1
Create Date: 2026-08-26 09:00:00.000000

Eight resources were being checked under ONE resource string on two very
different authorization surfaces: the Cloudflare-account-manager surface
(a real cloudflare_account_managers grant) and the project-role surface
(membership in one project). Because ProjectScopedPermissionCatalog.
ASSIGNABLE listed those shared strings, a project role could grant
account-tier power - most severely cloudflare_tunnel.delete and
cloudflare_tunnel.reveal_token on a tunnel that is an ACCOUNT-wide object
commonly serving several unrelated projects at once.

This migration splits the catalog: each project-scoped surface gets its own
`project_`-prefixed resource, and the account-level names stay put. It then
moves existing grants so nobody silently loses a capability:

  * role_permissions (global roles): COPIED to the new name where the old
    name still guards a real account/global route (a global-permission
    holder passes today through resolve_effective_permissions' global-UNION
    half - the copy preserves that byte-for-byte), MOVED where the old row
    is being retired outright.
  * project_role_permissions: MOVED in every case - a project role holding
    an account-level string is precisely what the split forbids.
  * cloudflare_tunnel.delete / .reveal_token project-role grants: DELETED
    with no replacement. That is the security fix, and it is intentionally
    NOT reversible (see downgrade()).

Retired rows are deleted here rather than left to seed_rbac.py's
delete-if-not-in-CATALOG sweep, so the whole operation is atomic and the
seed has nothing left to strip.

ORDERING: run `alembic upgrade head` BEFORE `python -m app.seeds.seed_rbac`.
Running the seed first against the new CATALOG would delete the retired
rows (cascading role_permissions and project_role_permissions) before this
migration can move their grants. The companion guard added to seed_rbac.py
turns that into a loud refusal rather than silent loss, but the ordering is
still the supported path.
"""

import uuid

import sqlalchemy as sa

from alembic import op

revision = "c5e1b8a47d92"
down_revision = "a3f7d9c2e5b1"
branch_labels = None
depends_on = None


# (old_resource, new_resource, action): the new row is created and the OLD
# row SURVIVES, because some account-level or global route still checks it.
COPY_TO_NEW: list[tuple[str, str, str]] = [
    ("cloudflare_config", "project_cloudflare_config", "read"),
    ("cloudflare_dns", "project_cloudflare_dns", "read"),
    ("cloudflare_dns", "project_cloudflare_dns", "create"),
    ("cloudflare_dns", "project_cloudflare_dns", "update"),
    ("cloudflare_dns", "project_cloudflare_dns", "delete"),
    ("cloudflare_tunnel", "project_cloudflare_tunnel", "read"),
    ("cloudflare_tunnel", "project_cloudflare_tunnel", "create"),
    ("cloudflare_tunnel", "project_cloudflare_tunnel", "sync"),
    ("cloudflare_tunnel", "project_cloudflare_tunnel", "refresh_status"),
    ("cloudflare_hostname", "project_cloudflare_hostname", "read"),
    ("cloudflare_hostname", "project_cloudflare_hostname", "create"),
    ("cloudflare_hostname", "project_cloudflare_hostname", "update"),
    ("cloudflare_hostname", "project_cloudflare_hostname", "delete"),
    ("cloudflare_audit", "project_cloudflare_audit", "read"),
    ("alert_rule", "project_alert_rule", "read"),
    ("incident", "project_incident", "read"),
]

# (old_resource, new_resource, action): the new row is created and the OLD
# row is DELETED - no call site anywhere checks the old name any more.
MOVE_TO_NEW: list[tuple[str, str, str]] = [
    ("loki_config", "project_loki_config", "read"),
    ("loki_config", "project_loki_config", "manage"),
    ("alert_rule", "project_alert_rule", "create"),
    ("alert_rule", "project_alert_rule", "update"),
    ("alert_rule", "project_alert_rule", "delete"),
    ("incident", "project_incident", "create"),
    ("incident", "project_incident", "acknowledge"),
    ("incident", "project_incident", "resolve"),
]

# Atoms that stop being project-assignable with NO replacement.
REVOKED_FROM_PROJECT_ROLES: list[tuple[str, str]] = [
    ("cloudflare_tunnel", "delete"),
    ("cloudflare_tunnel", "reveal_token"),
]

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

_DELETE_PROJECT_ROLE_GRANTS = sa.text(
    """
    DELETE FROM project_role_permissions
    WHERE permission_id IN (
        SELECT id FROM permissions
        WHERE resource = CAST(:resource AS VARCHAR(100)) AND action = CAST(:action AS VARCHAR(50))
    )
    """
)

_DELETE_PERMISSION = sa.text(
    "DELETE FROM permissions WHERE resource = CAST(:resource AS VARCHAR(100)) AND action = CAST(:action AS VARCHAR(50))"
)


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Create every new project_-prefixed permission row.
    for _old_resource, new_resource, action in COPY_TO_NEW + MOVE_TO_NEW:
        bind.execute(
            _INSERT_PERMISSION,
            {
                "new_id": uuid.uuid4(),
                "resource": new_resource,
                "action": action,
                "description_key": f"permissions.{new_resource}.{action}",
            },
        )

    # 2. Propagate grants BEFORE anything is deleted.
    for old_resource, new_resource, action in COPY_TO_NEW + MOVE_TO_NEW:
        params = {"old_resource": old_resource, "new_resource": new_resource, "action": action}
        bind.execute(_COPY_ROLE_GRANTS, params)
        bind.execute(_COPY_PROJECT_ROLE_GRANTS, params)

    # 3. A project role must never hold an ACCOUNT-level resource string:
    #    drop the now-superseded project-role grants on the old names.
    for old_resource, _new_resource, action in COPY_TO_NEW + MOVE_TO_NEW:
        bind.execute(_DELETE_PROJECT_ROLE_GRANTS, {"resource": old_resource, "action": action})

    # 4. The security fix proper - these two have no project_ twin to move to.
    for resource, action in REVOKED_FROM_PROJECT_ROLES:
        bind.execute(_DELETE_PROJECT_ROLE_GRANTS, {"resource": resource, "action": action})

    # 5. Retire the old rows whose every call site became project-scoped.
    #    role_permissions rows cascade (FK ondelete=CASCADE) - that is what
    #    MOVE means, and step 2 already re-granted the new name.
    for old_resource, _new_resource, action in MOVE_TO_NEW:
        bind.execute(_DELETE_PERMISSION, {"resource": old_resource, "action": action})


def downgrade() -> None:
    """Restores the retired account-level rows and their grants.

    NOT restored: project_role_permissions grants on cloudflare_tunnel.delete
    and cloudflare_tunnel.reveal_token. Those were deleted as a security fix
    and the pre-fix state is deliberately unrecoverable. A downgraded
    database simply has those project roles without those two atoms -
    re-add them by hand only if you consciously want the escalation back.
    """
    bind = op.get_bind()

    # 1. Recreate the retired old rows.
    for old_resource, _new_resource, action in MOVE_TO_NEW:
        bind.execute(
            _INSERT_PERMISSION,
            {
                "new_id": uuid.uuid4(),
                "resource": old_resource,
                "action": action,
                "description_key": f"permissions.{old_resource}.{action}",
            },
        )

    # 2. Copy grants back, new -> old (arguments swapped).
    for old_resource, new_resource, action in COPY_TO_NEW + MOVE_TO_NEW:
        params = {"old_resource": new_resource, "new_resource": old_resource, "action": action}
        bind.execute(_COPY_ROLE_GRANTS, params)
        bind.execute(_COPY_PROJECT_ROLE_GRANTS, params)

    # 3. Drop every project_-prefixed row; its grants cascade.
    for _old_resource, new_resource, action in COPY_TO_NEW + MOVE_TO_NEW:
        bind.execute(_DELETE_PERMISSION, {"resource": new_resource, "action": action})
