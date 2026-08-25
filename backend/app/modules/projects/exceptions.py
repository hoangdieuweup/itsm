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


class ProjectRoleNotFound(NotFoundError):
    """Raised when no project role matches the requested id."""

    code = ErrorCode.PROJECT_ROLE_NOT_FOUND
    message = "Project role not found"


class DuplicateProjectRoleName(ConflictError):
    """Raised when a project already has a role with the requested name."""

    code = ErrorCode.DUPLICATE_PROJECT_ROLE_NAME
    message = "This project already has a role with that name"


class PermissionNotProjectAssignable(ConflictError):
    """Raised when a project role's requested permissions include one
    outside ProjectScopedPermissionCatalog.ASSIGNABLE."""

    code = ErrorCode.PERMISSION_NOT_PROJECT_ASSIGNABLE
    message = "One or more permissions cannot be assigned to a project role"


class ProjectPermissionDenied(ForbiddenError):
    """Raised when the caller's effective project permission set (global
    UNION project role) does not include the required resource.action.
    Projects-owned rather than reusing rbac's PermissionDenied — that
    class isn't exported through rbac/public.py, and cross-module error
    reuse would break the module-owns-its-errors rule."""

    code = ErrorCode.PROJECT_PERMISSION_DENIED
    message = "You do not have this permission on this project"
