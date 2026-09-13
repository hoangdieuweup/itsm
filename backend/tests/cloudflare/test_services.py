"""Unit tests for app.modules.cloudflare.services — Fake-based, no database,
no real Cloudflare API calls."""

import logging
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.core.crypto import FernetCodec
from app.integrations.cache.exceptions import CacheUnavailable
from app.integrations.cloudflare.exceptions import CloudflareApiUnavailable as CfUnavailable
from app.integrations.cloudflare.exceptions import InvalidCloudflareToken
from app.integrations.cloudflare.schemas import CloudflareTrafficStats, ZoneOption
from app.modules.cloudflare.config import cloudflare_settings
from app.modules.cloudflare.constants import (
    AccessLevel,
    CloudflareAccountAuditActions,
    DnsRecordType,
    ManagedBy,
    TunnelStatus,
)
from app.modules.cloudflare.exceptions import (
    CloudflareAccountManagerNotFound,
    CloudflareAccountNotFound,
    CloudflareConfigAlreadyExists,
    CloudflareConfigNotFound,
    CloudflareEnvironmentNotFound,
    CloudflareTunnelNotFound,
    DnsRecordNotFound,
    DnsRecordsExistForConfig,
    DnsRecordSyncFailed,
    EnvironmentBaseUrlNotConfigured,
    InsufficientAccountAccess,
    LastOwnerRemovalBlocked,
    MissingDnsRecordPriority,
    TunnelConfigLocked,
    TunnelHostnameAlreadyExists,
    TunnelHostnameDomainMismatch,
    TunnelHostnameEnvironmentMismatch,
    TunnelIngressSyncFailed,
    TunnelPublicHostnameNotFound,
    ZoneNotOwnedByAccount,
)
from app.modules.cloudflare.repository import (
    AbstractCloudflareAccountManagerRepository,
    AbstractCloudflareAccountRepository,
    CloudflareAccountManagerRow,
)
from app.modules.cloudflare.schemas import (
    AccountAccessGrant,
    CloudflareAccountRead,
    CloudflareConfigRead,
    CloudflareTunnelRead,
    DnsRecordRead,
    TunnelPublicHostnameRead,
)
from app.modules.cloudflare.services.add_tunnel_hostname import AddTunnelHostname
from app.modules.cloudflare.services.assign_manager import AssignCloudflareAccountManager
from app.modules.cloudflare.services.create_account import CreateCloudflareAccount
from app.modules.cloudflare.services.create_config import CreateCloudflareConfig
from app.modules.cloudflare.services.create_dns_record import CreateDnsRecord
from app.modules.cloudflare.services.create_tunnel import CreateCloudflareTunnel
from app.modules.cloudflare.services.delete_account import DeleteCloudflareAccount
from app.modules.cloudflare.services.delete_config import DeleteCloudflareConfig
from app.modules.cloudflare.services.delete_dns_record import DeleteDnsRecord
from app.modules.cloudflare.services.delete_tunnel import DeleteCloudflareTunnel
from app.modules.cloudflare.services.get_traffic_stats import GetCloudflareTrafficStats
from app.modules.cloudflare.services.list_account_managers import ListCloudflareAccountManagers
from app.modules.cloudflare.services.list_dns_records import ListDnsRecords
from app.modules.cloudflare.services.list_tunnel_hostnames import ListTunnelHostnames
from app.modules.cloudflare.services.list_tunnels import ListTunnels
from app.modules.cloudflare.services.list_visible_accounts import ListVisibleCloudflareAccounts
from app.modules.cloudflare.services.list_zones import ListZones
from app.modules.cloudflare.services.refresh_tunnel_status import RefreshTunnelStatus
from app.modules.cloudflare.services.remove_manager import RemoveCloudflareAccountManager
from app.modules.cloudflare.services.remove_tunnel_hostname import RemoveTunnelHostname
from app.modules.cloudflare.services.reveal_token import RevealCloudflareAccountToken
from app.modules.cloudflare.services.reveal_tunnel_token import RevealCloudflareTunnelToken
from app.modules.cloudflare.services.sync_dns_records import SyncDnsRecords
from app.modules.cloudflare.services.sync_tunnels import SyncTunnels
from app.modules.cloudflare.services.test_connection import TestCloudflareAccountConnection
from app.modules.cloudflare.services.update_account import UpdateCloudflareAccount
from app.modules.cloudflare.services.update_config import UpdateCloudflareConfig
from app.modules.cloudflare.services.update_dns_record import UpdateDnsRecord
from app.modules.cloudflare.services.update_manager import UpdateCloudflareAccountManager
from app.modules.cloudflare.services.update_tunnel_hostname import UpdateTunnelHostname
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork
from app.modules.users.public import UserRead


