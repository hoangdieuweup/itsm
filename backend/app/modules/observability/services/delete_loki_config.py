from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.observability.constants import ObservabilityAuditActions
from app.modules.observability.exceptions import LokiConfigNotFound
from app.modules.observability.uow import AbstractObservabilityUnitOfWork
from app.modules.users.public import UserRead


class DeleteLokiConfig(AbstractUseCase):
    def __init__(self, uow: AbstractObservabilityUnitOfWork, audit_api: AuditApi) -> None:
        self._uow = uow
        self._audit_api = audit_api

    @use_case
    async def execute(self, environment_id: UUID, *, actor: UserRead) -> None:
        existing = await self._uow.loki_configs.get_by_environment_id(environment_id)
        if existing is None:
            raise LokiConfigNotFound()

        await self._uow.loki_configs.delete_by_environment_id(environment_id)
        await self._uow.commit()

        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action=ObservabilityAuditActions.LOKI_CONFIG_DELETED,
            severity=AuditSeverity.INFO,
            message=f"Loki config deleted for environment {environment_id}",
            actor=AuditActor(user_id=actor.id, email=actor.email),
            environment_id=environment_id,
        )
