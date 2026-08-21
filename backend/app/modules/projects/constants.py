"""Constants and enums owned by the projects module."""

from enum import StrEnum


class ProjectLimits:
    """Numeric limits owned by the projects module."""

    MAX_NAME_LENGTH = 255
    MAX_LINK_NAME_LENGTH = 255
    MAX_ENVIRONMENT_NAME_LENGTH = 100
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
