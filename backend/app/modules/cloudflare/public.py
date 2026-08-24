"""Contract exposed to other modules. This is the ONLY file another module
may import from cloudflare — enforced by scripts/check_module_boundaries.py
and the cloudflare-facade contract in .importlinter.

Phase 9 is the first real cross-module consumer: observability's alerting
flow needs a ready Cloudflare client + decrypted token for an environment,
and a way to register/read the per-account webhook destination secret used
to verify inbound Cloudflare Notifications webhooks.
"""

import secrets
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends

from app.core.base.markers import facade
from app.core.crypto import FernetCodec
from app.integrations.cloudflare.client import CloudflareClient
from app.integrations.cloudflare.dependencies import get_cloudflare_client
from app.modules.cloudflare.config import cloudflare_settings
from app.modules.cloudflare.dependencies import get_uow, require_account_access
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork

__all__ = [
    "ReadyCloudflareClient",
    "CloudflareApi",
    "get_cloudflare_api",
    "require_account_access",
]


@dataclass(frozen=True)
class ReadyCloudflareClient:
    """Everything another module needs to call the Cloudflare API on behalf
    of one environment's bound account."""

    client: CloudflareClient
    cf_account_id: str
    api_token: str
    cloudflare_account_id: UUID


class CloudflareApi:
    """Facade over cloudflare accounts/configs for other modules' cross-module needs."""

    def __init__(self, uow: AbstractCloudflareUnitOfWork, client: CloudflareClient) -> None:
        self._uow = uow
        self._client = client

    @facade
    async def get_ready_client_for_environment(self, environment_id: UUID) -> ReadyCloudflareClient | None:
        """Resolves environment -> cloudflare_configs -> cloudflare_accounts,
        decrypts the account's token, and returns everything the caller needs
        to call the Cloudflare API. Returns None if the environment has no
        Cloudflare account bound (see cloudflare_configs, Phase 4)."""
        config = await self._uow.configs.get_by_environment_id(environment_id)
        if config is None:
            return None
        account = await self._uow.accounts.get_by_id(config.cloudflare_account_id)
        ciphertext = await self._uow.accounts.get_token_ciphertext(config.cloudflare_account_id)
        if account is None or ciphertext is None:
            return None
        plaintext = FernetCodec.decrypt(ciphertext, key=cloudflare_settings.FERNET_KEY)
        return ReadyCloudflareClient(
            client=self._client,
            cf_account_id=account.cf_account_id,
            api_token=plaintext,
            cloudflare_account_id=account.id,
        )

    @facade
    async def ensure_webhook_destination(self, cloudflare_account_id: UUID, *, webhook_url: str) -> str:
        """Idempotent: returns the existing cf_webhook_destination_id if
        already registered, otherwise registers a new destination with a
        freshly generated secret, persists both (secret Fernet-encrypted),
        and returns the new destination id. Returns the DESTINATION ID, not
        the secret — the caller (observability's CreateAlertRule) needs the
        id immediately afterward for create_policy's mechanisms.webhooks.
        The secret is a separate, read-only concern (get_webhook_secret
        below), fetched only by the webhook-auth verification path."""
        existing_id, _existing_ciphertext = await self._uow.accounts.get_webhook_destination_ciphertext(
            cloudflare_account_id
        )
        if existing_id:
            return existing_id

        account = await self._uow.accounts.get_by_id(cloudflare_account_id)
        ciphertext = await self._uow.accounts.get_token_ciphertext(cloudflare_account_id)
        if account is None or ciphertext is None:
            raise ValueError(f"cloudflare account {cloudflare_account_id} does not exist")
        plaintext_token = FernetCodec.decrypt(ciphertext, key=cloudflare_settings.FERNET_KEY)
        secret = secrets.token_urlsafe(32)
        destination_id = await self._client.create_webhook_destination(
            cf_account_id=account.cf_account_id,
            api_token=plaintext_token,
            name="itsm-alerting",
            url=webhook_url,
            secret=secret,
        )
        secret_ciphertext = FernetCodec.encrypt(secret, key=cloudflare_settings.FERNET_KEY)
        await self._uow.accounts.set_webhook_destination(
            cloudflare_account_id,
            cf_webhook_destination_id=destination_id,
            secret_ciphertext=secret_ciphertext,
        )
        await self._uow.commit()
        return destination_id

    @facade
    async def get_webhook_secret(self, cloudflare_account_id: UUID) -> str | None:
        """Read-only: the decrypted webhook secret for this account, or None
        if no destination has ever been registered. Used exclusively by
        verify_cloudflare_webhook_secret — never registers anything, unlike
        ensure_webhook_destination."""
        _existing_id, existing_ciphertext = await self._uow.accounts.get_webhook_destination_ciphertext(
            cloudflare_account_id
        )
        if existing_ciphertext is None:
            return None
        return FernetCodec.decrypt(existing_ciphertext, key=cloudflare_settings.FERNET_KEY)


async def get_cloudflare_api(
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow),
    client: CloudflareClient = Depends(get_cloudflare_client),
) -> CloudflareApi:
    """Provide the facade to other modules."""
    return CloudflareApi(uow, client)
