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


class ProjectScopedPermissionCatalog:
    """The subset of the global rbac.Permission catalog a ProjectRole may
    ever grant. Bounded deliberately: project.delete (cascades every
    downstream Cloudflare/Loki/alerting row), project.manage_all,
    project_member.manage, and both project_role.* atoms are permanently
    excluded — managing roles/members and deleting a project always
    require a GLOBAL atom, never a project-scoped one, closing the
    mint-yourself-more-power loop a naive union would open."""

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
        }
    )
