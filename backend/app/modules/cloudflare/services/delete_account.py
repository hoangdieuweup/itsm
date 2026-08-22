"""Delete a Cloudflare account. Its manager rows cascade at the DB level."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.cloudflare.constants import CloudflareAccountAuditActions
from app.modules.cloudflare.exceptions import CloudflareAccountNotFound
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork


class DeleteCloudflareAccount(AbstractUseCase):
    """Delete an account. Router gates this with require_account_access(OWNER)
    directly — no request-body-dependent decision, unlike UpdateCloudflareAccount."""

    def __init__(self, uow: AbstractCloudflareUnitOfWork, audit_api: AuditApi) -> None:
        self._uow = uow
        self._audit_api = audit_api

    @use_case
    async def execute(self, account_id: UUID, *, actor_id: UUID, actor_email: str) -> None:
        existing = await self._uow.accounts.get_by_id(account_id)
        if existing is None:
            raise CloudflareAccountNotFound()

        await self._uow.accounts.delete(account_id)
        await self._uow.commit()

        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action=CloudflareAccountAuditActions.ACCOUNT_DELETED,
            severity=AuditSeverity.INFO,
            message=f"Cloudflare account '{existing.label}' deleted",
            actor=AuditActor(user_id=actor_id, email=actor_email),
        )
