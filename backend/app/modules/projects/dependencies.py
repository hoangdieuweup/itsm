"""Dependency wiring for the projects module. The composition root: the only
place that names a concrete class (ProjectsUnitOfWork) instead of its
Abstract* contract."""

from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.integrations.cache.client import CacheClient
from app.integrations.cache.dependencies import get_cache
from app.modules.audit.public import AuditApi, get_audit_api
from app.modules.auth.public import AuthApi, get_auth_api
from app.modules.projects.access import resolve_project_membership, resolve_project_permissions
from app.modules.projects.exceptions import (
    EnvironmentNotFound,
    ProjectLinkNotFound,
    ProjectPermissionDenied,
    ProjectRoleNotFound,
)
from app.modules.projects.schemas import ProjectPermissionGrant
from app.modules.projects.services.environments.create_environment import CreateEnvironment
from app.modules.projects.services.environments.delete_environment import DeleteEnvironment
from app.modules.projects.services.environments.update_environment import UpdateEnvironment
from app.modules.projects.services.links.create_project_link import CreateProjectLink
from app.modules.projects.services.links.delete_project_link import DeleteProjectLink
from app.modules.projects.services.links.update_project_link import UpdateProjectLink
from app.modules.projects.services.members.add_project_member import AddProjectMember
from app.modules.projects.services.members.assign_member_project_role import AssignMemberProjectRole
from app.modules.projects.services.members.list_project_members import ListProjectMembers
from app.modules.projects.services.members.remove_project_member import RemoveProjectMember
from app.modules.projects.services.projects.create_project import CreateProject
from app.modules.projects.services.projects.delete_project import DeleteProject
from app.modules.projects.services.projects.list_visible_projects import ListVisibleProjects
from app.modules.projects.services.projects.update_project import UpdateProject
from app.modules.projects.services.roles.create_project_role import CreateProjectRole
from app.modules.projects.services.roles.delete_project_role import DeleteProjectRole
from app.modules.projects.services.roles.list_assignable_permissions import ListAssignablePermissions
from app.modules.projects.services.roles.list_project_roles import ListProjectRoles
from app.modules.projects.services.roles.update_project_role import UpdateProjectRole
from app.modules.projects.uow import AbstractProjectsUnitOfWork, ProjectsUnitOfWork
from app.modules.rbac.public import RbacApi, get_rbac_api
from app.modules.users.public import UsersApi, get_users_api


async def get_uow(
    session: AsyncSession = Depends(get_session), cache: CacheClient = Depends(get_cache)
) -> ProjectsUnitOfWork:
    """Provide a request scoped unit of work. The one place the concrete class is named."""
    return ProjectsUnitOfWork(session, cache)


def require_project_membership():
    """Return a dependency that 403s unless the current user is a member of
    project_id (read from the path) or holds project:manage_all."""

    async def check(
        project_id: UUID,
        auth_api: AuthApi = Depends(get_auth_api),
        rbac_api: RbacApi = Depends(get_rbac_api),
        uow: AbstractProjectsUnitOfWork = Depends(get_uow),
    ) -> None:
        user = auth_api.current_user()
        await resolve_project_membership(project_id, user, rbac_api, uow)

    return check


def require_project_membership_for_environment():
    """Same check as require_project_membership, but keyed by environment_id
    (read from the path) — resolves the environment's project_id first."""

    async def check(
        environment_id: UUID,
        auth_api: AuthApi = Depends(get_auth_api),
        rbac_api: RbacApi = Depends(get_rbac_api),
        uow: AbstractProjectsUnitOfWork = Depends(get_uow),
    ) -> None:
        user = auth_api.current_user()
        environment = await uow.environments.get_by_id(environment_id)
        if environment is None:
            raise EnvironmentNotFound()
        await resolve_project_membership(environment.project_id, user, rbac_api, uow)

    return check


def require_project_membership_for_link():
    """Same check as require_project_membership, but keyed by link_id (read
    from the path) — resolves the link's project_id first."""

    async def check(
        link_id: UUID,
        auth_api: AuthApi = Depends(get_auth_api),
        rbac_api: RbacApi = Depends(get_rbac_api),
        uow: AbstractProjectsUnitOfWork = Depends(get_uow),
    ) -> None:
        user = auth_api.current_user()
        link = await uow.project_links.get_by_id(link_id)
        if link is None:
            raise ProjectLinkNotFound()
        await resolve_project_membership(link.project_id, user, rbac_api, uow)

    return check


