"""Update a Cloudflare account: rename its label and/or rotate its token."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.core.crypto import FernetCodec
from app.integrations.cloudflare.client import CloudflareClient
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.cloudflare.config import cloudflare_settings
from app.modules.cloudflare.constants import CloudflareAccountAuditActions
from app.modules.cloudflare.exceptions import CloudflareAccountNotFound, InsufficientAccountAccess
from app.modules.cloudflare.rules import CloudflareAccountRules
from app.modules.cloudflare.schemas import AccountAccessGrant, CloudflareAccountRead
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork


class UpdateCloudflareAccount(AbstractUseCase):
    """Rename and/or rotate an account's token.

    Structural correction from the Phase 3 pressure-test: the router's
    require_account_access(EDITOR) dependency is only a FLOOR check — it
    cannot know at decoration time whether this particular request rotates
    the token, since min_level is bound before any request (or its body)
    exists. The body-dependent OWNER requirement is therefore re-validated
    HERE, against the AccountAccessGrant the router already resolved, rather
    than being stapled onto a second Depends factory that has no way to see
    the parsed request body.
    """

    def __init__(
        self, uow: AbstractCloudflareUnitOfWork, client: CloudflareClient, audit_api: AuditApi
    ) -> None:
        self._uow = uow
        self._client = client
        self._audit_api = audit_api

    @use_case
    async def execute(
        self,
        account_id: UUID,
        *,
        label: str | None,
        api_token: str | None,
        grant: AccountAccessGrant,
        actor_email: str,
    ) -> CloudflareAccountRead:
        existing = await self._uow.accounts.get_by_id(account_id)
        if existing is None:
            raise CloudflareAccountNotFound()

        rotates_token = api_token is not None
        required = CloudflareAccountRules.required_level_for_update(rotates_token=rotates_token)
        if not CloudflareAccountRules.satisfies_level(grant.held_level, required):
            raise InsufficientAccountAccess()

        ciphertext = None
        if rotates_token:
            await self._client.test_connection(cf_account_id=existing.cf_account_id, api_token=api_token)
            ciphertext = FernetCodec.encrypt(api_token, key=cloudflare_settings.FERNET_KEY)

        account = await self._uow.accounts.update(account_id, label=label, api_token=ciphertext)
        await self._uow.commit()

        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action=CloudflareAccountAuditActions.ACCOUNT_UPDATED,
            severity=AuditSeverity.INFO,
            message=f"Cloudflare account '{account.label}' updated",
            actor=AuditActor(user_id=grant.user.id, email=actor_email),
        )
        return account