class FakeCloudflareAccountRepository(AbstractCloudflareAccountRepository):
    def __init__(self) -> None:
        self._rows: dict[UUID, CloudflareAccountRead] = {}
        self._ciphertexts: dict[UUID, str] = {}
        self._webhook_destinations: dict[UUID, tuple[str | None, str | None]] = {}

    async def get_by_id(self, entity_id: UUID) -> CloudflareAccountRead | None:
        return self._rows.get(entity_id)

    async def list_page(self, limit: int, offset: int) -> tuple[list[CloudflareAccountRead], int]:
        items = list(self._rows.values())[offset : offset + limit]
        return items, len(self._rows)

    async def list_for_ids(self, account_ids: list[UUID]) -> list[CloudflareAccountRead]:
        return [self._rows[i] for i in account_ids if i in self._rows]

    async def list_all(self) -> list[CloudflareAccountRead]:
        return sorted(self._rows.values(), key=lambda row: row.label)

    async def create(
        self, *, label: str, cf_account_id: str, api_token: str, created_by: UUID | None
    ) -> CloudflareAccountRead:
        account = CloudflareAccountRead(
            id=uuid4(),
            label=label,
            cf_account_id=cf_account_id,
            created_by=created_by,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self._rows[account.id] = account
        self._ciphertexts[account.id] = api_token
        return account

    async def update(
        self, account_id: UUID, *, label: str | None, api_token: str | None
    ) -> CloudflareAccountRead:
        existing = self._rows[account_id]
        updated = existing.model_copy(update={"label": label if label is not None else existing.label})
        self._rows[account_id] = updated
        if api_token is not None:
            self._ciphertexts[account_id] = api_token
        return updated

    async def delete(self, account_id: UUID) -> None:
        self._rows.pop(account_id, None)
        self._ciphertexts.pop(account_id, None)

    async def get_token_ciphertext(self, account_id: UUID) -> str | None:
        return self._ciphertexts.get(account_id)

    async def get_webhook_destination_ciphertext(self, account_id: UUID) -> tuple[str | None, str | None]:
        return self._webhook_destinations.get(account_id, (None, None))

    async def set_webhook_destination(
        self, account_id: UUID, *, cf_webhook_destination_id: str, secret_ciphertext: str
    ) -> None:
        self._webhook_destinations[account_id] = (cf_webhook_destination_id, secret_ciphertext)


class FakeCloudflareAccountManagerRepository(AbstractCloudflareAccountManagerRepository):
    def __init__(self) -> None:
        self._rows: dict[tuple[UUID, UUID], CloudflareAccountManagerRow] = {}

    async def get_by_id(self, entity_id: tuple) -> CloudflareAccountManagerRow | None:
        return self._rows.get(entity_id)

    async def list_page(self, limit: int, offset: int) -> tuple[list[CloudflareAccountManagerRow], int]:
        items = list(self._rows.values())[offset : offset + limit]
        return items, len(self._rows)

    async def get_for_user(self, account_id: UUID, user_id: UUID) -> CloudflareAccountManagerRow | None:
        return self._rows.get((account_id, user_id))

    async def list_for_account(self, account_id: UUID) -> list[CloudflareAccountManagerRow]:
        return [r for (aid, _), r in self._rows.items() if aid == account_id]

    async def list_for_user(self, user_id: UUID) -> list[CloudflareAccountManagerRow]:
        return [r for (_, uid), r in self._rows.items() if uid == user_id]

    async def count_owners(self, account_id: UUID) -> int:
        return sum(
            1
            for (aid, _), r in self._rows.items()
            if aid == account_id and r.access_level == AccessLevel.OWNER
        )

    async def upsert(
        self, account_id: UUID, user_id: UUID, access_level: AccessLevel
    ) -> CloudflareAccountManagerRow:
        row = CloudflareAccountManagerRow(
            cloudflare_account_id=account_id,
            user_id=user_id,
            access_level=access_level,
            created_at=datetime.now(UTC),
        )
        self._rows[(account_id, user_id)] = row
        return row

    async def remove(self, account_id: UUID, user_id: UUID) -> None:
        self._rows.pop((account_id, user_id), None)


class FakeConfigsRepo:
    def __init__(self) -> None:
        self._rows: dict = {}

    async def get_by_environment_id(self, environment_id):
        return self._rows.get(environment_id)

    async def create(self, *, environment_id, cloudflare_account_id, zone_id, zone_name):
        row = CloudflareConfigRead(
            id=uuid4(),
            environment_id=environment_id,
            cloudflare_account_id=cloudflare_account_id,
            zone_id=zone_id,
            zone_name=zone_name,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self._rows[environment_id] = row
        return row

    async def update_by_environment_id(self, environment_id, *, cloudflare_account_id, zone_id, zone_name):
        existing = self._rows[environment_id]
        updated = existing.model_copy(
            update={
                "cloudflare_account_id": cloudflare_account_id,
                "zone_id": zone_id,
                "zone_name": zone_name,
            }
        )
        self._rows[environment_id] = updated
        return updated

    async def delete_by_environment_id(self, environment_id):
        self._rows.pop(environment_id, None)

    async def list_environment_ids_for_account(self, cloudflare_account_id):
        return [
            row.environment_id
            for row in self._rows.values()
            if row.cloudflare_account_id == cloudflare_account_id
        ]

    async def list_environment_ids_for_zone(self, zone_id):
        return [row.environment_id for row in self._rows.values() if row.zone_id == zone_id]

    async def list_all(self):
        return list(self._rows.values())


class FakeDnsRecordsRepo:
    def __init__(self) -> None:
        self._rows: dict = {}

    async def list_for_environment(self, environment_id):
        return [r for r in self._rows.values() if r.environment_id == environment_id]

    async def get_by_id(self, record_id):
        return self._rows.get(record_id)

    async def create(
        self, *, environment_id, cf_record_id, record_type, name, content, priority, proxied, ttl, created_by
    ):
        row = DnsRecordRead(
            id=uuid4(),
            environment_id=environment_id,
            cf_record_id=cf_record_id,
            record_type=record_type,
            name=name,
            content=content,
            priority=priority,
            proxied=proxied,
            ttl=ttl,
            managed_by=ManagedBy.SYSTEM,
            created_by=created_by,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self._rows[row.id] = row
        return row

    async def update(self, record_id, *, content, priority, proxied, ttl):
        existing = self._rows[record_id]
        updated = existing.model_copy(
            update={"content": content, "priority": priority, "proxied": proxied, "ttl": ttl}
        )
        self._rows[record_id] = updated
        return updated

    async def delete(self, record_id):
        self._rows.pop(record_id, None)

    async def upsert_from_sync(
        self,
        *,
        environment_id,
        cf_record_id,
        record_type,
        name,
        content,
        priority,
        proxied,
        ttl,
        managed_by,
        last_synced_at,
    ):
        existing = next((r for r in self._rows.values() if r.cf_record_id == cf_record_id), None)
        if existing is None:
            row = DnsRecordRead(
                id=uuid4(),
                environment_id=environment_id,
                cf_record_id=cf_record_id,
                record_type=record_type,
                name=name,
                content=content,
                priority=priority,
                proxied=proxied,
                ttl=ttl,
                managed_by=managed_by,
                created_by=None,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            self._rows[row.id] = row
            return row
        # Mirrors the real repository: only EXTERNAL rows self-heal their
        # environment_id on every sync — a SYSTEM row's attribution was set
        # deliberately by CreateDnsRecord and must never be overwritten.
        new_environment_id = (
            environment_id if existing.managed_by == ManagedBy.EXTERNAL else existing.environment_id
        )
        updated = existing.model_copy(
            update={
                "environment_id": new_environment_id,
                "record_type": record_type,
                "name": name,
                "content": content,
                "priority": priority,
                "proxied": proxied,
                "ttl": ttl,
            }
        )
        self._rows[existing.id] = updated
        return updated

    async def delete_not_in_cf_ids(self, environment_ids, keep_cf_ids):
        stale = [
            r.id
            for r in self._rows.values()
            if r.environment_id in environment_ids and r.cf_record_id not in keep_cf_ids
        ]
        for record_id in stale:
            self._rows.pop(record_id, None)


class FakeCloudflareTunnelRepository:
    def __init__(self) -> None:
        self._rows: dict[UUID, CloudflareTunnelRead] = {}
        # Wired by FakeCloudflareUnitOfWork.__init__ right after both fakes
        # are constructed — mirrors the real repository's EXISTS join
        # against tunnel_public_hostnames without a shared session.
        self.hostnames_repo: FakeTunnelHostnameRepository | None = None

    async def get_by_id(self, entity_id: UUID) -> CloudflareTunnelRead | None:
        return self._rows.get(entity_id)

    async def list_page(self, limit: int, offset: int) -> tuple[list[CloudflareTunnelRead], int]:
        items = list(self._rows.values())[offset : offset + limit]
        return items, len(self._rows)

    async def list_for_account(self, cloudflare_account_id: UUID) -> list[CloudflareTunnelRead]:
        return [t for t in self._rows.values() if t.cloudflare_account_id == cloudflare_account_id]

    async def list_for_environment_via_hostnames(self, environment_id: UUID) -> list[CloudflareTunnelRead]:
        assert self.hostnames_repo is not None
        tunnel_ids = {
            h.tunnel_id for h in self.hostnames_repo._rows.values() if h.environment_id == environment_id
        }
        return [t for t in self._rows.values() if t.id in tunnel_ids]

    async def create(
        self, *, cloudflare_account_id: UUID, cf_tunnel_id: str, name: str
    ) -> CloudflareTunnelRead:
        tunnel = CloudflareTunnelRead(
            id=uuid4(),
            cloudflare_account_id=cloudflare_account_id,
            cf_tunnel_id=cf_tunnel_id,
            name=name,
            status=TunnelStatus.UNKNOWN,
            last_synced_at=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self._rows[tunnel.id] = tunnel
        return tunnel

    async def get_by_cf_tunnel_id(self, cf_tunnel_id: str) -> CloudflareTunnelRead | None:
        return next((t for t in self._rows.values() if t.cf_tunnel_id == cf_tunnel_id), None)

    async def upsert_from_sync(
        self, *, cloudflare_account_id: UUID, cf_tunnel_id: str, name: str, status, last_synced_at
    ) -> CloudflareTunnelRead:
        existing = await self.get_by_cf_tunnel_id(cf_tunnel_id)
        if existing is None:
            tunnel = CloudflareTunnelRead(
                id=uuid4(),
                cloudflare_account_id=cloudflare_account_id,
                cf_tunnel_id=cf_tunnel_id,
                name=name,
                status=status,
                last_synced_at=last_synced_at,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        else:
            tunnel = existing.model_copy(
                update={
                    "cloudflare_account_id": cloudflare_account_id,
                    "name": name,
                    "status": status,
                    "last_synced_at": last_synced_at,
                }
            )
        self._rows[tunnel.id] = tunnel
        return tunnel

    async def update_status(self, tunnel_id: UUID, *, status, last_synced_at) -> CloudflareTunnelRead:
        existing = self._rows[tunnel_id]
        updated = existing.model_copy(update={"status": status, "last_synced_at": last_synced_at})
        self._rows[tunnel_id] = updated
        return updated

    async def mark_missing_tunnels_down(
        self, *, cloudflare_account_id: UUID, active_cf_tunnel_ids: set[str], synced_at
    ) -> None:
        for tunnel_id, tunnel in list(self._rows.items()):
            if (
                tunnel.cloudflare_account_id == cloudflare_account_id
                and tunnel.cf_tunnel_id not in active_cf_tunnel_ids
            ):
                self._rows[tunnel_id] = tunnel.model_copy(
                    update={"status": TunnelStatus.DOWN, "last_synced_at": synced_at}
                )

    async def delete(self, tunnel_id: UUID) -> None:
        self._rows.pop(tunnel_id, None)


class FakeTunnelHostnameRepository:
    def __init__(self) -> None:
        self._rows: dict[UUID, TunnelPublicHostnameRead] = {}

    async def get_by_id(self, entity_id: UUID) -> TunnelPublicHostnameRead | None:
        return self._rows.get(entity_id)

    async def list_page(self, limit: int, offset: int) -> tuple[list[TunnelPublicHostnameRead], int]:
        items = list(self._rows.values())[offset : offset + limit]
        return items, len(self._rows)

    async def list_for_tunnel(
        self, tunnel_id: UUID, *, environment_id: UUID | None = None
    ) -> list[TunnelPublicHostnameRead]:
        rows = [h for h in self._rows.values() if h.tunnel_id == tunnel_id]
        if environment_id is not None:
            rows = [h for h in rows if h.environment_id == environment_id]
        return rows

    async def create(
        self,
        *,
        tunnel_id: UUID,
        hostname: str,
        service: str,
        created_by: UUID | None,
        environment_id: UUID | None = None,
    ) -> TunnelPublicHostnameRead:
        row = TunnelPublicHostnameRead(
            id=uuid4(),
            tunnel_id=tunnel_id,
            environment_id=environment_id,
            hostname=hostname,
            service=service,
            managed_by=ManagedBy.SYSTEM,
            created_by=created_by,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self._rows[row.id] = row
        return row

    async def update_service(self, hostname_id: UUID, *, service: str) -> TunnelPublicHostnameRead:
        existing = self._rows[hostname_id]
        updated = existing.model_copy(update={"service": service})
        self._rows[hostname_id] = updated
        return updated

    async def delete(self, hostname_id: UUID) -> None:
        self._rows.pop(hostname_id, None)

    async def upsert_from_sync(
        self, *, tunnel_id: UUID, hostname: str, service: str, environment_id: UUID | None, last_synced_at
    ) -> TunnelPublicHostnameRead:
        existing = next((h for h in self._rows.values() if h.hostname == hostname), None)
        if existing is None:
            row = TunnelPublicHostnameRead(
                id=uuid4(),
                tunnel_id=tunnel_id,
                environment_id=environment_id,
                hostname=hostname,
                service=service,
                managed_by=ManagedBy.EXTERNAL,
                created_by=None,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        else:
            # last_synced_at is not exposed on TunnelPublicHostnameRead —
            # accepted here only to mirror the real repository's signature.
            row = existing.model_copy(
                update={
                    "tunnel_id": tunnel_id,
                    "service": service,
                    "environment_id": environment_id,
                }
            )
        self._rows[row.id] = row
        return row

    async def delete_not_in_hostnames(self, tunnel_id: UUID, keep_hostnames: set[str]) -> None:
        for row_id, row in list(self._rows.items()):
            if row.tunnel_id == tunnel_id and row.hostname not in keep_hostnames:
                self._rows.pop(row_id, None)

    async def list_for_environment(self, environment_id: UUID) -> list[TunnelPublicHostnameRead]:
        return [h for h in self._rows.values() if h.environment_id == environment_id]


class FakeCloudflareUnitOfWork(AbstractCloudflareUnitOfWork):
    """In-memory unit of work. commit/rollback are no-ops that just count calls."""

    def __init__(self) -> None:
        self.accounts = FakeCloudflareAccountRepository()
        self.account_managers = FakeCloudflareAccountManagerRepository()
        self.configs = FakeConfigsRepo()
        self.dns_records = FakeDnsRecordsRepo()
        tunnels_repo = FakeCloudflareTunnelRepository()
        hostnames_repo = FakeTunnelHostnameRepository()
        tunnels_repo.hostnames_repo = hostnames_repo
        self.tunnels = tunnels_repo
        self.tunnel_hostnames = hostnames_repo
        self.commits = 0
        self.rollbacks = 0
        self.stale: list[tuple[str, UUID]] = []

    def mark_stale(self, entity: str, entity_id: UUID) -> None:
        self.stale.append((entity, entity_id))

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class FakeCloudflareClient:
    """Duck-typed stand-in for CloudflareClient — configurable to raise or succeed."""

    def __init__(self, raises: Exception | None = None) -> None:
        self._raises = raises
        self.calls: list[tuple[str, str]] = []

    async def test_connection(self, *, cf_account_id: str, api_token: str) -> None:
        self.calls.append((cf_account_id, api_token))
        if self._raises is not None:
            raise self._raises


class FakeClientWithZones(FakeCloudflareClient):
    def __init__(self, zones: list, raises: Exception | None = None) -> None:
        super().__init__(raises=raises)
        self._zones = zones

    async def list_zones(self, *, cf_account_id, api_token):
        if self._raises is not None:
            raise self._raises
        return self._zones


class FakeCloudflareTunnelClient:
    """Fakes only the 6 Tunnel methods — the DNS methods aren't needed by
    these tests, so they're omitted rather than stubbed unused."""

    def __init__(
        self,
        create_tunnel_id: str = "tun-fake",
        token: str = "token-fake",
        connections: list | None = None,
        ingress: list | None = None,
        raises_on_put: Exception | None = None,
    ) -> None:
        self._create_tunnel_id = create_tunnel_id
        self._token = token
        self._connections = connections if connections is not None else []
        self._ingress = ingress if ingress is not None else []
        self._raises_on_put = raises_on_put
        self.deleted_tunnel_ids: list[str] = []
        self.put_calls: list[list[dict]] = []

    async def create_tunnel(self, *, cf_account_id: str, api_token: str, name: str) -> str:
        return self._create_tunnel_id

    async def get_tunnel_token(self, *, cf_account_id: str, cf_tunnel_id: str, api_token: str) -> str:
        return self._token

    async def list_tunnel_connections(self, *, cf_account_id: str, cf_tunnel_id: str, api_token: str) -> list:
        return self._connections

    async def get_tunnel_configuration(
        self, *, cf_account_id: str, cf_tunnel_id: str, api_token: str
    ) -> list:
        return self._ingress

    async def put_tunnel_configuration(
        self, *, cf_account_id: str, cf_tunnel_id: str, api_token: str, ingress: list[dict]
    ) -> None:
        self.put_calls.append(ingress)
        if self._raises_on_put is not None:
            raise self._raises_on_put

    async def delete_tunnel(self, *, cf_account_id: str, cf_tunnel_id: str, api_token: str) -> None:
        self.deleted_tunnel_ids.append(cf_tunnel_id)


class FakeCacheClient:
    """Fakes only try_acquire_lock/release_lock — the 3 hostname-mutation
    services never call any other CacheClient method."""

    def __init__(self, raises: Exception | None = None) -> None:
        self._locked: set[str] = set()
        self._raises = raises
        self.released_keys: list[str] = []

    async def try_acquire_lock(self, key: str, *, ttl: int) -> bool:
        if self._raises is not None:
            raise self._raises
        if key in self._locked:
            return False
        self._locked.add(key)
        return True

    async def release_lock(self, key: str) -> None:
        self._locked.discard(key)
        self.released_keys.append(key)


class FakeProjectsApi:
    def __init__(self, environments: dict) -> None:
        self._environments = environments

    async def get_environment_by_id(self, environment_id):
        return self._environments.get(environment_id)


class FakeAuditApi:
    """Duck-typed stand-in for app.modules.audit.public.AuditApi — records every
    call instead of writing to Mongo, so tests can assert an event was logged."""

    def __init__(self) -> None:
        self.events: list[dict] = []

    async def log_event(self, **kwargs) -> None:
        self.events.append(kwargs)

    async def list_logs(self, **kwargs) -> tuple[list, int]:
        return [], 0


ACTOR_ID = uuid4()
ACTOR_EMAIL = "actor@example.com"
TEST_FERNET_KEY = "kL8Zx3vQ9mN2pR7wT4yU6bC1dF5gH0jK3lM6nO9pQ2s="


@pytest.fixture(autouse=True)
def _cloudflare_fernet_key(monkeypatch) -> None:
    """Every test in this file that encrypts/decrypts a token needs a real
    32-byte Fernet key — the module's own default is "" (fail-fast, per
    CloudflareConfig's docstring convention), which Fernet() rejects outright."""
    monkeypatch.setattr(cloudflare_settings, "FERNET_KEY", TEST_FERNET_KEY)


class TestCreateCloudflareAccount:
    async def test_creates_account_and_assigns_creator_as_owner(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        client = FakeCloudflareClient()
        audit_api = FakeAuditApi()

        account = await CreateCloudflareAccount(uow, client, audit_api).execute(
            "CF - Customer A", "cf-acc-1", "real-token", actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
        )

        assert account.label == "CF - Customer A"
        manager = await uow.account_managers.get_for_user(account.id, ACTOR_ID)
        assert manager is not None
        assert manager.access_level is AccessLevel.OWNER
        assert client.calls == [("cf-acc-1", "real-token")]
        assert uow.commits == 1
        assert audit_api.events[0]["action"] == CloudflareAccountAuditActions.ACCOUNT_CREATED

    async def test_stores_token_as_ciphertext_not_plaintext(self) -> None:
        uow = FakeCloudflareUnitOfWork()

        account = await CreateCloudflareAccount(uow, FakeCloudflareClient(), FakeAuditApi()).execute(
            "CF - Customer A", "cf-acc-1", "super-secret-token", actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
        )

        stored = await uow.accounts.get_token_ciphertext(account.id)
        assert stored != "super-secret-token"

    async def test_rejects_bad_token_before_persisting_anything(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        client = FakeCloudflareClient(raises=InvalidCloudflareToken())

        with pytest.raises(InvalidCloudflareToken):
            await CreateCloudflareAccount(uow, client, FakeAuditApi()).execute(
                "CF - Bad", "cf-acc-2", "bad-token", actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
            )

        assert uow.commits == 0
        items, total = await uow.accounts.list_page(50, 0)
        assert total == 0

    async def test_rejects_unreachable_cloudflare_before_persisting_anything(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        client = FakeCloudflareClient(raises=CfUnavailable())

        with pytest.raises(CfUnavailable):
            await CreateCloudflareAccount(uow, client, FakeAuditApi()).execute(
                "CF - Down", "cf-acc-3", "x", actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
            )

        assert uow.commits == 0


def _grant(held_level: AccessLevel | None) -> AccountAccessGrant:
    return AccountAccessGrant(user=UserRead.model_construct(id=ACTOR_ID), held_level=held_level)


class TestUpdateCloudflareAccount:
    async def test_editor_can_rename_label(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="Old", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )

        updated = await UpdateCloudflareAccount(uow, FakeCloudflareClient(), FakeAuditApi()).execute(
            account.id,
            label="New",
            api_token=None,
            grant=_grant(AccessLevel.EDITOR),
            actor_email=ACTOR_EMAIL,
        )

        assert updated.label == "New"
        assert uow.commits == 1

    async def test_editor_cannot_rotate_token(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="Old", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )

        with pytest.raises(InsufficientAccountAccess):
            await UpdateCloudflareAccount(uow, FakeCloudflareClient(), FakeAuditApi()).execute(
                account.id,
                label=None,
                api_token="new-token",
                grant=_grant(AccessLevel.EDITOR),
                actor_email=ACTOR_EMAIL,
            )

        assert uow.commits == 0

    async def test_owner_can_rotate_token(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="Old", cf_account_id="cf-1", api_token="old-ciphertext", created_by=ACTOR_ID
        )
        client = FakeCloudflareClient()

        await UpdateCloudflareAccount(uow, client, FakeAuditApi()).execute(
            account.id,
            label=None,
            api_token="new-plaintext-token",
            grant=_grant(AccessLevel.OWNER),
            actor_email=ACTOR_EMAIL,
        )

        assert client.calls == [("cf-1", "new-plaintext-token")]
        stored = await uow.accounts.get_token_ciphertext(account.id)
        assert stored != "new-plaintext-token"
        assert stored != "old-ciphertext"

    async def test_manage_all_bypass_can_rotate_token(self) -> None:
        """held_level=None (manage_all bypass) satisfies OWNER too."""
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="Old", cf_account_id="cf-1", api_token="old-ciphertext", created_by=ACTOR_ID
        )

        await UpdateCloudflareAccount(uow, FakeCloudflareClient(), FakeAuditApi()).execute(
            account.id,
            label=None,
            api_token="rotated",
            grant=_grant(None),
            actor_email=ACTOR_EMAIL,
        )

        assert uow.commits == 1

    async def test_rejects_bad_rotated_token_before_persisting(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="Old", cf_account_id="cf-1", api_token="old-ciphertext", created_by=ACTOR_ID
        )
        client = FakeCloudflareClient(raises=InvalidCloudflareToken())

        with pytest.raises(InvalidCloudflareToken):
            await UpdateCloudflareAccount(uow, client, FakeAuditApi()).execute(
                account.id,
                label=None,
                api_token="bad-token",
                grant=_grant(AccessLevel.OWNER),
                actor_email=ACTOR_EMAIL,
            )

        assert uow.commits == 0
        stored = await uow.accounts.get_token_ciphertext(account.id)
        assert stored == "old-ciphertext"

    async def test_rejects_unknown_account(self) -> None:
        uow = FakeCloudflareUnitOfWork()

        with pytest.raises(CloudflareAccountNotFound):
            await UpdateCloudflareAccount(uow, FakeCloudflareClient(), FakeAuditApi()).execute(
                uuid4(), label="X", api_token=None, grant=_grant(AccessLevel.OWNER), actor_email=ACTOR_EMAIL
            )


class TestDeleteCloudflareAccount:
    async def test_deletes_account(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="Gone", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )

        await DeleteCloudflareAccount(uow, FakeAuditApi()).execute(
            account.id, actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
        )

        assert await uow.accounts.get_by_id(account.id) is None
        assert uow.commits == 1

    async def test_rejects_unknown_account(self) -> None:
        uow = FakeCloudflareUnitOfWork()

        with pytest.raises(CloudflareAccountNotFound):
            await DeleteCloudflareAccount(uow, FakeAuditApi()).execute(
                uuid4(), actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
            )

        assert uow.commits == 0


class TestTestCloudflareAccountConnection:
    async def test_calls_client_with_decrypted_token(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        ciphertext = FernetCodec.encrypt("plain-token", key=TEST_FERNET_KEY)
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token=ciphertext, created_by=ACTOR_ID
        )
        client = FakeCloudflareClient()

        await TestCloudflareAccountConnection(uow, client).execute(account.id)

        assert client.calls == [("cf-1", "plain-token")]

    async def test_rejects_unknown_account(self) -> None:
        uow = FakeCloudflareUnitOfWork()

        with pytest.raises(CloudflareAccountNotFound):
            await TestCloudflareAccountConnection(uow, FakeCloudflareClient()).execute(uuid4())


class TestRevealCloudflareAccountToken:
    async def test_returns_decrypted_token_and_audits_without_leaking_it(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        ciphertext = FernetCodec.encrypt("super-secret", key=TEST_FERNET_KEY)
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token=ciphertext, created_by=ACTOR_ID
        )
        audit_api = FakeAuditApi()

        revealed = await RevealCloudflareAccountToken(uow, audit_api).execute(
            account.id, actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
        )

        assert revealed == "super-secret"
        event = audit_api.events[0]
        assert event["action"] == CloudflareAccountAuditActions.TOKEN_REVEALED
        assert "super-secret" not in str(event)

    async def test_rejects_unknown_account(self) -> None:
        uow = FakeCloudflareUnitOfWork()

        with pytest.raises(CloudflareAccountNotFound):
            await RevealCloudflareAccountToken(uow, FakeAuditApi()).execute(
                uuid4(), actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
            )


class FakeUsersApi:
    """Duck-typed stand-in for app.modules.users.public.UsersApi."""

    def __init__(self, users: dict[UUID, object]) -> None:
        self._users = users

    async def get_user_by_id(self, user_id: UUID):
        return self._users.get(user_id)


class TestListCloudflareAccountManagers:
    async def test_lists_managers_enriched_with_user_info(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )
        await uow.account_managers.upsert(account.id, ACTOR_ID, AccessLevel.OWNER)
        user = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL, name="Actor")
        users_api = FakeUsersApi({ACTOR_ID: user})

        managers = await ListCloudflareAccountManagers(uow, users_api).execute(account.id)

        assert len(managers) == 1
        assert managers[0].email == ACTOR_EMAIL
        assert managers[0].access_level is AccessLevel.OWNER

    async def test_skips_a_manager_row_whose_user_was_deleted(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )
        await uow.account_managers.upsert(account.id, ACTOR_ID, AccessLevel.OWNER)
        users_api = FakeUsersApi({})  # ACTOR_ID resolves to None

        managers = await ListCloudflareAccountManagers(uow, users_api).execute(account.id)

        assert managers == []

    async def test_rejects_unknown_account(self) -> None:
        uow = FakeCloudflareUnitOfWork()

        with pytest.raises(CloudflareAccountNotFound):
            await ListCloudflareAccountManagers(uow, FakeUsersApi({})).execute(uuid4())


class TestAssignCloudflareAccountManager:
    async def test_assigns_manager(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )
        target_id = uuid4()

        await AssignCloudflareAccountManager(uow, FakeAuditApi()).execute(
            account.id, target_id, AccessLevel.VIEWER, actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
        )

        row = await uow.account_managers.get_for_user(account.id, target_id)
        assert row is not None
        assert row.access_level is AccessLevel.VIEWER
        assert uow.commits == 1

    async def test_rejects_unknown_account(self) -> None:
        uow = FakeCloudflareUnitOfWork()

        with pytest.raises(CloudflareAccountNotFound):
            await AssignCloudflareAccountManager(uow, FakeAuditApi()).execute(
                uuid4(), uuid4(), AccessLevel.VIEWER, actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
            )


class TestUpdateCloudflareAccountManager:
    async def test_changes_access_level(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )
        target_id = uuid4()
        await uow.account_managers.upsert(account.id, target_id, AccessLevel.VIEWER)

        await UpdateCloudflareAccountManager(uow, FakeAuditApi()).execute(
            account.id, target_id, AccessLevel.EDITOR, actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
        )

        row = await uow.account_managers.get_for_user(account.id, target_id)
        assert row.access_level is AccessLevel.EDITOR

    async def test_blocks_downgrading_the_last_owner(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )
        await uow.account_managers.upsert(account.id, ACTOR_ID, AccessLevel.OWNER)

        with pytest.raises(LastOwnerRemovalBlocked):
            await UpdateCloudflareAccountManager(uow, FakeAuditApi()).execute(
                account.id, ACTOR_ID, AccessLevel.EDITOR, actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
            )

        row = await uow.account_managers.get_for_user(account.id, ACTOR_ID)
        assert row.access_level is AccessLevel.OWNER

    async def test_allows_downgrading_one_of_two_owners(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )
        second_owner = uuid4()
        await uow.account_managers.upsert(account.id, ACTOR_ID, AccessLevel.OWNER)
        await uow.account_managers.upsert(account.id, second_owner, AccessLevel.OWNER)

        await UpdateCloudflareAccountManager(uow, FakeAuditApi()).execute(
            account.id, ACTOR_ID, AccessLevel.EDITOR, actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
        )

        row = await uow.account_managers.get_for_user(account.id, ACTOR_ID)
        assert row.access_level is AccessLevel.EDITOR

    async def test_rejects_unknown_manager(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )

        with pytest.raises(CloudflareAccountManagerNotFound):
            await UpdateCloudflareAccountManager(uow, FakeAuditApi()).execute(
                account.id, uuid4(), AccessLevel.EDITOR, actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
            )


class TestRemoveCloudflareAccountManager:
    async def test_removes_manager(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )
        target_id = uuid4()
        await uow.account_managers.upsert(account.id, target_id, AccessLevel.VIEWER)

        await RemoveCloudflareAccountManager(uow, FakeAuditApi()).execute(
            account.id, target_id, actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
        )

        assert await uow.account_managers.get_for_user(account.id, target_id) is None

    async def test_blocks_removing_the_last_owner(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )
        await uow.account_managers.upsert(account.id, ACTOR_ID, AccessLevel.OWNER)

        with pytest.raises(LastOwnerRemovalBlocked):
            await RemoveCloudflareAccountManager(uow, FakeAuditApi()).execute(
                account.id, ACTOR_ID, actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
            )

        assert await uow.account_managers.get_for_user(account.id, ACTOR_ID) is not None

    async def test_allows_removing_a_non_owner(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )
        await uow.account_managers.upsert(account.id, ACTOR_ID, AccessLevel.OWNER)
        target_id = uuid4()
        await uow.account_managers.upsert(account.id, target_id, AccessLevel.EDITOR)

        await RemoveCloudflareAccountManager(uow, FakeAuditApi()).execute(
            account.id, target_id, actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
        )

        assert await uow.account_managers.get_for_user(account.id, target_id) is None

    async def test_rejects_unknown_manager(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )

        with pytest.raises(CloudflareAccountManagerNotFound):
            await RemoveCloudflareAccountManager(uow, FakeAuditApi()).execute(
                account.id, uuid4(), actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
            )


class FakeRbacApi:
    """Duck-typed stand-in for app.modules.rbac.public.RbacApi — only the one
    method this module's services actually call."""

    def __init__(self, *, manage_all: bool) -> None:
        self._manage_all = manage_all

    async def has_permission(self, user_id, resource, action) -> bool:
        return self._manage_all


class TestListVisibleCloudflareAccounts:
    async def test_manage_all_sees_every_account(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        await uow.accounts.create(label="A", cf_account_id="cf-1", api_token="x", created_by=ACTOR_ID)
        await uow.accounts.create(label="B", cf_account_id="cf-2", api_token="x", created_by=ACTOR_ID)

        accounts = await ListVisibleCloudflareAccounts(uow, FakeRbacApi(manage_all=True)).execute(uuid4())

        assert {a.label for a in accounts} == {"A", "B"}

    async def test_regular_user_sees_only_managed_accounts(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        visible = await uow.accounts.create(
            label="Visible", cf_account_id="cf-1", api_token="x", created_by=ACTOR_ID
        )
        await uow.accounts.create(label="Hidden", cf_account_id="cf-2", api_token="x", created_by=ACTOR_ID)
        await uow.account_managers.upsert(visible.id, ACTOR_ID, AccessLevel.VIEWER)

        accounts = await ListVisibleCloudflareAccounts(uow, FakeRbacApi(manage_all=False)).execute(ACTOR_ID)

        assert [a.label for a in accounts] == ["Visible"]

    async def test_user_with_no_relationship_sees_nothing(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        await uow.accounts.create(label="A", cf_account_id="cf-1", api_token="x", created_by=ACTOR_ID)

        accounts = await ListVisibleCloudflareAccounts(uow, FakeRbacApi(manage_all=False)).execute(uuid4())

        assert accounts == []

    async def test_manage_all_sees_accounts_beyond_a_single_page(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        for index in range(1001):
            await uow.accounts.create(
                label=f"A{index}", cf_account_id=f"cf-{index}", api_token="x", created_by=ACTOR_ID
            )

        accounts = await ListVisibleCloudflareAccounts(uow, FakeRbacApi(manage_all=True)).execute(uuid4())

        assert len(accounts) == 1001


class TestCreateCloudflareConfig:
    async def test_binds_environment_to_verified_zone(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A",
            cf_account_id="cf-1",
            api_token=FernetCodec.encrypt("plain", key=TEST_FERNET_KEY),
            created_by=ACTOR_ID,
        )
        await uow.account_managers.upsert(account.id, ACTOR_ID, AccessLevel.OWNER)
        env_id = uuid4()
        projects_api = FakeProjectsApi({env_id: object()})
        client = FakeClientWithZones([ZoneOption(id="z1", name="verified-name.com")])
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        config = await CreateCloudflareConfig(
            uow, client, FakeRbacApi(manage_all=False), projects_api, FakeAuditApi()
        ).execute(env_id, account.id, "z1", actor=actor)

        assert config.zone_name == "verified-name.com"
        assert config.zone_id == "z1"

    async def test_rejects_zone_not_owned_by_account(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A",
            cf_account_id="cf-1",
            api_token=FernetCodec.encrypt("plain", key=TEST_FERNET_KEY),
            created_by=ACTOR_ID,
        )
        await uow.account_managers.upsert(account.id, ACTOR_ID, AccessLevel.OWNER)
        env_id = uuid4()
        projects_api = FakeProjectsApi({env_id: object()})
        client = FakeClientWithZones([ZoneOption(id="other-zone", name="not-this.com")])
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        with pytest.raises(ZoneNotOwnedByAccount):
            await CreateCloudflareConfig(
                uow, client, FakeRbacApi(manage_all=False), projects_api, FakeAuditApi()
            ).execute(env_id, account.id, "spoofed-zone-id", actor=actor)

        assert uow.commits == 0

    async def test_rejects_unknown_environment(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )
        await uow.account_managers.upsert(account.id, ACTOR_ID, AccessLevel.OWNER)
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        with pytest.raises(CloudflareEnvironmentNotFound):
            await CreateCloudflareConfig(
                uow,
                FakeClientWithZones([]),
                FakeRbacApi(manage_all=False),
                FakeProjectsApi({}),
                FakeAuditApi(),
            ).execute(uuid4(), account.id, "z1", actor=actor)

    async def test_rejects_double_binding(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A",
            cf_account_id="cf-1",
            api_token=FernetCodec.encrypt("plain", key=TEST_FERNET_KEY),
            created_by=ACTOR_ID,
        )
        await uow.account_managers.upsert(account.id, ACTOR_ID, AccessLevel.OWNER)
        env_id = uuid4()
        projects_api = FakeProjectsApi({env_id: object()})
        client = FakeClientWithZones([ZoneOption(id="z1", name="a.com")])
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)
        await CreateCloudflareConfig(
            uow, client, FakeRbacApi(manage_all=False), projects_api, FakeAuditApi()
        ).execute(env_id, account.id, "z1", actor=actor)

        with pytest.raises(CloudflareConfigAlreadyExists):
            await CreateCloudflareConfig(
                uow, client, FakeRbacApi(manage_all=False), projects_api, FakeAuditApi()
            ).execute(env_id, account.id, "z1", actor=actor)

    async def test_rejects_insufficient_access(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )
        # No manager row for ACTOR_ID on this account, and no manage_all.
        env_id = uuid4()
        projects_api = FakeProjectsApi({env_id: object()})
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        with pytest.raises(InsufficientAccountAccess):
            await CreateCloudflareConfig(
                uow, FakeClientWithZones([]), FakeRbacApi(manage_all=False), projects_api, FakeAuditApi()
            ).execute(env_id, account.id, "z1", actor=actor)


class TestUpdateCloudflareConfig:
    async def test_rebinds_to_a_different_zone(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A",
            cf_account_id="cf-1",
            api_token=FernetCodec.encrypt("plain", key=TEST_FERNET_KEY),
            created_by=ACTOR_ID,
        )
        env_id = uuid4()
        await uow.configs.create(
            environment_id=env_id, cloudflare_account_id=account.id, zone_id="old-zone", zone_name="old.com"
        )
        client = FakeClientWithZones([ZoneOption(id="new-zone", name="new.com")])

        updated = await UpdateCloudflareConfig(uow, client, FakeAuditApi()).execute(
            env_id, "new-zone", actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
        )

        assert updated.zone_id == "new-zone"
        assert updated.zone_name == "new.com"

    async def test_rejects_zone_not_owned_by_account(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A",
            cf_account_id="cf-1",
            api_token=FernetCodec.encrypt("plain", key=TEST_FERNET_KEY),
            created_by=ACTOR_ID,
        )
        env_id = uuid4()
        await uow.configs.create(
            environment_id=env_id, cloudflare_account_id=account.id, zone_id="old-zone", zone_name="old.com"
        )
        client = FakeClientWithZones([ZoneOption(id="other-zone", name="other.com")])

        with pytest.raises(ZoneNotOwnedByAccount):
            await UpdateCloudflareConfig(uow, client, FakeAuditApi()).execute(
                env_id, "spoofed", actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
            )

    async def test_rejects_unbound_environment(self) -> None:
        uow = FakeCloudflareUnitOfWork()

        with pytest.raises(CloudflareConfigNotFound):
            await UpdateCloudflareConfig(uow, FakeClientWithZones([]), FakeAuditApi()).execute(
                uuid4(), "z1", actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
            )


class FakeDnsRecordsRepoEmpty:
    async def list_for_environment(self, environment_id):
        return []


class FakeDnsRecordsRepoNonEmpty:
    async def list_for_environment(self, environment_id):
        return [object()]


class TestDeleteCloudflareConfig:
    async def test_deletes_when_no_dns_records_exist(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        uow.dns_records = FakeDnsRecordsRepoEmpty()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )
        env_id = uuid4()
        await uow.configs.create(
            environment_id=env_id, cloudflare_account_id=account.id, zone_id="z1", zone_name="a.com"
        )

        await DeleteCloudflareConfig(uow, FakeAuditApi()).execute(
            env_id, actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
        )

        assert await uow.configs.get_by_environment_id(env_id) is None

    async def test_blocks_delete_when_dns_records_exist(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        uow.dns_records = FakeDnsRecordsRepoNonEmpty()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )
        env_id = uuid4()
        await uow.configs.create(
            environment_id=env_id, cloudflare_account_id=account.id, zone_id="z1", zone_name="a.com"
        )

        with pytest.raises(DnsRecordsExistForConfig):
            await DeleteCloudflareConfig(uow, FakeAuditApi()).execute(
                env_id, actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
            )

        assert await uow.configs.get_by_environment_id(env_id) is not None


class TestListZones:
    async def test_returns_zones_for_account(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        ciphertext = FernetCodec.encrypt("plain-token", key=TEST_FERNET_KEY)
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token=ciphertext, created_by=ACTOR_ID
        )
        client = FakeClientWithZones([ZoneOption(id="z1", name="a.com")])

        zones = await ListZones(uow, client).execute(account.id)

        assert zones == [ZoneOption(id="z1", name="a.com")]

    async def test_rejects_unknown_account(self) -> None:
        uow = FakeCloudflareUnitOfWork()

        with pytest.raises(CloudflareAccountNotFound):
            await ListZones(uow, FakeClientWithZones([])).execute(uuid4())


class TestListDnsRecords:
    async def test_returns_records_for_bound_environment(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )
        env_id = uuid4()
        await uow.configs.create(
            environment_id=env_id, cloudflare_account_id=account.id, zone_id="z1", zone_name="a.com"
        )
        await uow.dns_records.create(
            environment_id=env_id,
            cf_record_id="rec1",
            record_type=DnsRecordType.A,
            name="app",
            content="1.2.3.4",
            priority=None,
            proxied=True,
            ttl=1,
            created_by=ACTOR_ID,
        )

        records = await ListDnsRecords(uow).execute(env_id)

        assert len(records) == 1
        assert records[0].cf_record_id == "rec1"

    async def test_rejects_unbound_environment(self) -> None:
        uow = FakeCloudflareUnitOfWork()

        with pytest.raises(CloudflareConfigNotFound):
            await ListDnsRecords(uow).execute(uuid4())


class FakeDnsClient(FakeCloudflareClient):
    """Extends FakeCloudflareClient with the 3 DNS write methods, each
    independently configurable to raise."""

    def __init__(
        self,
        create_returns: str = "rec-new",
        create_raises: Exception | None = None,
        delete_raises: Exception | None = None,
    ) -> None:
        super().__init__()
        self._create_returns = create_returns
        self._create_raises = create_raises
        self._delete_raises = delete_raises
        self.deleted: list[str] = []

    async def create_dns_record(self, **kwargs) -> str:
        if self._create_raises is not None:
            raise self._create_raises
        return self._create_returns

    async def delete_dns_record(self, *, zone_id, cf_record_id, api_token) -> None:
        if self._delete_raises is not None:
            raise self._delete_raises
        self.deleted.append(cf_record_id)


class FailingDnsRecordsRepo(FakeDnsRecordsRepo):
    """Every create() call raises, simulating a local DB failure AFTER
    Cloudflare already accepted the write."""

    async def create(self, **kwargs):
        raise RuntimeError("simulated DB failure")


def _assert_first_critical_log_carries_exception(caplog: pytest.LogCaptureFixture) -> None:
    """The first CRITICAL record is the failed local write. The use case
    re-raises `from None`, so this record is the only place its cause survives."""
    critical = [record for record in caplog.records if record.levelno == logging.CRITICAL]
    assert critical, "expected a CRITICAL log for the failed local write"
    assert critical[0].exc_info is not None


class TestCreateDnsRecord:
    async def test_creates_record_with_real_cf_record_id(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A",
            cf_account_id="cf-1",
            api_token=FernetCodec.encrypt("plain", key=TEST_FERNET_KEY),
            created_by=ACTOR_ID,
        )
        env_id = uuid4()
        await uow.configs.create(
            environment_id=env_id, cloudflare_account_id=account.id, zone_id="z1", zone_name="a.com"
        )
        client = FakeDnsClient(create_returns="rec-new")
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        record = await CreateDnsRecord(uow, client, FakeAuditApi()).execute(
            env_id, DnsRecordType.A, "app", "1.2.3.4", None, True, 1, actor=actor
        )

        assert record.cf_record_id == "rec-new"
        assert record.managed_by == ManagedBy.SYSTEM

    async def test_mx_without_priority_raises_before_calling_cloudflare(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A",
            cf_account_id="cf-1",
            api_token=FernetCodec.encrypt("plain", key=TEST_FERNET_KEY),
            created_by=ACTOR_ID,
        )
        env_id = uuid4()
        await uow.configs.create(
            environment_id=env_id, cloudflare_account_id=account.id, zone_id="z1", zone_name="a.com"
        )
        client = FakeDnsClient()
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        with pytest.raises(MissingDnsRecordPriority):
            await CreateDnsRecord(uow, client, FakeAuditApi()).execute(
                env_id, DnsRecordType.MX, "app", "mail.example.com", None, False, 1, actor=actor
            )

    async def test_local_failure_after_cf_success_attempts_compensating_delete(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        uow = FakeCloudflareUnitOfWork()
        uow.dns_records = FailingDnsRecordsRepo()
        account = await uow.accounts.create(
            label="A",
            cf_account_id="cf-1",
            api_token=FernetCodec.encrypt("plain", key=TEST_FERNET_KEY),
            created_by=ACTOR_ID,
        )
        env_id = uuid4()
        await uow.configs.create(
            environment_id=env_id, cloudflare_account_id=account.id, zone_id="z1", zone_name="a.com"
        )
        client = FakeDnsClient(create_returns="rec-orphan-risk")
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        with pytest.raises(DnsRecordSyncFailed):
            await CreateDnsRecord(uow, client, FakeAuditApi()).execute(
                env_id, DnsRecordType.A, "app", "1.2.3.4", None, False, 1, actor=actor
            )

        _assert_first_critical_log_carries_exception(caplog)

        assert client.deleted == ["rec-orphan-risk"]

    async def test_rejects_unbound_environment(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        with pytest.raises(CloudflareConfigNotFound):
            await CreateDnsRecord(uow, FakeDnsClient(), FakeAuditApi()).execute(
                uuid4(), DnsRecordType.A, "app", "1.2.3.4", None, False, 1, actor=actor
            )


class FakeDnsClientForUpdate(FakeCloudflareClient):
    def __init__(self, update_raises: Exception | None = None) -> None:
        super().__init__()
        self._update_raises = update_raises
        self.update_calls: list[dict] = []

    async def update_dns_record(self, **kwargs) -> None:
        if self._update_raises is not None:
            raise self._update_raises
        self.update_calls.append(kwargs)


class FailingUpdateDnsRecordsRepo(FakeDnsRecordsRepo):
    async def update(self, record_id, **kwargs):
        raise RuntimeError("simulated DB failure")


class TestUpdateDnsRecord:
    async def test_updates_content_and_ttl(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A",
            cf_account_id="cf-1",
            api_token=FernetCodec.encrypt("plain", key=TEST_FERNET_KEY),
            created_by=ACTOR_ID,
        )
        env_id = uuid4()
        await uow.configs.create(
            environment_id=env_id, cloudflare_account_id=account.id, zone_id="z1", zone_name="a.com"
        )
        existing = await uow.dns_records.create(
            environment_id=env_id,
            cf_record_id="rec1",
            record_type=DnsRecordType.A,
            name="app",
            content="1.2.3.4",
            priority=None,
            proxied=False,
            ttl=1,
            created_by=ACTOR_ID,
        )
        client = FakeDnsClientForUpdate()
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        updated = await UpdateDnsRecord(uow, client, FakeAuditApi()).execute(
            env_id, existing.id, "5.6.7.8", None, True, 300, actor=actor
        )

        assert updated.content == "5.6.7.8"
        assert updated.ttl == 300

    async def test_local_failure_after_cf_success_attempts_compensating_revert(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A",
            cf_account_id="cf-1",
            api_token=FernetCodec.encrypt("plain", key=TEST_FERNET_KEY),
            created_by=ACTOR_ID,
        )
        env_id = uuid4()
        await uow.configs.create(
            environment_id=env_id, cloudflare_account_id=account.id, zone_id="z1", zone_name="a.com"
        )
        existing = await uow.dns_records.create(
            environment_id=env_id,
            cf_record_id="rec1",
            record_type=DnsRecordType.A,
            name="app",
            content="1.2.3.4",
            priority=None,
            proxied=False,
            ttl=1,
            created_by=ACTOR_ID,
        )
        failing_repo = FailingUpdateDnsRecordsRepo()
        failing_repo._rows[existing.id] = existing
        uow.dns_records = failing_repo
        client = FakeDnsClientForUpdate()
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        with pytest.raises(DnsRecordSyncFailed):
            await UpdateDnsRecord(uow, client, FakeAuditApi()).execute(
                env_id, existing.id, "9.9.9.9", None, True, 600, actor=actor
            )

        _assert_first_critical_log_carries_exception(caplog)

        # First call = the real update; second call = the compensating
        # revert back to the original content/ttl.
        assert len(client.update_calls) == 2
        assert client.update_calls[1]["content"] == "1.2.3.4"
        assert client.update_calls[1]["ttl"] == 1

    async def test_rejects_unknown_record(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A",
            cf_account_id="cf-1",
            api_token=FernetCodec.encrypt("plain", key=TEST_FERNET_KEY),
            created_by=ACTOR_ID,
        )
        env_id = uuid4()
        await uow.configs.create(
            environment_id=env_id, cloudflare_account_id=account.id, zone_id="z1", zone_name="a.com"
        )
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        with pytest.raises(DnsRecordNotFound):
            await UpdateDnsRecord(uow, FakeDnsClientForUpdate(), FakeAuditApi()).execute(
                env_id, uuid4(), "x", None, False, 1, actor=actor
            )

    async def test_rejects_record_owned_by_a_different_environment(self) -> None:
        """The actual cross-project-edit fix: a record synced to a sibling
        environment sharing the same zone must 404 for this environment's
        caller, not succeed silently."""
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A",
            cf_account_id="cf-1",
            api_token=FernetCodec.encrypt("plain", key=TEST_FERNET_KEY),
            created_by=ACTOR_ID,
        )
        env_id, other_env_id = uuid4(), uuid4()
        await uow.configs.create(
            environment_id=env_id, cloudflare_account_id=account.id, zone_id="z1", zone_name="a.com"
        )
        other_record = await uow.dns_records.create(
            environment_id=other_env_id,
            cf_record_id="rec-other",
            record_type=DnsRecordType.A,
            name="backend",
            content="1.2.3.4",
            priority=None,
            proxied=False,
            ttl=1,
            created_by=ACTOR_ID,
        )
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        with pytest.raises(DnsRecordNotFound):
            await UpdateDnsRecord(uow, FakeDnsClientForUpdate(), FakeAuditApi()).execute(
                env_id, other_record.id, "9.9.9.9", None, False, 1, actor=actor
            )


class FakeDnsClientForDelete(FakeCloudflareClient):
    def __init__(self) -> None:
        super().__init__()
        self.deleted: list[str] = []

    async def delete_dns_record(self, *, zone_id, cf_record_id, api_token) -> None:
        self.deleted.append(cf_record_id)


class FailingDeleteDnsRecordsRepo(FakeDnsRecordsRepo):
    async def delete(self, record_id):
        raise RuntimeError("simulated DB failure")


class TestDeleteDnsRecord:
    async def test_deletes_record(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A",
            cf_account_id="cf-1",
            api_token=FernetCodec.encrypt("plain", key=TEST_FERNET_KEY),
            created_by=ACTOR_ID,
        )
        env_id = uuid4()
        await uow.configs.create(
            environment_id=env_id, cloudflare_account_id=account.id, zone_id="z1", zone_name="a.com"
        )
        existing = await uow.dns_records.create(
            environment_id=env_id,
            cf_record_id="rec1",
            record_type=DnsRecordType.A,
            name="app",
            content="1.2.3.4",
            priority=None,
            proxied=False,
            ttl=1,
            created_by=ACTOR_ID,
        )
        client = FakeDnsClientForDelete()
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        await DeleteDnsRecord(uow, client, FakeAuditApi()).execute(env_id, existing.id, actor=actor)

        assert client.deleted == ["rec1"]
        assert await uow.dns_records.get_by_id(existing.id) is None

    async def test_local_failure_after_cf_delete_succeeds_raises_sync_failed(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A",
            cf_account_id="cf-1",
            api_token=FernetCodec.encrypt("plain", key=TEST_FERNET_KEY),
            created_by=ACTOR_ID,
        )
        env_id = uuid4()
        await uow.configs.create(
            environment_id=env_id, cloudflare_account_id=account.id, zone_id="z1", zone_name="a.com"
        )
        existing = await uow.dns_records.create(
            environment_id=env_id,
            cf_record_id="rec1",
            record_type=DnsRecordType.A,
            name="app",
            content="1.2.3.4",
            priority=None,
            proxied=False,
            ttl=1,
            created_by=ACTOR_ID,
        )
        failing_repo = FailingDeleteDnsRecordsRepo()
        failing_repo._rows[existing.id] = existing
        uow.dns_records = failing_repo
        client = FakeDnsClientForDelete()
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        with pytest.raises(DnsRecordSyncFailed):
            await DeleteDnsRecord(uow, client, FakeAuditApi()).execute(env_id, existing.id, actor=actor)

        _assert_first_critical_log_carries_exception(caplog)

        # Cloudflare's side really is deleted — no compensating action exists.
        assert client.deleted == ["rec1"]

    async def test_rejects_unknown_record(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A",
            cf_account_id="cf-1",
            api_token=FernetCodec.encrypt("plain", key=TEST_FERNET_KEY),
            created_by=ACTOR_ID,
        )
        env_id = uuid4()
        await uow.configs.create(
            environment_id=env_id, cloudflare_account_id=account.id, zone_id="z1", zone_name="a.com"
        )
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        with pytest.raises(DnsRecordNotFound):
            await DeleteDnsRecord(uow, FakeDnsClientForDelete(), FakeAuditApi()).execute(
                env_id, uuid4(), actor=actor
            )

    async def test_rejects_record_owned_by_a_different_environment(self) -> None:
        """The actual cross-project-delete fix: a record synced to a sibling
        environment sharing the same zone must 404 for this environment's
        caller, not succeed silently."""
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A",
            cf_account_id="cf-1",
            api_token=FernetCodec.encrypt("plain", key=TEST_FERNET_KEY),
            created_by=ACTOR_ID,
        )
        env_id, other_env_id = uuid4(), uuid4()
        await uow.configs.create(
            environment_id=env_id, cloudflare_account_id=account.id, zone_id="z1", zone_name="a.com"
        )
        other_record = await uow.dns_records.create(
            environment_id=other_env_id,
            cf_record_id="rec-other",
            record_type=DnsRecordType.A,
            name="backend",
            content="1.2.3.4",
            priority=None,
            proxied=False,
            ttl=1,
            created_by=ACTOR_ID,
        )
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)
        client = FakeDnsClientForDelete()

        with pytest.raises(DnsRecordNotFound):
            await DeleteDnsRecord(uow, client, FakeAuditApi()).execute(env_id, other_record.id, actor=actor)
        # Never even attempted the Cloudflare call for a record this
        # environment doesn't own.
        assert client.deleted == []


class FakeDnsSyncClient(FakeCloudflareClient):
    """Fakes only list_dns_records — the one Cloudflare call SyncDnsRecords
    makes."""

    def __init__(self, records: list[dict]) -> None:
        super().__init__()
        self._records = records

    async def list_dns_records(self, *, zone_id, api_token):
        return self._records


class TestSyncDnsRecords:
    async def _setup(self, *, sibling_base_urls: dict[UUID, str | None] | None = None, cf_records=None):
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="acc",
            cf_account_id="cf-1",
            api_token=FernetCodec.encrypt("tok", key=TEST_FERNET_KEY),
            created_by=None,
        )
        triggering_env_id = uuid4()
        await uow.configs.create(
            environment_id=triggering_env_id,
            cloudflare_account_id=account.id,
            zone_id="shared-zone",
            zone_name="agentsplatform.cloud",
        )
        environments: dict = {}
        if sibling_base_urls:
            for sibling_id, base_url in sibling_base_urls.items():
                await uow.configs.create(
                    environment_id=sibling_id,
                    cloudflare_account_id=account.id,
                    zone_id="shared-zone",
                    zone_name="agentsplatform.cloud",
                )
                environments[sibling_id] = SimpleNamespace(id=sibling_id, base_url=base_url)
        projects_api = FakeProjectsApi(environments)
        client = FakeDnsSyncClient(cf_records or [])
        return uow, triggering_env_id, projects_api, client

    async def test_attributes_each_sibling_environments_own_records_correctly(self) -> None:
        """The literal regression test for the bug: two environments sharing
        one zone, sync triggered from one, records correctly split between
        both rather than all claimed by whichever synced."""
        agent_mkt_id, itsm_id = uuid4(), uuid4()
        cf_records = [
            {
                "id": "rec-agent-mkt",
                "type": "A",
                "name": "agent-mkt.agentsplatform.cloud",
                "content": "1.1.1.1",
            },
            {"id": "rec-itsm", "type": "A", "name": "itsm.agentsplatform.cloud", "content": "2.2.2.2"},
        ]
        uow, triggering_env_id, projects_api, client = await self._setup(
            sibling_base_urls={
                agent_mkt_id: "https://agent-mkt.agentsplatform.cloud",
                itsm_id: "https://itsm.agentsplatform.cloud",
            },
            cf_records=cf_records,
        )

        await SyncDnsRecords(uow, client, projects_api).execute(triggering_env_id)

        agent_mkt_records = await uow.dns_records.list_for_environment(agent_mkt_id)
        itsm_records = await uow.dns_records.list_for_environment(itsm_id)
        assert [r.cf_record_id for r in agent_mkt_records] == ["rec-agent-mkt"]
        assert [r.cf_record_id for r in itsm_records] == ["rec-itsm"]

    async def test_record_matching_no_environment_gets_none(self) -> None:
        agent_mkt_id = uuid4()
        cf_records = [
            {"id": "rec-backend", "type": "CNAME", "name": "backend.agentsplatform.cloud", "content": "x"},
        ]
        uow, triggering_env_id, projects_api, client = await self._setup(
            sibling_base_urls={agent_mkt_id: "https://agent-mkt.agentsplatform.cloud"},
            cf_records=cf_records,
        )

        await SyncDnsRecords(uow, client, projects_api).execute(triggering_env_id)

        assert await uow.dns_records.list_for_environment(agent_mkt_id) == []
        assert await uow.dns_records.list_for_environment(triggering_env_id) == []
        unmatched = [r for r in uow.dns_records._rows.values() if r.cf_record_id == "rec-backend"]
        assert len(unmatched) == 1
        assert unmatched[0].environment_id is None

    async def test_system_record_attribution_is_never_overwritten_by_matching(self) -> None:
        """A record CreateDnsRecord deliberately attributed to an
        environment must survive a sync even if its name doesn't exactly
        equal that environment's base_url (e.g. an "api." subdomain)."""
        uow, triggering_env_id, projects_api, client = await self._setup(
            cf_records=[
                {
                    "id": "rec-api",
                    "type": "A",
                    "name": "api.agent-mkt.agentsplatform.cloud",
                    "content": "9.9.9.9",
                }
            ],
        )
        await uow.dns_records.create(
            environment_id=triggering_env_id,
            cf_record_id="rec-api",
            record_type=DnsRecordType.A,
            name="api.agent-mkt.agentsplatform.cloud",
            content="1.2.3.4",
            priority=None,
            proxied=False,
            ttl=1,
            created_by=ACTOR_ID,
        )

        await SyncDnsRecords(uow, client, projects_api).execute(triggering_env_id)

        records = await uow.dns_records.list_for_environment(triggering_env_id)
        assert [r.cf_record_id for r in records] == ["rec-api"]
        assert records[0].managed_by == ManagedBy.SYSTEM
        assert records[0].content == "9.9.9.9"

    async def test_deletes_stale_records_across_the_whole_sibling_set(self) -> None:
        """A sibling's record deleted on Cloudflare gets cleaned up even
        though this pass was triggered by a DIFFERENT sibling. Cloudflare's
        live response is non-empty (one unrelated record present) since
        SyncDnsRecords deliberately skips cleanup entirely on an empty
        response — a guard against wiping every local record on a
        transient empty/error response."""
        sibling_id = uuid4()
        uow, triggering_env_id, projects_api, client = await self._setup(
            sibling_base_urls={sibling_id: "https://agent-mkt.agentsplatform.cloud"},
            cf_records=[
                {"id": "rec-unrelated", "type": "TXT", "name": "unrelated.example.com", "content": "x"}
            ],
        )
        await uow.dns_records.upsert_from_sync(
            environment_id=sibling_id,
            cf_record_id="rec-stale",
            record_type=DnsRecordType.A,
            name="agent-mkt.agentsplatform.cloud",
            content="1.1.1.1",
            priority=None,
            proxied=False,
            ttl=1,
            managed_by=ManagedBy.EXTERNAL,
            last_synced_at=datetime.now(UTC),
        )

        await SyncDnsRecords(uow, client, projects_api).execute(triggering_env_id)

        assert await uow.dns_records.list_for_environment(sibling_id) == []


class TestCreateCloudflareTunnel:
    async def test_creates_tunnel_and_returns_plaintext_token_once(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="acc",
            cf_account_id="cf-1",
            api_token=FernetCodec.encrypt("plaintext-token", key=TEST_FERNET_KEY),
            created_by=None,
        )
        config = await uow.configs.create(
            environment_id=uuid4(), cloudflare_account_id=account.id, zone_id="z1", zone_name="example.com"
        )
        client = FakeCloudflareTunnelClient(create_tunnel_id="tun-1", token="conn-token-xyz")
        use_case = CreateCloudflareTunnel(uow, client, FakeAuditApi())
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        tunnel, token = await use_case.execute(config.environment_id, "prod-tunnel", actor=actor)

        assert tunnel.cf_tunnel_id == "tun-1"
        assert tunnel.status == "unknown"
        assert token == "conn-token-xyz"

    async def test_raises_config_not_found_when_environment_unbound(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        use_case = CreateCloudflareTunnel(uow, FakeCloudflareTunnelClient(), FakeAuditApi())
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        with pytest.raises(CloudflareConfigNotFound):
            await use_case.execute(uuid4(), "prod-tunnel", actor=actor)


class TestDeleteCloudflareTunnel:
    async def test_deletes_on_cloudflare_then_locally_no_hostname_guard(self) -> None:
        """Decision #7: unlike DeleteCloudflareConfig, this does NOT check for
        existing tunnel_public_hostnames rows — CASCADE handles them."""
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="acc",
            cf_account_id="cf-1",
            api_token=FernetCodec.encrypt("tok", key=TEST_FERNET_KEY),
            created_by=None,
        )
        config = await uow.configs.create(
            environment_id=uuid4(), cloudflare_account_id=account.id, zone_id="z1", zone_name="example.com"
        )
        tunnel = await uow.tunnels.create(cloudflare_account_id=account.id, cf_tunnel_id="tun-1", name="t")
        await uow.tunnel_hostnames.create(
            tunnel_id=tunnel.id, hostname="a.example.com", service="http://x", created_by=None
        )
        client = FakeCloudflareTunnelClient()
        use_case = DeleteCloudflareTunnel(uow, client, FakeAuditApi())
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        await use_case.execute(config.environment_id, tunnel.id, actor=actor)

        assert client.deleted_tunnel_ids == ["tun-1"]
        assert await uow.tunnels.get_by_id(tunnel.id) is None

    async def test_raises_not_found_for_tunnel_on_a_different_account(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="acc",
            cf_account_id="cf-1",
            api_token=FernetCodec.encrypt("tok", key=TEST_FERNET_KEY),
            created_by=None,
        )
        config = await uow.configs.create(
            environment_id=uuid4(), cloudflare_account_id=account.id, zone_id="z1", zone_name="example.com"
        )
        other_tunnel = await uow.tunnels.create(cloudflare_account_id=uuid4(), cf_tunnel_id="tun-x", name="x")
        use_case = DeleteCloudflareTunnel(uow, FakeCloudflareTunnelClient(), FakeAuditApi())
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        with pytest.raises(CloudflareTunnelNotFound):
            await use_case.execute(config.environment_id, other_tunnel.id, actor=actor)

    async def test_accepts_tunnel_shared_by_a_sibling_environment_on_the_same_account(self) -> None:
        """The literal regression case this fix targets: a tunnel that was
        originally synced while a DIFFERENT environment triggered the sync
        must still be manageable from any environment sharing the same
        Cloudflare account — ownership is account-scoped, not environment-scoped."""
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="acc",
            cf_account_id="cf-1",
            api_token=FernetCodec.encrypt("tok", key=TEST_FERNET_KEY),
            created_by=None,
        )
        config = await uow.configs.create(
            environment_id=uuid4(), cloudflare_account_id=account.id, zone_id="z1", zone_name="example.com"
        )
        shared_tunnel = await uow.tunnels.create(
            cloudflare_account_id=account.id, cf_tunnel_id="tun-shared", name="shared"
        )
        client = FakeCloudflareTunnelClient()
        use_case = DeleteCloudflareTunnel(uow, client, FakeAuditApi())
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        await use_case.execute(config.environment_id, shared_tunnel.id, actor=actor)

        assert client.deleted_tunnel_ids == ["tun-shared"]


class TestRevealCloudflareTunnelToken:
    async def test_refetches_token_live_never_from_storage(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="acc",
            cf_account_id="cf-1",
            api_token=FernetCodec.encrypt("tok", key=TEST_FERNET_KEY),
            created_by=None,
        )
        config = await uow.configs.create(
            environment_id=uuid4(), cloudflare_account_id=account.id, zone_id="z1", zone_name="example.com"
        )
        tunnel = await uow.tunnels.create(cloudflare_account_id=account.id, cf_tunnel_id="tun-1", name="t")
        client = FakeCloudflareTunnelClient(token="fresh-token-123")
        use_case = RevealCloudflareTunnelToken(uow, client, FakeAuditApi())
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        token = await use_case.execute(config.environment_id, tunnel.id, actor=actor)

        assert token == "fresh-token-123"


class TestRefreshTunnelStatus:
    async def test_zero_connections_is_down(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="acc",
            cf_account_id="cf-1",
            api_token=FernetCodec.encrypt("tok", key=TEST_FERNET_KEY),
            created_by=None,
        )
        config = await uow.configs.create(
            environment_id=uuid4(), cloudflare_account_id=account.id, zone_id="z1", zone_name="example.com"
        )
        tunnel = await uow.tunnels.create(cloudflare_account_id=account.id, cf_tunnel_id="tun-1", name="t")
        client = FakeCloudflareTunnelClient(connections=[])
        use_case = RefreshTunnelStatus(uow, client)

        updated = await use_case.execute(config.environment_id, tunnel.id)

        assert updated.status == "down"
        assert updated.last_synced_at is not None

    async def test_one_or_more_connections_is_healthy(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="acc",
            cf_account_id="cf-1",
            api_token=FernetCodec.encrypt("tok", key=TEST_FERNET_KEY),
            created_by=None,
        )
        config = await uow.configs.create(
            environment_id=uuid4(), cloudflare_account_id=account.id, zone_id="z1", zone_name="example.com"
        )
        tunnel = await uow.tunnels.create(cloudflare_account_id=account.id, cf_tunnel_id="tun-1", name="t")
        client = FakeCloudflareTunnelClient(connections=[{"id": "c1"}, {"id": "c2"}])
        use_case = RefreshTunnelStatus(uow, client)

        updated = await use_case.execute(config.environment_id, tunnel.id)

        assert updated.status == "healthy"


class TestListTunnels:
    async def test_returns_only_tunnels_matched_to_the_environment_via_hostnames(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        environment_id = uuid4()
        other_environment_id = uuid4()
        matched = await uow.tunnels.create(cloudflare_account_id=uuid4(), cf_tunnel_id="tun-a", name="a")
        unmatched = await uow.tunnels.create(cloudflare_account_id=uuid4(), cf_tunnel_id="tun-b", name="b")
        await uow.tunnel_hostnames.create(
            tunnel_id=matched.id,
            hostname="app.example.com",
            service="http://x",
            created_by=None,
            environment_id=environment_id,
        )
        await uow.tunnel_hostnames.create(
            tunnel_id=unmatched.id,
            hostname="other.example.com",
            service="http://y",
            created_by=None,
            environment_id=other_environment_id,
        )
        use_case = ListTunnels(uow)

        tunnels = await use_case.execute(environment_id)

        assert [t.id for t in tunnels] == [matched.id]

    async def test_tunnel_with_no_matched_hostname_never_appears(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        await uow.tunnels.create(cloudflare_account_id=uuid4(), cf_tunnel_id="tun-a", name="a")
        use_case = ListTunnels(uow)

        tunnels = await use_case.execute(uuid4())

        assert tunnels == []


class TestListTunnelHostnames:
    async def test_returns_only_hostnames_matched_to_the_environment(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="acc",
            cf_account_id="cf-1",
            api_token=FernetCodec.encrypt("tok", key=TEST_FERNET_KEY),
            created_by=None,
        )
        config = await uow.configs.create(
            environment_id=uuid4(), cloudflare_account_id=account.id, zone_id="z1", zone_name="example.com"
        )
        other_environment_id = uuid4()
        tunnel = await uow.tunnels.create(cloudflare_account_id=account.id, cf_tunnel_id="tun-1", name="t")
        await uow.tunnel_hostnames.create(
            tunnel_id=tunnel.id,
            hostname="a.example.com",
            service="http://x",
            created_by=None,
            environment_id=config.environment_id,
        )
        await uow.tunnel_hostnames.create(
            tunnel_id=tunnel.id,
            hostname="b.example.com",
            service="http://y",
            created_by=None,
            environment_id=other_environment_id,
        )
        use_case = ListTunnelHostnames(uow)

        hostnames = await use_case.execute(config.environment_id, tunnel.id)

        assert [h.hostname for h in hostnames] == ["a.example.com"]

    async def test_raises_not_found_for_tunnel_on_a_different_account(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="acc",
            cf_account_id="cf-1",
            api_token=FernetCodec.encrypt("tok", key=TEST_FERNET_KEY),
            created_by=None,
        )
        config = await uow.configs.create(
            environment_id=uuid4(), cloudflare_account_id=account.id, zone_id="z1", zone_name="example.com"
        )
        other_tunnel = await uow.tunnels.create(cloudflare_account_id=uuid4(), cf_tunnel_id="tun-1", name="t")
        use_case = ListTunnelHostnames(uow)
        with pytest.raises(CloudflareTunnelNotFound):
            await use_case.execute(config.environment_id, other_tunnel.id)

    async def test_raises_config_not_found_when_environment_unbound(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        tunnel = await uow.tunnels.create(cloudflare_account_id=uuid4(), cf_tunnel_id="tun-1", name="t")
        use_case = ListTunnelHostnames(uow)
        with pytest.raises(CloudflareConfigNotFound):
            await use_case.execute(uuid4(), tunnel.id)


class TestAddTunnelHostname:
    async def _setup(self, *, sibling_base_urls: dict[UUID, str | None] | None = None, **client_kwargs):
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="acc",
            cf_account_id="cf-1",
            api_token=FernetCodec.encrypt("tok", key=TEST_FERNET_KEY),
            created_by=None,
        )
        config = await uow.configs.create(
            environment_id=uuid4(), cloudflare_account_id=account.id, zone_id="z1", zone_name="example.com"
        )
        tunnel = await uow.tunnels.create(cloudflare_account_id=account.id, cf_tunnel_id="tun-1", name="t")
        environments = {config.environment_id: _fake_environment(config.environment_id, None)}
        for env_id, base_url in (sibling_base_urls or {}).items():
            await uow.configs.create(
                environment_id=env_id,
                cloudflare_account_id=account.id,
                zone_id="z1",
                zone_name="example.com",
            )
            environments[env_id] = _fake_environment(env_id, base_url)
        client = FakeCloudflareTunnelClient(**client_kwargs)
        projects_api = FakeProjectsApi(environments)
        return uow, config, tunnel, client, projects_api

    async def test_adds_to_empty_ingress(self) -> None:
        uow, config, tunnel, client, projects_api = await self._setup(ingress=[])
        use_case = AddTunnelHostname(uow, client, FakeCacheClient(), FakeAuditApi(), projects_api)
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        created = await use_case.execute(
            config.environment_id, tunnel.id, "app.example.com", "http://localhost:8080", actor=actor
        )

        assert created.hostname == "app.example.com"
        assert client.put_calls[-1] == [{"hostname": "app.example.com", "service": "http://localhost:8080"}]

    async def test_inserts_before_catch_all_and_preserves_its_unmodeled_fields(self) -> None:
        catch_all = {"service": "http_status:404", "originRequest": {"noTLSVerify": True}}
        uow, config, tunnel, client, projects_api = await self._setup(ingress=[catch_all])
        use_case = AddTunnelHostname(uow, client, FakeCacheClient(), FakeAuditApi(), projects_api)
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        await use_case.execute(
            config.environment_id, tunnel.id, "app.example.com", "http://localhost:8080", actor=actor
        )

        sent = client.put_calls[-1]
        assert sent[0] == {"hostname": "app.example.com", "service": "http://localhost:8080"}
        assert sent[-1] == catch_all

    async def test_preserves_unrelated_existing_rule_unmodeled_fields(self) -> None:
        existing_rule = {"hostname": "other.example.com", "service": "http://y", "path": "/api/*"}
        uow, config, tunnel, client, projects_api = await self._setup(ingress=[existing_rule])
        use_case = AddTunnelHostname(uow, client, FakeCacheClient(), FakeAuditApi(), projects_api)
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        await use_case.execute(
            config.environment_id, tunnel.id, "app.example.com", "http://localhost:8080", actor=actor
        )

        sent = client.put_calls[-1]
        assert existing_rule in sent

    async def test_duplicate_hostname_on_same_tunnel_rejected_before_calling_cloudflare(self) -> None:
        uow, config, tunnel, client, projects_api = await self._setup(ingress=[])
        await uow.tunnel_hostnames.create(
            tunnel_id=tunnel.id, hostname="app.example.com", service="http://old", created_by=None
        )
        use_case = AddTunnelHostname(uow, client, FakeCacheClient(), FakeAuditApi(), projects_api)
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        with pytest.raises(TunnelHostnameAlreadyExists):
            await use_case.execute(
                config.environment_id, tunnel.id, "app.example.com", "http://new", actor=actor
            )
        assert client.put_calls == []

    async def test_hostname_on_wrong_domain_rejected_before_calling_cloudflare(self) -> None:
        uow, config, tunnel, client, projects_api = await self._setup(ingress=[])
        use_case = AddTunnelHostname(uow, client, FakeCacheClient(), FakeAuditApi(), projects_api)
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        with pytest.raises(TunnelHostnameDomainMismatch):
            await use_case.execute(
                config.environment_id, tunnel.id, "app.otherdomain.com", "http://x", actor=actor
            )
        assert client.put_calls == []

    async def test_lock_already_held_raises_config_locked_without_calling_cloudflare(self) -> None:
        uow, config, tunnel, client, projects_api = await self._setup(ingress=[])
        cache = FakeCacheClient()
        await cache.try_acquire_lock(f"lock:tunnel:{tunnel.id}", ttl=5)
        use_case = AddTunnelHostname(uow, client, cache, FakeAuditApi(), projects_api)
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        with pytest.raises(TunnelConfigLocked):
            await use_case.execute(
                config.environment_id, tunnel.id, "app.example.com", "http://x", actor=actor
            )
        assert client.put_calls == []

    async def test_cache_unavailable_propagates_loudly(self) -> None:
        uow, config, tunnel, client, projects_api = await self._setup(ingress=[])
        cache = FakeCacheClient(raises=CacheUnavailable())
        use_case = AddTunnelHostname(uow, client, cache, FakeAuditApi(), projects_api)
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        with pytest.raises(CacheUnavailable):
            await use_case.execute(
                config.environment_id, tunnel.id, "app.example.com", "http://x", actor=actor
            )

    async def test_lock_is_released_after_success(self) -> None:
        uow, config, tunnel, client, projects_api = await self._setup(ingress=[])
        cache = FakeCacheClient()
        use_case = AddTunnelHostname(uow, client, cache, FakeAuditApi(), projects_api)
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        await use_case.execute(config.environment_id, tunnel.id, "app.example.com", "http://x", actor=actor)

        assert cache.released_keys == [f"lock:tunnel:{tunnel.id}"]

    async def test_local_write_failure_triggers_compensating_put_back_and_raises_sync_failed(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        starting_ingress = [{"service": "http_status:404"}]
        uow, config, tunnel, client, projects_api = await self._setup(ingress=starting_ingress)

        class BrokenHostnameRepo:
            async def list_for_tunnel(self, tunnel_id):
                return []

            async def create(self, **kwargs):
                raise RuntimeError("db exploded")

        uow.tunnel_hostnames = BrokenHostnameRepo()
        use_case = AddTunnelHostname(uow, client, FakeCacheClient(), FakeAuditApi(), projects_api)
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        with pytest.raises(TunnelIngressSyncFailed):
            await use_case.execute(
                config.environment_id, tunnel.id, "app.example.com", "http://x", actor=actor
            )

        _assert_first_critical_log_carries_exception(caplog)

        assert client.put_calls[0] == [
            {"hostname": "app.example.com", "service": "http://x"},
            {"service": "http_status:404"},
        ]
        assert client.put_calls[-1] == starting_ingress

    async def test_rejects_hostname_claiming_a_sibling_environments_domain(self) -> None:
        """The escalation guard (D6): a hostname that exactly matches a
        DIFFERENT sibling environment's own base_url must never be created
        from this environment, even though it belongs to the same shared
        zone and Cloudflare would otherwise happily accept it."""
        sibling_id = uuid4()
        uow, config, tunnel, client, projects_api = await self._setup(
            ingress=[], sibling_base_urls={sibling_id: "https://sibling.example.com"}
        )
        use_case = AddTunnelHostname(uow, client, FakeCacheClient(), FakeAuditApi(), projects_api)
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        with pytest.raises(TunnelHostnameEnvironmentMismatch):
            await use_case.execute(
                config.environment_id, tunnel.id, "sibling.example.com", "http://x", actor=actor
            )
        assert client.put_calls == []

    async def test_allows_hostname_matching_its_own_environment(self) -> None:
        uow, config, tunnel, client, projects_api = await self._setup(ingress=[])
        projects_api._environments[config.environment_id] = _fake_environment(
            config.environment_id, "https://app.example.com"
        )
        use_case = AddTunnelHostname(uow, client, FakeCacheClient(), FakeAuditApi(), projects_api)
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        created = await use_case.execute(
            config.environment_id, tunnel.id, "app.example.com", "http://x", actor=actor
        )
        assert created.hostname == "app.example.com"

    async def test_allows_hostname_matching_no_environment(self) -> None:
        """The routine, allowed case — publishing a fresh subdomain with no
        base_url configured for it anywhere must never be rejected."""
        sibling_id = uuid4()
        uow, config, tunnel, client, projects_api = await self._setup(
            ingress=[], sibling_base_urls={sibling_id: "https://sibling.example.com"}
        )
        use_case = AddTunnelHostname(uow, client, FakeCacheClient(), FakeAuditApi(), projects_api)
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        created = await use_case.execute(
            config.environment_id, tunnel.id, "api.example.com", "http://x", actor=actor
        )
        assert created.hostname == "api.example.com"


class TestUpdateTunnelHostname:
    async def _setup_with_hostname(self, existing_rule_extra: dict | None = None):
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="acc",
            cf_account_id="cf-1",
            api_token=FernetCodec.encrypt("tok", key=TEST_FERNET_KEY),
            created_by=None,
        )
        config = await uow.configs.create(
            environment_id=uuid4(), cloudflare_account_id=account.id, zone_id="z1", zone_name="example.com"
        )
        tunnel = await uow.tunnels.create(cloudflare_account_id=account.id, cf_tunnel_id="tun-1", name="t")
        hostname_row = await uow.tunnel_hostnames.create(
            tunnel_id=tunnel.id,
            hostname="app.example.com",
            service="http://old",
            created_by=None,
            environment_id=config.environment_id,
        )
        rule = {"hostname": "app.example.com", "service": "http://old", **(existing_rule_extra or {})}
        client = FakeCloudflareTunnelClient(ingress=[rule])
        return uow, config, tunnel, hostname_row, client

    async def test_updates_service_preserving_unmodeled_fields(self) -> None:
        uow, config, tunnel, hostname_row, client = await self._setup_with_hostname({"path": "/api/*"})
        use_case = UpdateTunnelHostname(uow, client, FakeCacheClient(), FakeAuditApi())
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        updated = await use_case.execute(
            config.environment_id, tunnel.id, hostname_row.id, "http://new", actor=actor
        )

        assert updated.service == "http://new"
        sent = client.put_calls[-1]
        assert sent == [{"hostname": "app.example.com", "service": "http://new", "path": "/api/*"}]

    async def test_lock_already_held_raises_config_locked(self) -> None:
        uow, config, tunnel, hostname_row, client = await self._setup_with_hostname()
        cache = FakeCacheClient()
        await cache.try_acquire_lock(f"lock:tunnel:{tunnel.id}", ttl=5)
        use_case = UpdateTunnelHostname(uow, client, cache, FakeAuditApi())
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        with pytest.raises(TunnelConfigLocked):
            await use_case.execute(
                config.environment_id, tunnel.id, hostname_row.id, "http://new", actor=actor
            )
        assert client.put_calls == []

    async def test_local_write_failure_triggers_compensating_put_back(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        uow, config, tunnel, hostname_row, client = await self._setup_with_hostname()

        class BrokenHostnameRepo:
            async def get_by_id(self, hostname_id):
                return hostname_row

            async def update_service(self, *args, **kwargs):
                raise RuntimeError("db exploded")

        uow.tunnel_hostnames = BrokenHostnameRepo()
        use_case = UpdateTunnelHostname(uow, client, FakeCacheClient(), FakeAuditApi())
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        with pytest.raises(TunnelIngressSyncFailed):
            await use_case.execute(
                config.environment_id, tunnel.id, hostname_row.id, "http://new", actor=actor
            )

        _assert_first_critical_log_carries_exception(caplog)

        assert client.put_calls[-1] == [{"hostname": "app.example.com", "service": "http://old"}]

    async def test_rejects_hostname_belonging_to_a_different_environment(self) -> None:
        uow, config, tunnel, hostname_row, client = await self._setup_with_hostname()
        other_environment_id = uuid4()
        uow.tunnel_hostnames._rows[hostname_row.id] = hostname_row.model_copy(
            update={"environment_id": other_environment_id}
        )
        use_case = UpdateTunnelHostname(uow, client, FakeCacheClient(), FakeAuditApi())
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        with pytest.raises(TunnelPublicHostnameNotFound):
            await use_case.execute(
                config.environment_id, tunnel.id, hostname_row.id, "http://new", actor=actor
            )
        assert client.put_calls == []

    async def test_rejects_hostname_with_no_matched_environment(self) -> None:
        """NULL-attributed hostnames are rejected too (D7) — the same
        strict-equality guard DNS records already use, no exemption for
        the unmatched case."""
        uow, config, tunnel, hostname_row, client = await self._setup_with_hostname()
        uow.tunnel_hostnames._rows[hostname_row.id] = hostname_row.model_copy(update={"environment_id": None})
        use_case = UpdateTunnelHostname(uow, client, FakeCacheClient(), FakeAuditApi())
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        with pytest.raises(TunnelPublicHostnameNotFound):
            await use_case.execute(
                config.environment_id, tunnel.id, hostname_row.id, "http://new", actor=actor
            )
        assert client.put_calls == []


class TestRemoveTunnelHostname:
    async def _setup_with_hostname(self):
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="acc",
            cf_account_id="cf-1",
            api_token=FernetCodec.encrypt("tok", key=TEST_FERNET_KEY),
            created_by=None,
        )
        config = await uow.configs.create(
            environment_id=uuid4(), cloudflare_account_id=account.id, zone_id="z1", zone_name="example.com"
        )
        tunnel = await uow.tunnels.create(cloudflare_account_id=account.id, cf_tunnel_id="tun-1", name="t")
        hostname_row = await uow.tunnel_hostnames.create(
            tunnel_id=tunnel.id,
            hostname="app.example.com",
            service="http://x",
            created_by=None,
            environment_id=config.environment_id,
        )
        catch_all = {"service": "http_status:404"}
        rule = {"hostname": "app.example.com", "service": "http://x"}
        client = FakeCloudflareTunnelClient(ingress=[rule, catch_all])
        return uow, config, tunnel, hostname_row, client, catch_all

    async def test_removes_rule_and_preserves_catch_all(self) -> None:
        uow, config, tunnel, hostname_row, client, catch_all = await self._setup_with_hostname()
        use_case = RemoveTunnelHostname(uow, client, FakeCacheClient(), FakeAuditApi())
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        await use_case.execute(config.environment_id, tunnel.id, hostname_row.id, actor=actor)

        assert client.put_calls[-1] == [catch_all]
        assert await uow.tunnel_hostnames.get_by_id(hostname_row.id) is None

    async def test_rejects_hostname_belonging_to_a_different_environment(self) -> None:
        uow, config, tunnel, hostname_row, client, _catch_all = await self._setup_with_hostname()
        other_environment_id = uuid4()
        uow.tunnel_hostnames._rows[hostname_row.id] = hostname_row.model_copy(
            update={"environment_id": other_environment_id}
        )
        use_case = RemoveTunnelHostname(uow, client, FakeCacheClient(), FakeAuditApi())
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        with pytest.raises(TunnelPublicHostnameNotFound):
            await use_case.execute(config.environment_id, tunnel.id, hostname_row.id, actor=actor)
        assert client.put_calls == []
        assert await uow.tunnel_hostnames.get_by_id(hostname_row.id) is not None

    async def test_rejects_hostname_with_no_matched_environment(self) -> None:
        uow, config, tunnel, hostname_row, client, _catch_all = await self._setup_with_hostname()
        uow.tunnel_hostnames._rows[hostname_row.id] = hostname_row.model_copy(update={"environment_id": None})
        use_case = RemoveTunnelHostname(uow, client, FakeCacheClient(), FakeAuditApi())
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        with pytest.raises(TunnelPublicHostnameNotFound):
            await use_case.execute(config.environment_id, tunnel.id, hostname_row.id, actor=actor)
        assert client.put_calls == []
        assert await uow.tunnel_hostnames.get_by_id(hostname_row.id) is not None

    async def test_lock_already_held_raises_config_locked(self) -> None:
        uow, config, tunnel, hostname_row, client, _ = await self._setup_with_hostname()
        cache = FakeCacheClient()
        await cache.try_acquire_lock(f"lock:tunnel:{tunnel.id}", ttl=5)
        use_case = RemoveTunnelHostname(uow, client, cache, FakeAuditApi())
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        with pytest.raises(TunnelConfigLocked):
            await use_case.execute(config.environment_id, tunnel.id, hostname_row.id, actor=actor)
        assert client.put_calls == []

    async def test_local_delete_failure_triggers_compensating_put_back(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        uow, config, tunnel, hostname_row, client, catch_all = await self._setup_with_hostname()
        starting_ingress = [{"hostname": "app.example.com", "service": "http://x"}, catch_all]

        class BrokenHostnameRepo:
            async def get_by_id(self, hostname_id):
                return hostname_row

            async def delete(self, *args, **kwargs):
                raise RuntimeError("db exploded")

        uow.tunnel_hostnames = BrokenHostnameRepo()
        use_case = RemoveTunnelHostname(uow, client, FakeCacheClient(), FakeAuditApi())
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        with pytest.raises(TunnelIngressSyncFailed):
            await use_case.execute(config.environment_id, tunnel.id, hostname_row.id, actor=actor)

        _assert_first_critical_log_carries_exception(caplog)

        assert client.put_calls[0] == [catch_all]
        assert client.put_calls[-1] == starting_ingress


class FakeSyncTunnelsClient(FakeCloudflareClient):
    """Fakes only the 2 methods SyncTunnels calls: list_tunnels (account-wide)
    and get_tunnel_configuration (per tunnel, keyed by cf_tunnel_id)."""

    def __init__(
        self,
        tunnels: list[dict] | None = None,
        ingress_by_id: dict[str, list[dict]] | None = None,
        raises: Exception | None = None,
    ) -> None:
        super().__init__(raises=raises)
        self._tunnels = tunnels if tunnels is not None else []
        self._ingress_by_id = ingress_by_id if ingress_by_id is not None else {}

    async def list_tunnels(self, *, cf_account_id: str, api_token: str) -> list[dict]:
        return self._tunnels

    async def get_tunnel_configuration(
        self, *, cf_account_id: str, cf_tunnel_id: str, api_token: str
    ) -> list[dict]:
        return self._ingress_by_id.get(cf_tunnel_id, [])


def _fake_environment(environment_id: UUID, base_url: str | None) -> SimpleNamespace:
    """Minimal stand-in for projects.public.EnvironmentRead — SyncTunnels
    only ever reads .id/.base_url off what FakeProjectsApi returns."""
    return SimpleNamespace(id=environment_id, base_url=base_url)


class TestSyncTunnels:
    async def _setup(self, *, sibling_base_urls: dict[UUID, str | None] | None = None, **client_kwargs):
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="acc",
            cf_account_id="cf-1",
            api_token=FernetCodec.encrypt("tok", key=TEST_FERNET_KEY),
            created_by=None,
        )
        triggering_config = await uow.configs.create(
            environment_id=uuid4(), cloudflare_account_id=account.id, zone_id="z1", zone_name="a.example.com"
        )
        environments = {
            triggering_config.environment_id: _fake_environment(triggering_config.environment_id, None)
        }
        for env_id, base_url in (sibling_base_urls or {}).items():
            await uow.configs.create(
                environment_id=env_id,
                cloudflare_account_id=account.id,
                zone_id="z2",
                zone_name="b.example.com",
            )
            environments[env_id] = _fake_environment(env_id, base_url)
        client = FakeSyncTunnelsClient(**client_kwargs)
        projects_api = FakeProjectsApi(environments)
        return uow, triggering_config, client, projects_api

    async def test_syncing_from_one_environment_matches_a_sibling_environments_hostname(self) -> None:
        """The literal regression test for the bug: triggering a sync from
        environment A must correctly populate hostname->environment
        associations for environment B too, sharing the same account —
        never corrupting or ignoring B's data."""
        env_b_id = uuid4()
        uow, triggering_config, client, projects_api = await self._setup(
            sibling_base_urls={env_b_id: "https://b.agentsplatform.cloud"},
            tunnels=[{"id": "tun-1", "name": "shared", "status": "healthy"}],
            ingress_by_id={
                "tun-1": [
                    {"hostname": "b.agentsplatform.cloud", "service": "http://localhost:5173"},
                    {"service": "http_status:404"},
                ]
            },
        )
        use_case = SyncTunnels(uow, client, projects_api)

        await use_case.execute(triggering_config.environment_id)

        tunnel = await uow.tunnels.get_by_cf_tunnel_id("tun-1")
        assert tunnel is not None
        hostnames = await uow.tunnel_hostnames.list_for_tunnel(tunnel.id)
        matched = next(h for h in hostnames if h.hostname == "b.agentsplatform.cloud")
        assert matched.environment_id == env_b_id

    async def test_environment_with_no_base_url_never_gets_a_hostname_matched(self) -> None:
        uow, triggering_config, client, projects_api = await self._setup(
            tunnels=[{"id": "tun-1", "name": "t", "status": "healthy"}],
            ingress_by_id={"tun-1": [{"hostname": "unmatched.example.com", "service": "http://x"}]},
        )
        use_case = SyncTunnels(uow, client, projects_api)

        await use_case.execute(triggering_config.environment_id)

        tunnel = await uow.tunnels.get_by_cf_tunnel_id("tun-1")
        assert tunnel is not None
        hostnames = await uow.tunnel_hostnames.list_for_tunnel(tunnel.id)
        assert hostnames[0].environment_id is None

    async def test_removes_local_hostname_no_longer_reported_by_cloudflare(self) -> None:
        uow, triggering_config, client, projects_api = await self._setup(
            tunnels=[{"id": "tun-1", "name": "t", "status": "healthy"}],
            ingress_by_id={"tun-1": []},
        )
        stale_tunnel = await uow.tunnels.upsert_from_sync(
            cloudflare_account_id=triggering_config.cloudflare_account_id,
            cf_tunnel_id="tun-1",
            name="t",
            status=TunnelStatus.HEALTHY,
            last_synced_at=datetime.now(UTC),
        )
        await uow.tunnel_hostnames.create(
            tunnel_id=stale_tunnel.id, hostname="gone.example.com", service="http://x", created_by=None
        )
        use_case = SyncTunnels(uow, client, projects_api)

        await use_case.execute(triggering_config.environment_id)

        hostnames = await uow.tunnel_hostnames.list_for_tunnel(stale_tunnel.id)
        assert hostnames == []

    async def test_marks_local_only_tunnel_as_down(self) -> None:
        uow, triggering_config, client, projects_api = await self._setup(tunnels=[])
        local_only = await uow.tunnels.create(
            cloudflare_account_id=triggering_config.cloudflare_account_id, cf_tunnel_id="tun-gone", name="t"
        )
        use_case = SyncTunnels(uow, client, projects_api)

        await use_case.execute(triggering_config.environment_id)

        updated = await uow.tunnels.get_by_id(local_only.id)
        assert updated is not None
        assert updated.status == "down"

    async def test_gracefully_degrades_when_environment_unbound(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        use_case = SyncTunnels(uow, FakeSyncTunnelsClient(), FakeProjectsApi({}))

        tunnels = await use_case.execute(uuid4())

        assert tunnels == []


class FakeTrafficStatsClient(FakeCloudflareClient):
    def __init__(self, stats: CloudflareTrafficStats | None = None, raises: Exception | None = None) -> None:
        super().__init__(raises=raises)
        self._stats = stats
        self.traffic_calls: list[dict] = []

    async def get_zone_traffic_stats(self, *, zone_id, api_token, hostname, since, until):
        self.traffic_calls.append({"zone_id": zone_id, "hostname": hostname, "since": since, "until": until})
        if self._raises is not None:
            raise self._raises
        return self._stats


class TestGetCloudflareTrafficStats:
    async def _setup(self, *, base_url: str | None):
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A",
            cf_account_id="cf-1",
            api_token=FernetCodec.encrypt("plain", key=TEST_FERNET_KEY),
            created_by=ACTOR_ID,
        )
        env_id = uuid4()
        await uow.configs.create(
            environment_id=env_id, cloudflare_account_id=account.id, zone_id="z1", zone_name="example.com"
        )
        projects_api = FakeProjectsApi({env_id: _fake_environment(env_id, base_url)})
        return uow, env_id, projects_api

    async def test_raises_config_not_found_for_unbound_environment(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        client = FakeTrafficStatsClient()
        projects_api = FakeProjectsApi({})
        use_case = GetCloudflareTrafficStats(uow, client, projects_api)

        with pytest.raises(CloudflareConfigNotFound):
            await use_case.execute(environment_id=uuid4(), since=None, until=None)

    async def test_raises_base_url_not_configured_when_environment_has_none(self) -> None:
        uow, env_id, projects_api = await self._setup(base_url=None)
        client = FakeTrafficStatsClient()
        use_case = GetCloudflareTrafficStats(uow, client, projects_api)

        with pytest.raises(EnvironmentBaseUrlNotConfigured):
            await use_case.execute(environment_id=env_id, since=None, until=None)

    async def test_calls_client_with_hostname_parsed_from_base_url(self) -> None:
        uow, env_id, projects_api = await self._setup(base_url="https://app.example.com/some/path")
        stats = CloudflareTrafficStats(
            hostname="app.example.com", total_requests=1, total_bytes=2, buckets=[], status_codes=[]
        )
        client = FakeTrafficStatsClient(stats=stats)
        use_case = GetCloudflareTrafficStats(uow, client, projects_api)

        result = await use_case.execute(environment_id=env_id, since=None, until=None)

        assert result == stats
        assert client.traffic_calls[0]["hostname"] == "app.example.com"
        assert client.traffic_calls[0]["zone_id"] == "z1"

    async def test_defaults_to_a_24_hour_range_ending_now_when_omitted(self) -> None:
        uow, env_id, projects_api = await self._setup(base_url="https://app.example.com")
        client = FakeTrafficStatsClient(
            stats=CloudflareTrafficStats(
                hostname="app.example.com", total_requests=0, total_bytes=0, buckets=[], status_codes=[]
            )
        )
        use_case = GetCloudflareTrafficStats(uow, client, projects_api)

        before_call = datetime.now(UTC)
        await use_case.execute(environment_id=env_id, since=None, until=None)
        after_call = datetime.now(UTC)

        call = client.traffic_calls[0]
        assert before_call <= call["until"] <= after_call
        assert call["until"] - call["since"] == timedelta(hours=24)

    async def test_uses_caller_supplied_range_when_given(self) -> None:
        uow, env_id, projects_api = await self._setup(base_url="https://app.example.com")
        client = FakeTrafficStatsClient(
            stats=CloudflareTrafficStats(
                hostname="app.example.com", total_requests=0, total_bytes=0, buckets=[], status_codes=[]
            )
        )
        use_case = GetCloudflareTrafficStats(uow, client, projects_api)
        since = datetime(2026, 1, 1, tzinfo=UTC)
        until = datetime(2026, 1, 2, tzinfo=UTC)

        await use_case.execute(environment_id=env_id, since=since, until=until)

        call = client.traffic_calls[0]
        assert call["since"] == since
        assert call["until"] == until
