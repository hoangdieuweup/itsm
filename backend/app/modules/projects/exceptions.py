"""Errors owned by the projects module."""

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.modules.projects.constants import ErrorCode


class ProjectNotFound(NotFoundError):
    """Raised when no project matches the requested id."""

    code = ErrorCode.PROJECT_NOT_FOUND
    message = "Project not found"


class EnvironmentNotFound(NotFoundError):
    """Raised when no environment matches the requested id."""

    code = ErrorCode.ENVIRONMENT_NOT_FOUND
    message = "Environment not found"


class EnvironmentTypeAlreadyExists(ConflictError):
    """Raised when a project already has an environment of the requested type."""

    code = ErrorCode.ENVIRONMENT_TYPE_ALREADY_EXISTS
    message = "This project already has an environment of that type"


class ProjectLinkNotFound(NotFoundError):
    """Raised when no project link matches the requested id."""

    code = ErrorCode.PROJECT_LINK_NOT_FOUND
    message = "Project link not found"


class InsufficientProjectAccess(ForbiddenError):
    """Raised when the caller is neither a member of the project nor holds
    project:manage_all."""

    code = ErrorCode.INSUFFICIENT_PROJECT_ACCESS
    message = "You are not a member of this project"


class ProjectMemberAlreadyExists(ConflictError):
    """Raised when the target user is already a member of the project."""

    code = ErrorCode.PROJECT_MEMBER_ALREADY_EXISTS
    message = "This user is already a member of the project"
