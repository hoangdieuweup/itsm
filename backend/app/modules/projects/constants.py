"""Constants and enums owned by the projects module."""

from enum import StrEnum


class ProjectLimits:
    """Numeric limits owned by the projects module."""

    MAX_NAME_LENGTH = 255
    MAX_LINK_NAME_LENGTH = 255
    MAX_ENVIRONMENT_NAME_LENGTH = 100
    MAX_PROJECT_ROLE_NAME_LENGTH = 100
    DEFAULT_PAGE_SIZE = 50


class EnvironmentType(StrEnum):
    """The three deployment tiers a project can have — at most one of each,
    enforced by UNIQUE(project_id, type)."""

    DEV = "dev"
    STAGING = "staging"
    PRODUCTION = "production"


class ProjectLinkType(StrEnum):
    """External link kinds a project can carry."""

    JIRA = "jira"
    GIT = "git"
    OTHER = "other"


class ProjectsEvents:
    """Messaging identity owned by the projects module. See references/messaging.md."""

    EXCHANGE = "projects"


class ProjectsCacheKeys:
    """Cache identity owned by the projects module. See references/caching.md."""

    PROJECT_ENTITY = "project"
    ENVIRONMENT_ENTITY = "environment"
    TTL_SECONDS = 300


class ErrorCode(StrEnum):
    """Stable error codes returned to clients by this module."""

    PROJECT_NOT_FOUND = "projects_project_not_found"
    ENVIRONMENT_NOT_FOUND = "projects_environment_not_found"
    ENVIRONMENT_TYPE_ALREADY_EXISTS = "projects_environment_type_already_exists"
    PROJECT_LINK_NOT_FOUND = "projects_project_link_not_found"
    INSUFFICIENT_PROJECT_ACCESS = "projects_insufficient_project_access"
    PROJECT_MEMBER_ALREADY_EXISTS = "projects_project_member_already_exists"
    PROJECT_ROLE_NOT_FOUND = "projects_project_role_not_found"
    DUPLICATE_PROJECT_ROLE_NAME = "projects_duplicate_project_role_name"
    PERMISSION_NOT_PROJECT_ASSIGNABLE = "projects_permission_not_project_assignable"
    PROJECT_PERMISSION_DENIED = "projects_project_permission_denied"


class ProjectAuditActions(StrEnum):
    """Action identifiers this module writes via audit.log_event. Centralized
    so the same string is never typo'd or drifted across call sites — audit
    itself is domain-agnostic and only ever sees whatever string is passed."""

    PROJECT_CREATED = "PROJECT_CREATED"
    PROJECT_UPDATED = "PROJECT_UPDATED"
    PROJECT_DELETED = "PROJECT_DELETED"
    ENVIRONMENT_CREATED = "ENVIRONMENT_CREATED"
    ENVIRONMENT_UPDATED = "ENVIRONMENT_UPDATED"
    ENVIRONMENT_DELETED = "ENVIRONMENT_DELETED"
    MEMBER_ADDED = "MEMBER_ADDED"
    MEMBER_REMOVED = "MEMBER_REMOVED"
    PROJECT_ROLE_CREATED = "PROJECT_ROLE_CREATED"
    PROJECT_ROLE_UPDATED = "PROJECT_ROLE_UPDATED"
    PROJECT_ROLE_DELETED = "PROJECT_ROLE_DELETED"
    MEMBER_ROLE_ASSIGNED = "MEMBER_ROLE_ASSIGNED"


class ProjectScopedPermissionCatalog:
    """The subset of the global rbac.Permission catalog a ProjectRole may
    ever grant.

    Every Cloudflare/Loki/Alerting/Incident entry below is a `project_`-
    prefixed resource whose ONLY check site is a project-scoped dependency.
    The account-level namesakes (cloudflare_tunnel.*, cloudflare_dns.*,
    loki_config.*, alert_rule.*, incident.*) are deliberately absent: they
    are what the account-manager path of require_cloudflare_environment_access
    checks, and letting a project role grant one of those strings is exactly
    the cross-tenant escalation this split closes. Before the split, a
    Project-A-only member with a role granting cloudflare_tunnel.delete could
    delete a tunnel actively serving Projects B/C/D, because a Cloudflare
    Tunnel is an ACCOUNT-wide object (CloudflareTunnel has no environment_id
    column at all — see cloudflare/models.py).

    Permanently excluded, in every namespace: project.delete (cascades every
    downstream Cloudflare/Loki/alerting row), project.manage_all,
    project_member.manage, both project_role.* atoms, all Cloudflare ACCOUNT
    administration (cloudflare_account.*, cloudflare_manager.*),
    cloudflare_config.manage (binding an environment to an account is a
    trust-establishing action — a project role may only OPERATE inside a
    binding someone with real account access already established), and —
    added by this split — cloudflare_tunnel.delete and
    cloudflare_tunnel.reveal_token, which have no project_ twin at all.

    See docs/superpowers/plans/2026-08-26-project-scoped-resource-split-and-
    tunnel-hostname-ownership-fix.md."""

    ASSIGNABLE: frozenset[tuple[str, str]] = frozenset(
        {
            ("project", "read"),
            ("project", "update"),
            ("environment", "create"),
            ("environment", "read"),
            ("environment", "update"),
            ("environment", "delete"),
            ("project_link", "read"),
            ("project_link", "manage"),
            ("project_member", "read"),
            ("project_cloudflare_config", "read"),
            ("project_cloudflare_dns", "read"),
            ("project_cloudflare_dns", "create"),
            ("project_cloudflare_dns", "update"),
            ("project_cloudflare_dns", "delete"),
            ("project_cloudflare_tunnel", "read"),
            ("project_cloudflare_tunnel", "create"),
            ("project_cloudflare_tunnel", "sync"),
            ("project_cloudflare_tunnel", "refresh_status"),
            ("project_cloudflare_hostname", "read"),
            ("project_cloudflare_hostname", "create"),
            ("project_cloudflare_hostname", "update"),
            ("project_cloudflare_hostname", "delete"),
            ("project_cloudflare_traffic", "read"),
            ("project_loki_config", "read"),
            ("project_loki_config", "manage"),
            ("project_alert_rule", "create"),
            ("project_alert_rule", "read"),
            ("project_alert_rule", "update"),
            ("project_alert_rule", "delete"),
            ("project_incident", "create"),
            ("project_incident", "read"),
            ("project_incident", "acknowledge"),
            ("project_incident", "resolve"),
        }
    )
