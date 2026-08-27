"""Contract exposed to other modules. This is the ONLY file another module
may import from cloudflare — enforced by scripts/check_module_boundaries.py
and the cloudflare-facade contract in .importlinter.

Phase 9 is the first real cross-module consumer: observability's alerting
flow needs a ready Cloudflare client + decrypted token for an environment,
and a way to register/read the per-account webhook destination secret used
to verify inbound Cloudflare Notifications webhooks.
"""

import secrets
from uuid import UUID

from fastapi import Depends

from app.core.base.markers import facade
from app.core.crypto import FernetCodec
from app.integrations.cloudflare.client import CloudflareClient
from app.integrations.cloudflare.dependencies import get_cloudflare_client
from app.modules.cloudflare.config import cloudflare_settings
from app.modules.cloudflare.constants import CloudflareWebhookDefaults, DriftKind, ManagedBy
from app.modules.cloudflare.dependencies import get_uow, require_account_access
from app.modules.cloudflare.schemas import (
    CloudflareConfigRead,
    DnsReconciliationDiff,
    ReadyCloudflareClient,
    TunnelDriftEntry,
    TunnelPublicHostnameRead,
)
from app.modules.cloudflare.services.sync_dns_records import SyncDnsRecords
from app.modules.cloudflare.services.sync_tunnels import SyncTunnels
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork
from app.modules.projects.public import ProjectsApi, get_projects_api

__all__ = [
    "ReadyCloudflareClient",
    "DnsReconciliationDiff",
    "TunnelDriftEntry",
    "DriftKind",
    "CloudflareApi",
    "get_cloudflare_api",
    "require_account_access",
]


class CloudflareApi:
    """Facade over cloudflare accounts/configs for other modules' cross-module needs."""

    def __init__(
        self, uow: AbstractCloudflareUnitOfWork, client: CloudflareClient, *, projects_api: ProjectsApi
    ) -> None:
        self._uow = uow
        self._client = client
        self._projects_api = projects_api

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
            zone_id=config.zone_id,
        )

    @facade
    async def get_ready_client_for_account(self, cloudflare_account_id: UUID) -> ReadyCloudflareClient | None:
        """Resolves a Cloudflare account id directly — no environment/config
        lookup, since some routes (e.g. available-alerts) are account-scoped
        with no environment anywhere in their path. Returns None if the
        account doesn't exist or has no stored token."""
        account = await self._uow.accounts.get_by_id(cloudflare_account_id)
        ciphertext = await self._uow.accounts.get_token_ciphertext(cloudflare_account_id)
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
            name=CloudflareWebhookDefaults.DESTINATION_NAME,
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

    @facade
    async def list_bound_configs(self) -> list[CloudflareConfigRead]:
        """Every environment currently bound to a Cloudflare account/zone —
        the full set the drift reconciliation job must consider on each
        pass."""
        return await self._uow.configs.list_all()

    @facade
    async def reconcile_dns_records(self, environment_id: UUID) -> DnsReconciliationDiff:
        """Snapshot dns_records for environment_id, run the existing
        on-demand SyncDnsRecords unchanged (it already does the real
        Cloudflare fetch + upsert-as-EXTERNAL + delete-stale work), snapshot
        again, and diff the two by cf_record_id. new_external: genuinely new
        discoveries (present after but not before, and marked EXTERNAL —
        excludes a record that merely had a field updated). vanished:
        present before but gone after (SyncDnsRecords already deleted them;
        this list exists purely so the caller can still raise an incident
        referencing what was removed)."""
        before = {r.cf_record_id: r for r in await self._uow.dns_records.list_for_environment(environment_id)}
        after_list = await SyncDnsRecords(self._uow, self._client, self._projects_api).execute(environment_id)
        after = {r.cf_record_id: r for r in after_list}
        new_external = [
            r for cf_id, r in after.items() if cf_id not in before and r.managed_by == ManagedBy.EXTERNAL
        ]
        vanished = [r for cf_id, r in before.items() if cf_id not in after]
        return DnsReconciliationDiff(new_external=new_external, vanished=vanished)

    @facade
    async def reconcile_tunnels_for_account(self, cloudflare_account_id: UUID) -> list[TunnelDriftEntry]:
        """Account-wide, matching SyncTunnels' own scope — a tunnel serves
        many environments at once, so reconciling per-environment would
        either redundantly re-sync the same account once per sibling
        environment, or misattribute drift to whichever environment
        happened to trigger the pass. Snapshots every hostname currently
        matched to ANY environment bound to this account, runs SyncTunnels
        once, diffs by hostname. Hostnames matched to no tracked environment
        are excluded — there's no environment to attach an incident to, and
        no reason to: drift on a hostname this app doesn't track isn't this
        app's concern."""
        sibling_environment_ids = await self._uow.configs.list_environment_ids_for_account(
            cloudflare_account_id
        )
        if not sibling_environment_ids:
            return []

        before: dict[str, TunnelPublicHostnameRead] = {}
        for environment_id in sibling_environment_ids:
            for h in await self._uow.tunnel_hostnames.list_for_environment(environment_id):
                before[h.hostname] = h

        await SyncTunnels(self._uow, self._client, self._projects_api).execute(sibling_environment_ids[0])

        after: dict[str, TunnelPublicHostnameRead] = {}
        for environment_id in sibling_environment_ids:
            for h in await self._uow.tunnel_hostnames.list_for_environment(environment_id):
                after[h.hostname] = h

        entries: list[TunnelDriftEntry] = []
        for hostname, h in after.items():
            if hostname not in before and h.managed_by == ManagedBy.EXTERNAL and h.environment_id is not None:
                entries.append(
                    TunnelDriftEntry(kind=DriftKind.NEW_EXTERNAL, environment_id=h.environment_id, hostname=h)
                )
        for hostname, h in before.items():
            if hostname not in after and h.environment_id is not None:
                entries.append(
                    TunnelDriftEntry(kind=DriftKind.VANISHED, environment_id=h.environment_id, hostname=h)
                )
        return entries


async def get_cloudflare_api(
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow),
    client: CloudflareClient = Depends(get_cloudflare_client),
    projects_api: ProjectsApi = Depends(get_projects_api),
) -> CloudflareApi:
    """Provide the facade to other modules."""
    return CloudflareApi(uow, client, projects_api=projects_api)
