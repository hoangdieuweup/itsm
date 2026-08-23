"""Configure Loki for an environment. Mirrors CreateCloudflareConfig's
overall shape: validate the environment exists, reject a duplicate binding,
encrypt the secret, commit, audit."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.core.crypto import FernetCodec
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.observability.config import observability_settings
from app.modules.observability.constants import LokiAuthType, ObservabilityAuditActions
from app.modules.observability.exceptions import LokiConfigAlreadyExists, ObservabilityEnvironmentNotFound
from app.modules.observability.schemas import LokiConfigRead
from app.modules.observability.uow import AbstractObservabilityUnitOfWork
from app.modules.projects.public import ProjectsApi
from app.modules.users.public import UserRead


class CreateLokiConfig(AbstractUseCase):
    def __init__(
        self, uow: AbstractObservabilityUnitOfWork, projects_api: ProjectsApi, audit_api: AuditApi
    ) -> None:
        self._uow = uow
        self._projects_api = projects_api
        self._audit_api = audit_api

    @use_case
    async def execute(
        self,
        environment_id: UUID,
        *,
        endpoint_url: str,
        tenant_id: str | None,
        auth_type: LokiAuthType,
        credential: str | None,
        default_query: str,
        default_range_minutes: int,
        actor: UserRead,
    ) -> LokiConfigRead:
        environment = await self._projects_api.get_environment_by_id(environment_id)
        if environment is None:
            raise ObservabilityEnvironmentNotFound()

        if await self._uow.loki_configs.get_by_environment_id(environment_id) is not None:
            raise LokiConfigAlreadyExists()

        ciphertext = None
        if auth_type != LokiAuthType.NONE and credential is not None:
            ciphertext = FernetCodec.encrypt(credential, key=observability_settings.FERNET_KEY)

        config = await self._uow.loki_configs.create(
            environment_id=environment_id,
            endpoint_url=endpoint_url,
            tenant_id=tenant_id,
            auth_type=auth_type,
            credential=ciphertext,
            default_query=default_query,
            default_range_minutes=default_range_minutes,
        )
        await self._uow.commit()

        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action=ObservabilityAuditActions.LOKI_CONFIG_CREATED,
            severity=AuditSeverity.INFO,
            message=f"Loki config created for environment {environment_id}",
            actor=AuditActor(user_id=actor.id, email=actor.email),
            environment_id=environment_id,
        )
        return config
