"""Contract exposed to other modules. This is the ONLY file another module
may import from audit — enforced by scripts/check_module_boundaries.py.
"""

import logging
from datetime import datetime
from uuid import UUID

from fastapi import Depends
from pymongo.errors import PyMongoError

from app.core.base.markers import facade
from app.integrations.mongo.exceptions import MongoUnavailable
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.dependencies import get_audit_repository
from app.modules.audit.repository import AbstractAuditLogRepository, MongoAuditLogRepository
from app.modules.audit.schemas import AuditActor, AuditLogEntry

__all__ = ["AuditActor", "AuditLogEntry", "AuditApi", "get_audit_api"]

logger = logging.getLogger(__name__)


class AuditApi:
    """Facade over the logs collection for every other module."""

    def __init__(self, repository: AbstractAuditLogRepository) -> None:
        self._repository = repository

    @facade
    async def log_event(
        self,
        *,
        type: AuditEventType,
        source: AuditSource,
        action: str,
        severity: AuditSeverity,
        message: str,
        actor: AuditActor,
        project_id: UUID | None = None,
        environment_id: UUID | None = None,
        incident_id: str | None = None,
        payload: dict | None = None,
    ) -> None:
        """Record an event. Fire-and-forget: a Mongo outage degrades to a
        logged warning, never an exception into the caller — the caller's
        own database transaction already committed by the time this runs,
        so there is nothing left to roll back."""
        try:
            await self._repository.insert(
                type=type,
                source=source,
                action=action,
                severity=severity,
                message=message,
                project_id=project_id,
                environment_id=environment_id,
                actor=actor,
                incident_id=incident_id,
                payload=payload or {},
            )
        except PyMongoError:
            logger.warning("audit log write failed, degrading silently", exc_info=True)

    @facade
    async def list_logs(
        self,
        *,
        project_id: UUID | None = None,
        environment_id: UUID | None = None,
        type: AuditEventType | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AuditLogEntry], int]:
        """Return one page of log entries. Unlike log_event, this must not
        swallow a Mongo outage — a broken log viewer should show an error,
        not silently claim there are no logs."""
        try:
            return await self._repository.list_page(
                project_id=project_id,
                environment_id=environment_id,
                type=type,
                since=since,
                until=until,
                limit=limit,
                offset=offset,
            )
        except PyMongoError as exc:
            raise MongoUnavailable() from exc


async def get_audit_api(
    repository: MongoAuditLogRepository = Depends(get_audit_repository),
) -> AuditApi:
    """Provide the facade to other modules."""
    return AuditApi(repository)
