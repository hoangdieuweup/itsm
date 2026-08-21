"""Dependency wiring for the projects module. The composition root: the only
place that names a concrete class (ProjectsUnitOfWork) instead of its
Abstract* contract."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.integrations.cache.client import CacheClient
from app.integrations.cache.dependencies import get_cache
from app.modules.audit.public import AuditApi, get_audit_api
from app.modules.projects.services.create_environment import CreateEnvironment
from app.modules.projects.services.create_project import CreateProject
from app.modules.projects.services.create_project_link import CreateProjectLink
from app.modules.projects.services.delete_environment import DeleteEnvironment
from app.modules.projects.services.delete_project import DeleteProject
from app.modules.projects.services.delete_project_link import DeleteProjectLink
from app.modules.projects.services.update_environment import UpdateEnvironment
from app.modules.projects.services.update_project import UpdateProject
from app.modules.projects.services.update_project_link import UpdateProjectLink
from app.modules.projects.uow import AbstractProjectsUnitOfWork, ProjectsUnitOfWork


async def get_uow(
    session: AsyncSession = Depends(get_session), cache: CacheClient = Depends(get_cache)
) -> ProjectsUnitOfWork:
    """Provide a request scoped unit of work. The one place the concrete class is named."""
    return ProjectsUnitOfWork(session, cache)


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
