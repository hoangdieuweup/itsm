"""Dependency wiring for the projects module. The composition root: the only
place that names a concrete class (ProjectsUnitOfWork) instead of its
Abstract* contract."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.integrations.cache.client import CacheClient
from app.integrations.cache.dependencies import get_cache
from app.modules.projects.uow import ProjectsUnitOfWork


async def get_uow(
    session: AsyncSession = Depends(get_session), cache: CacheClient = Depends(get_cache)
) -> ProjectsUnitOfWork:
    """Provide a request scoped unit of work. The one place the concrete class is named."""
    return ProjectsUnitOfWork(session, cache)
