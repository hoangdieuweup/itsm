"""Remove a user's access to a Cloudflare account."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.cloudflare.constants import AccessLevel, CloudflareAccountAuditActions
from app.modules.cloudflare.exceptions import CloudflareAccountManagerNotFound, LastOwnerRemovalBlocked
from app.modules.cloudflare.rules import CloudflareAccountRules
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork


class RemoveCloudflareAccountManager(AbstractUseCase):
    """Remove a user's manager row entirely. Router gates this with
    require_account_access(OWNER)."""

    def __init__(self, uow: AbstractCloudflareUnitOfWork, audit_api: AuditApi) -> None:
        self._uow = uow
        self._audit_api = audit_api

    @use_case
    async def execute(
        self, account_id: UUID, target_user_id: UUID, *, actor_id: UUID, actor_email: str
    ) -> None:
        existing = await self._uow.account_managers.get_for_user(account_id, target_user_id)
        if existing is None:
            raise CloudflareAccountManagerNotFound()

        if existing.access_level == AccessLevel.OWNER:
            owner_count = await self._uow.account_managers.count_owners(account_id)
            if CloudflareAccountRules.blocks_last_owner_removal(existing.access_level, owner_count):
                raise LastOwnerRemovalBlocked()

        await self._uow.account_managers.remove(account_id, target_user_id)
        await self._uow.commit()

        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action=CloudflareAccountAuditActions.MANAGER_REMOVED,
            severity=AuditSeverity.INFO,
            message=f"User {target_user_id}'s access on account {account_id} removed",
            actor=AuditActor(user_id=actor_id, email=actor_email),
        )
