"""Remove an environment's Cloudflare binding. Blocked while any dns_records
row still references the environment — deleting the binding first would
orphan them with no zone_id to resolve from."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.cloudflare.constants import CloudflareDnsAuditActions
from app.modules.cloudflare.exceptions import CloudflareConfigNotFound, DnsRecordsExistForConfig
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork


class DeleteCloudflareConfig(AbstractUseCase):
    """Router gates this with require_account_access_for_environment(EDITOR)
    directly — actor identity passed as plain actor_id/actor_email, matching
    DeleteCloudflareAccount's shape (no request-body-dependent decision needing grant)."""

    def __init__(self, uow: AbstractCloudflareUnitOfWork, audit_api: AuditApi) -> None:
        self._uow = uow
        self._audit_api = audit_api

    @use_case
    async def execute(self, environment_id: UUID, *, actor_id: UUID, actor_email: str) -> None:
        existing = await self._uow.configs.get_by_environment_id(environment_id)
        if existing is None:
            raise CloudflareConfigNotFound()

        if await self._uow.dns_records.list_for_environment(environment_id):
            raise DnsRecordsExistForConfig()

        await self._uow.configs.delete_by_environment_id(environment_id)
        await self._uow.commit()

        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action=CloudflareDnsAuditActions.CONFIG_DELETED,
            severity=AuditSeverity.INFO,
            message="Environment unbound from Cloudflare",
            actor=AuditActor(user_id=actor_id, email=actor_email),
        )
