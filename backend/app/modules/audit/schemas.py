"""Schemas for the audit module."""

from datetime import datetime
from uuid import UUID

from app.core.models import FrozenModel
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource


class AuditActor(FrozenModel):
    """Who performed the action, when known — absent for system-detected events."""

    user_id: UUID | None = None
    email: str | None = None


class AuditLogEntry(FrozenModel):
    """One row of the `logs` collection, as read back for the viewer."""

    id: str
    type: AuditEventType
    project_id: UUID | None = None
    environment_id: UUID | None = None
    source: AuditSource
    actor: AuditActor
    action: str
    severity: AuditSeverity
    incident_id: str | None = None
    message: str
    payload: dict = {}
    timestamp: datetime
    created_at: datetime
