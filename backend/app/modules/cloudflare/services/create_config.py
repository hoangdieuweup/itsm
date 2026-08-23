"""Bind an environment to a Cloudflare account + zone. Calls Cloudflare to
verify zone ownership BEFORE persisting — same "call the external API
before persisting" principle as CreateCloudflareAccount's test_connection
call."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.core.crypto import FernetCodec
from app.integrations.cloudflare.client import CloudflareClient
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.cloudflare.access import resolve_account_access_grant
from app.modules.cloudflare.config import cloudflare_settings
from app.modules.cloudflare.constants import AccessLevel, CloudflareDnsAuditActions
from app.modules.cloudflare.exceptions import (
    CloudflareAccountNotFound,
    CloudflareConfigAlreadyExists,
    CloudflareEnvironmentNotFound,
    ZoneNotOwnedByAccount,
)
from app.modules.cloudflare.schemas import CloudflareConfigRead
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork
from app.modules.projects.public import ProjectsApi
from app.modules.rbac.public import RbacApi
from app.modules.users.public import UserRead


class CreateCloudflareConfig(AbstractUseCase):
    """Resolves the Layer-2 grant itself (Decision #1) since
    cloudflare_account_id only exists in the request body — no path segment
    exists yet for a Depends(require_account_access(...)) factory to read."""

    def __init__(
        self,
        uow: AbstractCloudflareUnitOfWork,
        client: CloudflareClient,
        rbac_api: RbacApi,
        projects_api: ProjectsApi,
        audit_api: AuditApi,
    ) -> None:
        self._uow = uow
        self._client = client
        self._rbac_api = rbac_api
        self._projects_api = projects_api
        self._audit_api = audit_api

    @use_case
    async def execute(
        self, environment_id: UUID, cloudflare_account_id: UUID, zone_id: str, *, actor: UserRead
    ) -> CloudflareConfigRead:
        await resolve_account_access_grant(
            cloudflare_account_id, actor, self._rbac_api, self._uow, AccessLevel.EDITOR
        )

        environment = await self._projects_api.get_environment_by_id(environment_id)
        if environment is None:
            raise CloudflareEnvironmentNotFound()

        if await self._uow.configs.get_by_environment_id(environment_id) is not None:
            raise CloudflareConfigAlreadyExists()

        account = await self._uow.accounts.get_by_id(cloudflare_account_id)
        if account is None:
            raise CloudflareAccountNotFound()
        ciphertext = await self._uow.accounts.get_token_ciphertext(cloudflare_account_id)
        if ciphertext is None:
            raise CloudflareAccountNotFound()
        plaintext = FernetCodec.decrypt(ciphertext, key=cloudflare_settings.FERNET_KEY)

        zones = await self._client.list_zones(cf_account_id=account.cf_account_id, api_token=plaintext)
        matched = next((z for z in zones if z.id == zone_id), None)
        if matched is None:
            raise ZoneNotOwnedByAccount()

        config = await self._uow.configs.create(
            environment_id=environment_id,
            cloudflare_account_id=cloudflare_account_id,
            zone_id=zone_id,
            zone_name=matched.name,
        )
        await self._uow.commit()

        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action=CloudflareDnsAuditActions.CONFIG_CREATED,
            severity=AuditSeverity.INFO,
            message=f"Environment bound to Cloudflare zone '{matched.name}'",
            actor=AuditActor(user_id=actor.id, email=actor.email),
        )
        return config
