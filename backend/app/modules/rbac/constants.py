"""Constants and enums owned by the rbac module."""

from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Any
from uuid import UUID


class RbacPermissionCatalog:
    """The fixed (resource, action, description_key) catalog — seeded from
    code, never admin-created. See rbac/seeds and references/rbac.md's
    anti-pattern list: permissions are what the application *can* do, not
    free text.

    description_key is an i18n key (e.g. "permissions.role.create"), not
    display text — the frontend owns the actual translated string under its
    own "rbac" message namespace, the same way error codes are keys the
    frontend maps to copy, never raw text from the backend. See
    Permission's docstring in models.py.

    Permissions are grouped by functional API area, not by generic CRUD.
    Each sub-resource (tunnel, DNS, hostname, …) has its own permission
    set so roles can be scoped to specific operational areas.
    """

    CATALOG: list[tuple[str, str, str]] = [
        # ── System administration ───────────────────────────────────
        ("role", "create", "permissions.role.create"),
        ("role", "read", "permissions.role.read"),
        ("role", "update", "permissions.role.update"),
        ("role", "delete", "permissions.role.delete"),
        ("permission", "read", "permissions.permission.read"),
        ("user", "read", "permissions.user.read"),
        ("user", "update_status", "permissions.user.update_status"),
        ("user", "assign_role", "permissions.user.assign_role"),
        ("audit_log", "read", "permissions.audit_log.read"),
        # ── Projects ───────────────────────────────────────────────
        ("project", "create", "permissions.project.create"),
        ("project", "read", "permissions.project.read"),
        ("project", "update", "permissions.project.update"),
        ("project", "delete", "permissions.project.delete"),
        ("project", "manage_all", "permissions.project.manage_all"),
        ("project_member", "read", "permissions.project_member.read"),
        ("project_member", "manage", "permissions.project_member.manage"),
        ("project_link", "read", "permissions.project_link.read"),
        ("project_link", "manage", "permissions.project_link.manage"),
        ("project_role", "read", "permissions.project_role.read"),
        ("project_role", "manage", "permissions.project_role.manage"),
        # ── Environments ───────────────────────────────────────────
        ("environment", "create", "permissions.environment.create"),
        ("environment", "read", "permissions.environment.read"),
        ("environment", "update", "permissions.environment.update"),
        ("environment", "delete", "permissions.environment.delete"),
        # ── Cloudflare accounts ────────────────────────────────────
        ("cloudflare_account", "create", "permissions.cloudflare_account.create"),
        ("cloudflare_account", "read", "permissions.cloudflare_account.read"),
        ("cloudflare_account", "update", "permissions.cloudflare_account.update"),
        ("cloudflare_account", "delete", "permissions.cloudflare_account.delete"),
        ("cloudflare_account", "test_connection", "permissions.cloudflare_account.test_connection"),
        ("cloudflare_account", "reveal_token", "permissions.cloudflare_account.reveal_token"),
        ("cloudflare_account", "manage_all", "permissions.cloudflare_account.manage_all"),
        # ── Cloudflare account managers ────────────────────────────
        ("cloudflare_manager", "read", "permissions.cloudflare_manager.read"),
        ("cloudflare_manager", "manage", "permissions.cloudflare_manager.manage"),
        # ── Cloudflare config (zone binding) ───────────────────────
        ("cloudflare_config", "read", "permissions.cloudflare_config.read"),
        ("cloudflare_config", "manage", "permissions.cloudflare_config.manage"),
        # ── Cloudflare tunnels ─────────────────────────────────────
        ("cloudflare_tunnel", "read", "permissions.cloudflare_tunnel.read"),
        ("cloudflare_tunnel", "create", "permissions.cloudflare_tunnel.create"),
        ("cloudflare_tunnel", "delete", "permissions.cloudflare_tunnel.delete"),
        ("cloudflare_tunnel", "sync", "permissions.cloudflare_tunnel.sync"),
        ("cloudflare_tunnel", "reveal_token", "permissions.cloudflare_tunnel.reveal_token"),
        ("cloudflare_tunnel", "refresh_status", "permissions.cloudflare_tunnel.refresh_status"),
        # ── Cloudflare public hostnames ────────────────────────────
        ("cloudflare_hostname", "read", "permissions.cloudflare_hostname.read"),
        ("cloudflare_hostname", "create", "permissions.cloudflare_hostname.create"),
        ("cloudflare_hostname", "update", "permissions.cloudflare_hostname.update"),
        ("cloudflare_hostname", "delete", "permissions.cloudflare_hostname.delete"),
        # ── Cloudflare DNS records ─────────────────────────────────
        ("cloudflare_dns", "read", "permissions.cloudflare_dns.read"),
        ("cloudflare_dns", "create", "permissions.cloudflare_dns.create"),
        ("cloudflare_dns", "update", "permissions.cloudflare_dns.update"),
        ("cloudflare_dns", "delete", "permissions.cloudflare_dns.delete"),
        # ── Cloudflare traffic stats (GraphQL Analytics, ACCOUNT-level;
        # kept for symmetry — the account-level route this would gate
        # doesn't exist yet, project_cloudflare_traffic is what's used) ──
        ("cloudflare_traffic", "read", "permissions.cloudflare_traffic.read"),
        # ── Notification channels ──────────────────────────────────
        ("notification_channel", "create", "permissions.notification_channel.create"),
        ("notification_channel", "read", "permissions.notification_channel.read"),
        ("notification_channel", "update", "permissions.notification_channel.update"),
        ("notification_channel", "delete", "permissions.notification_channel.delete"),
        ("notification_channel", "test_send", "permissions.notification_channel.test_send"),
        # ── Alert rules (ACCOUNT-level: available-alerts route only) ──
        ("alert_rule", "read", "permissions.alert_rule.read"),
        # ── Incidents (GLOBAL: cross-project list route only) ───────
        ("incident", "read", "permissions.incident.read"),
        # ── PROJECT-SCOPED twins ───────────────────────────────────
        ("project_cloudflare_config", "read", "permissions.project_cloudflare_config.read"),
        ("project_cloudflare_dns", "read", "permissions.project_cloudflare_dns.read"),
        ("project_cloudflare_dns", "create", "permissions.project_cloudflare_dns.create"),
        ("project_cloudflare_dns", "update", "permissions.project_cloudflare_dns.update"),
        ("project_cloudflare_dns", "delete", "permissions.project_cloudflare_dns.delete"),
        ("project_cloudflare_tunnel", "read", "permissions.project_cloudflare_tunnel.read"),
        ("project_cloudflare_tunnel", "create", "permissions.project_cloudflare_tunnel.create"),
        ("project_cloudflare_tunnel", "sync", "permissions.project_cloudflare_tunnel.sync"),
        (
            "project_cloudflare_tunnel",
            "refresh_status",
            "permissions.project_cloudflare_tunnel.refresh_status",
        ),
        ("project_cloudflare_hostname", "read", "permissions.project_cloudflare_hostname.read"),
        ("project_cloudflare_hostname", "create", "permissions.project_cloudflare_hostname.create"),
        ("project_cloudflare_hostname", "update", "permissions.project_cloudflare_hostname.update"),
        ("project_cloudflare_hostname", "delete", "permissions.project_cloudflare_hostname.delete"),
        ("project_cloudflare_traffic", "read", "permissions.project_cloudflare_traffic.read"),
        ("project_loki_config", "read", "permissions.project_loki_config.read"),
        ("project_loki_config", "manage", "permissions.project_loki_config.manage"),
        ("project_alert_rule", "create", "permissions.project_alert_rule.create"),
        ("project_alert_rule", "read", "permissions.project_alert_rule.read"),
        ("project_alert_rule", "update", "permissions.project_alert_rule.update"),
        ("project_alert_rule", "delete", "permissions.project_alert_rule.delete"),
        ("project_incident", "create", "permissions.project_incident.create"),
        ("project_incident", "read", "permissions.project_incident.read"),
        ("project_incident", "acknowledge", "permissions.project_incident.acknowledge"),
        ("project_incident", "resolve", "permissions.project_incident.resolve"),
    ]


