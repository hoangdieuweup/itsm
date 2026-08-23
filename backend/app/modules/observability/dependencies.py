"""FastAPI dependency providers for the observability module. Every provider
depends on an Abstract* contract."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.integrations.loki.client import LokiClient
from app.integrations.loki.dependencies import get_loki_client
from app.modules.audit.public import AuditApi, get_audit_api
from app.modules.observability.services.create_loki_config import CreateLokiConfig
from app.modules.observability.services.delete_loki_config import DeleteLokiConfig
from app.modules.observability.services.get_loki_config import GetLokiConfig
from app.modules.observability.services.run_log_query import RunLogQuery
from app.modules.observability.services.update_loki_config import UpdateLokiConfig
from app.modules.observability.uow import AbstractObservabilityUnitOfWork, ObservabilityUnitOfWork
from app.modules.projects.public import ProjectsApi, get_projects_api


async def get_uow(session: AsyncSession = Depends(get_session)) -> ObservabilityUnitOfWork:
    """Provide a request scoped unit of work. The one place the concrete class is named."""
    return ObservabilityUnitOfWork(session)


async def get_create_loki_config(
    uow: AbstractObservabilityUnitOfWork = Depends(get_uow),
    projects_api: ProjectsApi = Depends(get_projects_api),
    audit_api: AuditApi = Depends(get_audit_api),
) -> CreateLokiConfig:
    return CreateLokiConfig(uow, projects_api, audit_api)


async def get_get_loki_config(
    uow: AbstractObservabilityUnitOfWork = Depends(get_uow),
) -> GetLokiConfig:
    return GetLokiConfig(uow)


async def get_update_loki_config(
    uow: AbstractObservabilityUnitOfWork = Depends(get_uow),
    audit_api: AuditApi = Depends(get_audit_api),
) -> UpdateLokiConfig:
    return UpdateLokiConfig(uow, audit_api)


async def get_delete_loki_config(
    uow: AbstractObservabilityUnitOfWork = Depends(get_uow),
    audit_api: AuditApi = Depends(get_audit_api),
) -> DeleteLokiConfig:
    return DeleteLokiConfig(uow, audit_api)


async def get_run_log_query(
    uow: AbstractObservabilityUnitOfWork = Depends(get_uow),
    client: LokiClient = Depends(get_loki_client),
) -> RunLogQuery:
    return RunLogQuery(uow, client)
