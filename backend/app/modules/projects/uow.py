"""Transaction boundary for the projects module."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.uow import AbstractCachedUnitOfWork
from app.core.uow import CachedSqlAlchemyUnitOfWork
from app.integrations.cache.client import CacheClient
from app.modules.projects.repository import (
    AbstractEnvironmentRepository,
    AbstractProjectLinkRepository,
    AbstractProjectMemberRepository,
    AbstractProjectRepository,
    AbstractProjectRoleRepository,
    EnvironmentRepository,
    ProjectLinkRepository,
    ProjectMemberRepository,
    ProjectRepository,
    ProjectRoleRepository,
)


class AbstractProjectsUnitOfWork(AbstractCachedUnitOfWork):
    """Contract a use case depends on instead of the concrete SQLAlchemy class below."""

    projects: AbstractProjectRepository
    environments: AbstractEnvironmentRepository
    project_links: AbstractProjectLinkRepository
    project_members: AbstractProjectMemberRepository
    project_roles: AbstractProjectRoleRepository


class ProjectsUnitOfWork(AbstractProjectsUnitOfWork, CachedSqlAlchemyUnitOfWork):
    """Owns the transaction for the projects module's tables."""

    def __init__(self, session: AsyncSession, cache: CacheClient) -> None:
        super().__init__(session, cache)
        self.projects = ProjectRepository(session, cache)
        self.environments = EnvironmentRepository(session, cache)
        self.project_links = ProjectLinkRepository(session)
        self.project_members = ProjectMemberRepository(session)
        self.project_roles = ProjectRoleRepository(session)