class RbacResources:
    """Every resource string CATALOG defines. Routers pass these to
    require_permission/require_any_permission instead of a raw string
    literal, so a typo fails at import time (AttributeError) instead of
    silently creating an unsatisfiable permission requirement. Mirrors the
    frontend's shared/constants/permissions.ts RESOURCES object 1:1."""

    ROLE = "role"
    PERMISSION = "permission"
    USER = "user"
    PROJECT = "project"
    PROJECT_MEMBER = "project_member"
    PROJECT_LINK = "project_link"
    PROJECT_ROLE = "project_role"
    ENVIRONMENT = "environment"
    AUDIT_LOG = "audit_log"
    CLOUDFLARE_ACCOUNT = "cloudflare_account"
    CLOUDFLARE_MANAGER = "cloudflare_manager"
    CLOUDFLARE_CONFIG = "cloudflare_config"
    CLOUDFLARE_TUNNEL = "cloudflare_tunnel"
    CLOUDFLARE_HOSTNAME = "cloudflare_hostname"
    CLOUDFLARE_DNS = "cloudflare_dns"
    CLOUDFLARE_TRAFFIC = "cloudflare_traffic"
    NOTIFICATION_CHANNEL = "notification_channel"
    ALERT_RULE = "alert_rule"
    INCIDENT = "incident"
    # Project-scoped twins — see ProjectScopedPermissionCatalog.ASSIGNABLE.
    PROJECT_CLOUDFLARE_CONFIG = "project_cloudflare_config"
    PROJECT_CLOUDFLARE_TUNNEL = "project_cloudflare_tunnel"
    PROJECT_CLOUDFLARE_HOSTNAME = "project_cloudflare_hostname"
    PROJECT_CLOUDFLARE_DNS = "project_cloudflare_dns"
    PROJECT_CLOUDFLARE_TRAFFIC = "project_cloudflare_traffic"
    PROJECT_LOKI_CONFIG = "project_loki_config"
    PROJECT_ALERT_RULE = "project_alert_rule"
    PROJECT_INCIDENT = "project_incident"


