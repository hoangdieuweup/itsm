"""Create a Cloudflare account: Cloudflare must confirm the token BEFORE
anything is persisted, then the creator becomes the account's first OWNER."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.core.crypto import FernetCodec
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.cloudflare.client import CloudflareClient
from app.modules.cloudflare.config import cloudflare_settings
from app.modules.cloudflare.constants import AccessLevel, CloudflareAccountAuditActions
from app.modules.cloudflare.schemas import CloudflareAccountRead
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork


class CreateCloudflareAccount(AbstractUseCase):
    """Create an account, testing the token against Cloudflare's API first —
    same "call the external API before persisting" principle later DNS/Tunnel
    phases reuse. The creator becomes the account's first OWNER (mirrors
    CreateProject's auto-inserted default links: bootstrapping logic lives in
    the use case, not a template row)."""

    def __init__(
        self, uow: AbstractCloudflareUnitOfWork, client: CloudflareClient, audit_api: AuditApi
    ) -> None:
        self._uow = uow
        self._client = client
        self._audit_api = audit_api

    @use_case
    async def execute(
        self, label: str, cf_account_id: str, api_token: str, *, actor_id: UUID, actor_email: str
    ) -> CloudflareAccountRead:
        await self._client.test_connection(cf_account_id=cf_account_id, api_token=api_token)

        ciphertext = FernetCodec.encrypt(api_token, key=cloudflare_settings.FERNET_KEY)
        account = await self._uow.accounts.create(
            label=label, cf_account_id=cf_account_id, api_token=ciphertext, created_by=actor_id
        )
        await self._uow.account_managers.upsert(account.id, actor_id, AccessLevel.OWNER)
        await self._uow.commit()

        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action=CloudflareAccountAuditActions.ACCOUNT_CREATED,
            severity=AuditSeverity.INFO,
            message=f"Cloudflare account '{account.label}' created",
            actor=AuditActor(user_id=actor_id, email=actor_email),
        )
        return account
