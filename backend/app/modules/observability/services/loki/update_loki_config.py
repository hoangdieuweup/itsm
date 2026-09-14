"""Update an environment's Loki config. Every field is optional at this
layer — an omitted field keeps its existing value, mirroring
UpdateCloudflareAccount's label/api_token convention. tenant_id has no way
to be explicitly cleared through this endpoint (a real, accepted limitation
— delete and recreate the config instead); credential DOES have a clear
path: switching auth_type to NONE always clears it, regardless of whatever
credential value was also passed, since a NONE-auth config has no business
holding a leftover secret."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.observability.constants import LokiAuthType, ObservabilityAuditActions
from app.modules.observability.exceptions import LokiConfigNotFound
from app.modules.observability.schemas import LokiConfigRead
from app.modules.observability.uow import AbstractObservabilityUnitOfWork
from app.modules.users.public import UserRead


class UpdateLokiConfig(AbstractUseCase):
    def __init__(self, uow: AbstractObservabilityUnitOfWork, audit_api: AuditApi) -> None:
        self._uow = uow
        self._audit_api = audit_api

    @use_case
    async def execute(
        self,
        environment_id: UUID,
        *,
        endpoint_url: str | None = None,
        tenant_id: str | None = None,
        auth_type: LokiAuthType | None = None,
        credential: str | None = None,
        default_query: str | None = None,
        default_range_minutes: int | None = None,
        actor: UserRead,
    ) -> LokiConfigRead:
        existing = await self._uow.loki_configs.get_by_environment_id(environment_id)
        if existing is None:
            raise LokiConfigNotFound()

        new_auth_type = auth_type if auth_type is not None else existing.auth_type

        keep_credential = new_auth_type != LokiAuthType.NONE and credential is None

        config = await self._uow.loki_configs.update_by_environment_id(
            environment_id,
            endpoint_url=endpoint_url if endpoint_url is not None else existing.endpoint_url,
            tenant_id=tenant_id if tenant_id is not None else existing.tenant_id,
            auth_type=new_auth_type,
            credential=None if new_auth_type == LokiAuthType.NONE else credential,
            keep_credential=keep_credential,
            default_query=default_query if default_query is not None else existing.default_query,
            default_range_minutes=(
                default_range_minutes if default_range_minutes is not None else existing.default_range_minutes
            ),
        )
        await self._uow.commit()

        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action=ObservabilityAuditActions.LOKI_CONFIG_UPDATED,
            severity=AuditSeverity.INFO,
            message=f"Loki config updated for environment {environment_id}",
            actor=AuditActor(user_id=actor.id, email=actor.email),
            environment_id=environment_id,
        )
        return config
