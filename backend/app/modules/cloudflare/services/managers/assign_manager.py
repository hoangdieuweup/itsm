"""Grant a user a specific access_level on a Cloudflare account."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.cloudflare.constants import AccessLevel, CloudflareAccountAuditActions
from app.modules.cloudflare.exceptions import CloudflareAccountNotFound
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork


class AssignCloudflareAccountManager(AbstractUseCase):
    """Grant (or re-grant) a user a specific access_level on an account.
    Router gates this with require_account_access(OWNER) — only an existing
    OWNER (or a manage_all holder) can hand out access to someone else."""

    def __init__(self, uow: AbstractCloudflareUnitOfWork, audit_api: AuditApi) -> None:
        self._uow = uow
        self._audit_api = audit_api

    @use_case
    async def execute(
        self,
        account_id: UUID,
        target_user_id: UUID,
        access_level: AccessLevel,
        *,
        actor_id: UUID,
        actor_email: str,
    ) -> None:
        account = await self._uow.accounts.get_by_id(account_id)
        if account is None:
            raise CloudflareAccountNotFound()

        await self._uow.account_managers.upsert(account_id, target_user_id, access_level)
        await self._uow.commit()

        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action=CloudflareAccountAuditActions.MANAGER_ASSIGNED,
            severity=AuditSeverity.INFO,
            message=f"User {target_user_id} assigned {access_level.value} on '{account.label}'",
            actor=AuditActor(user_id=actor_id, email=actor_email),
        )