def require_project_permission(resource: str, action: str):
    """Return a dependency that 403s unless the caller's effective
    permission set in project_id (global UNION project role) includes
    resource.action. Replaces the old require_permission(...) +
    require_project_membership() pairing — two sequential gates cannot
    express union."""

    async def check(
        project_id: UUID,
        auth_api: AuthApi = Depends(get_auth_api),
        rbac_api: RbacApi = Depends(get_rbac_api),
        uow: AbstractProjectsUnitOfWork = Depends(get_uow),
    ) -> ProjectPermissionGrant:
        user = auth_api.current_user()
        grant = await resolve_project_permissions(project_id, user, rbac_api, uow)
        if f"{resource}.{action}" not in grant.permissions:
            raise ProjectPermissionDenied()
        return grant

    return check


def require_project_permission_for_environment(resource: str, action: str):
    """Same as require_project_permission, keyed by environment_id."""

    async def check(
        environment_id: UUID,
        auth_api: AuthApi = Depends(get_auth_api),
        rbac_api: RbacApi = Depends(get_rbac_api),
        uow: AbstractProjectsUnitOfWork = Depends(get_uow),
    ) -> ProjectPermissionGrant:
        user = auth_api.current_user()
        environment = await uow.environments.get_by_id(environment_id)
        if environment is None:
            raise EnvironmentNotFound()
        grant = await resolve_project_permissions(environment.project_id, user, rbac_api, uow)
        if f"{resource}.{action}" not in grant.permissions:
            raise ProjectPermissionDenied()
        return grant

    return check


def require_project_permission_for_link(resource: str, action: str):
    """Same as require_project_permission, keyed by link_id."""

    async def check(
        link_id: UUID,
        auth_api: AuthApi = Depends(get_auth_api),
        rbac_api: RbacApi = Depends(get_rbac_api),
        uow: AbstractProjectsUnitOfWork = Depends(get_uow),
    ) -> ProjectPermissionGrant:
        user = auth_api.current_user()
        link = await uow.project_links.get_by_id(link_id)
        if link is None:
            raise ProjectLinkNotFound()
        grant = await resolve_project_permissions(link.project_id, user, rbac_api, uow)
        if f"{resource}.{action}" not in grant.permissions:
            raise ProjectPermissionDenied()
        return grant

    return check


def require_project_membership_for_project_role():
    """Resolves project_role_id (path) -> project_id, then the plain
    binary membership check — used by PATCH/DELETE /project-roles/{id},
    which are also gated by require_project_permission(project_role, manage)
    (Layer 1)."""

    async def check(
        project_role_id: UUID,
        auth_api: AuthApi = Depends(get_auth_api),
        rbac_api: RbacApi = Depends(get_rbac_api),
        uow: AbstractProjectsUnitOfWork = Depends(get_uow),
    ) -> None:
        user = auth_api.current_user()
        role = await uow.project_roles.get_by_id(project_role_id)
        if role is None:
            raise ProjectRoleNotFound()
        await resolve_project_membership(role.project_id, user, rbac_api, uow)

    return check


async def get_create_project(
    uow: AbstractProjectsUnitOfWork = Depends(get_uow), audit_api: AuditApi = Depends(get_audit_api)
) -> CreateProject:
    """Provide the create-project use case."""
    return CreateProject(uow, audit_api)


async def get_update_project(
    uow: AbstractProjectsUnitOfWork = Depends(get_uow), audit_api: AuditApi = Depends(get_audit_api)
) -> UpdateProject:
    """Provide the update-project use case."""
    return UpdateProject(uow, audit_api)


async def get_delete_project(
    uow: AbstractProjectsUnitOfWork = Depends(get_uow), audit_api: AuditApi = Depends(get_audit_api)
) -> DeleteProject:
    """Provide the delete-project use case."""
    return DeleteProject(uow, audit_api)


async def get_create_environment(
    uow: AbstractProjectsUnitOfWork = Depends(get_uow), audit_api: AuditApi = Depends(get_audit_api)
) -> CreateEnvironment:
    """Provide the create-environment use case."""
    return CreateEnvironment(uow, audit_api)