class RbacActions:
    """Every action string CATALOG defines. See RbacResources' docstring —
    mirrors the frontend's ACTIONS object 1:1."""

    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    UPDATE_STATUS = "update_status"
    ASSIGN_ROLE = "assign_role"
    MANAGE = "manage"
    MANAGE_ALL = "manage_all"
    SYNC = "sync"
    REVEAL_TOKEN = "reveal_token"
    REFRESH_STATUS = "refresh_status"
    TEST_CONNECTION = "test_connection"
    TEST_SEND = "test_send"
    ACKNOWLEDGE = "acknowledge"
    RESOLVE = "resolve"


class RbacDefaults:
    """Seeded role names. See seeds/seed_rbac.py.

    No OWNER_ROLE_NAME: this system has no "owner" role — admin is the
    highest seeded role, and the bus-factor protection (RbacRules.
    blocks_last_admin_removal) guards admin, not a role nothing creates.
    """

    ADMIN_ROLE_NAME = "admin"
    MEMBER_ROLE_NAME = "member"
    SYSTEM_ROLE_NAMES = (ADMIN_ROLE_NAME, MEMBER_ROLE_NAME)
    DEFAULT_ROLE_NAME = MEMBER_ROLE_NAME


class RbacCacheKeys:
    """Cache identity owned by the rbac module. See references/caching.md."""

    ROLE_ENTITY = "role"
    USER_ROLE_ENTITY = "user_role"
    TTL_SECONDS = 300


class RbacLimits:
    """Numeric limits owned by the rbac module."""

    MAX_ROLE_NAME_LENGTH = 100


class RbacTypes:
    """Type aliases owned by the rbac module."""

    UserLookup = Callable[[UUID], Awaitable[Any | None]]
    ProtectionCheck = Callable[[UUID], Awaitable[bool]]


class ErrorCode(StrEnum):
    """Stable error codes returned to clients by this module."""

    ROLE_NOT_FOUND = "rbac_role_not_found"
    DUPLICATE_ROLE_NAME = "rbac_duplicate_role_name"
    SYSTEM_ROLE_IMMUTABLE = "rbac_system_role_immutable"
    ROLE_IN_USE = "rbac_role_in_use"
    CANNOT_REMOVE_LAST_ADMIN = "rbac_cannot_remove_last_admin"
    CANNOT_MODIFY_PROTECTED_ADMIN = "rbac_cannot_modify_protected_admin"
    TARGET_USER_NOT_FOUND = "rbac_target_user_not_found"
    PERMISSION_DENIED = "rbac_permission_denied"
    UNKNOWN_PERMISSION_ID = "rbac_unknown_permission_id"
