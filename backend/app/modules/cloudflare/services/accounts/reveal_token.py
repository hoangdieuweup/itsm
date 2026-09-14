"""Reveal a Cloudflare account's plaintext token, on demand only."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.cloudflare.constants import CloudflareAccountAuditActions
from app.modules.cloudflare.exceptions import CloudflareAccountNotFound
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork


class RevealCloudflareAccountToken(AbstractUseCase):
    """Decrypt and return an account's plaintext token. Router gates this
    with require_account_access(OWNER). The audit entry logs the account and
    actor only — NEVER the decrypted token value, since Mongo's free-form
    log payload has none of Postgres's column-level discipline."""

    def __init__(self, uow: AbstractCloudflareUnitOfWork, audit_api: AuditApi) -> None:
        self._uow = uow
        self._audit_api = audit_api

    @use_case
    async def execute(self, account_id: UUID, *, actor_id: UUID, actor_email: str) -> str:
        account = await self._uow.accounts.get_by_id(account_id)
        if account is None:
            raise CloudflareAccountNotFound()
        credentials = await self._uow.accounts.get_credentials(account_id)
        if credentials is None:
            raise CloudflareAccountNotFound()

        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action=CloudflareAccountAuditActions.TOKEN_REVEALED,
            severity=AuditSeverity.HIGH,
            message=f"Cloudflare account '{account.label}' token revealed",
            actor=AuditActor(user_id=actor_id, email=actor_email),
        )
        return credentials.api_token