async def get_update_environment(
    uow: AbstractProjectsUnitOfWork = Depends(get_uow), audit_api: AuditApi = Depends(get_audit_api)
) -> UpdateEnvironment:
    """Provide the update-environment use case."""
    return UpdateEnvironment(uow, audit_api)


async def get_delete_environment(
    uow: AbstractProjectsUnitOfWork = Depends(get_uow), audit_api: AuditApi = Depends(get_audit_api)
) -> DeleteEnvironment:
    """Provide the delete-environment use case."""
    return DeleteEnvironment(uow, audit_api)


async def get_create_project_link(uow: AbstractProjectsUnitOfWork = Depends(get_uow)) -> CreateProjectLink:
    """Provide the create-project-link use case."""
    return CreateProjectLink(uow)


async def get_update_project_link(uow: AbstractProjectsUnitOfWork = Depends(get_uow)) -> UpdateProjectLink:
    """Provide the update-project-link use case."""
    return UpdateProjectLink(uow)


async def get_delete_project_link(uow: AbstractProjectsUnitOfWork = Depends(get_uow)) -> DeleteProjectLink:
    """Provide the delete-project-link use case."""
    return DeleteProjectLink(uow)


async def get_list_visible_projects(
    uow: AbstractProjectsUnitOfWork = Depends(get_uow), rbac_api: RbacApi = Depends(get_rbac_api)
) -> ListVisibleProjects:
    """Provide the list-visible-projects use case."""
    return ListVisibleProjects(uow, rbac_api)


async def get_list_project_members(
    uow: AbstractProjectsUnitOfWork = Depends(get_uow), users_api: UsersApi = Depends(get_users_api)
) -> ListProjectMembers:
    """Provide the list-project-members use case."""
    return ListProjectMembers(uow, users_api)


async def get_add_project_member(
    uow: AbstractProjectsUnitOfWork = Depends(get_uow), audit_api: AuditApi = Depends(get_audit_api)
) -> AddProjectMember:
    """Provide the add-project-member use case."""
    return AddProjectMember(uow, audit_api)


async def get_remove_project_member(
    uow: AbstractProjectsUnitOfWork = Depends(get_uow), audit_api: AuditApi = Depends(get_audit_api)
) -> RemoveProjectMember:
    """Provide the remove-project-member use case."""
    return RemoveProjectMember(uow, audit_api)


async def get_create_project_role(
    uow: AbstractProjectsUnitOfWork = Depends(get_uow),
    rbac_api: RbacApi = Depends(get_rbac_api),
    audit_api: AuditApi = Depends(get_audit_api),
) -> CreateProjectRole:
    """Provide the create-project-role use case."""
    return CreateProjectRole(uow, rbac_api, audit_api)


async def get_update_project_role(
    uow: AbstractProjectsUnitOfWork = Depends(get_uow),
    rbac_api: RbacApi = Depends(get_rbac_api),
    audit_api: AuditApi = Depends(get_audit_api),
) -> UpdateProjectRole:
    """Provide the update-project-role use case."""
    return UpdateProjectRole(uow, rbac_api, audit_api)


async def get_delete_project_role(
    uow: AbstractProjectsUnitOfWork = Depends(get_uow), audit_api: AuditApi = Depends(get_audit_api)
) -> DeleteProjectRole:
    """Provide the delete-project-role use case."""
    return DeleteProjectRole(uow, audit_api)


async def get_list_project_roles(
    uow: AbstractProjectsUnitOfWork = Depends(get_uow), rbac_api: RbacApi = Depends(get_rbac_api)
) -> ListProjectRoles:
    """Provide the list-project-roles use case."""
    return ListProjectRoles(uow, rbac_api)


async def get_assign_member_project_role(
    uow: AbstractProjectsUnitOfWork = Depends(get_uow), audit_api: AuditApi = Depends(get_audit_api)
) -> AssignMemberProjectRole:
    """Provide the assign-member-project-role use case."""
    return AssignMemberProjectRole(uow, audit_api)


async def get_list_assignable_permissions(
    rbac_api: RbacApi = Depends(get_rbac_api),
) -> ListAssignablePermissions:
    """Provide the list-assignable-permissions use case."""
    return ListAssignablePermissions(rbac_api)
