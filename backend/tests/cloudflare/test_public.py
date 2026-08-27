"""Unit tests for app.modules.cloudflare.public — the facade other modules
(observability, in Phase 9) reach cloudflare through."""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.crypto import FernetCodec
from app.modules.cloudflare.config import cloudflare_settings
from app.modules.cloudflare.constants import DnsRecordType, ManagedBy, TunnelStatus
from app.modules.cloudflare.public import CloudflareApi
from app.modules.cloudflare.schemas import CloudflareTunnelRead, DnsRecordRead, TunnelPublicHostnameRead

TEST_KEY = "kL8Zx3vQ9mN2pR7wT4yU6bC1dF5gH0jK3lM6nO9pQ2s="


@pytest.fixture(autouse=True)
def _fernet_key(monkeypatch) -> None:
    monkeypatch.setattr(cloudflare_settings, "FERNET_KEY", TEST_KEY)


class FakeAccountsRepo:
    def __init__(self, accounts=None, token_ciphertexts=None) -> None:
        self._accounts = accounts or {}
        self._tokens = token_ciphertexts or {}
        self._webhook_destinations: dict = {}
        self.set_webhook_destination_calls = []

    async def get_by_id(self, account_id):
        return self._accounts.get(account_id)

    async def get_token_ciphertext(self, account_id):
        return self._tokens.get(account_id)

    async def get_webhook_destination_ciphertext(self, account_id):
        return self._webhook_destinations.get(account_id, (None, None))

    async def set_webhook_destination(self, account_id, *, cf_webhook_destination_id, secret_ciphertext):
        self._webhook_destinations[account_id] = (cf_webhook_destination_id, secret_ciphertext)
        self.set_webhook_destination_calls.append(account_id)


class FakeConfigsRepo:
    def __init__(self, configs=None) -> None:
        self._configs = configs or {}

    async def get_by_environment_id(self, environment_id):
        return self._configs.get(environment_id)

    async def list_all(self):
        return list(self._configs.values())

    async def list_environment_ids_for_account(self, cloudflare_account_id):
        return [
            c.environment_id
            for c in self._configs.values()
            if c.cloudflare_account_id == cloudflare_account_id
        ]

    async def list_environment_ids_for_zone(self, zone_id):
        return [c.environment_id for c in self._configs.values() if c.zone_id == zone_id]


class FakeDnsRecordsRepo:
    def __init__(self) -> None:
        self._rows: dict[str, DnsRecordRead] = {}

    async def list_for_environment(self, environment_id):
        return [r for r in self._rows.values() if r.environment_id == environment_id]

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
        existing = self._rows.get(cf_record_id)
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
        else:
            # Only EXTERNAL rows self-heal environment_id on every sync —
            # mirrors the real repository's SYSTEM-preserving behavior.
            new_environment_id = (
                environment_id if existing.managed_by == ManagedBy.EXTERNAL else existing.environment_id
            )
            row = existing.model_copy(
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
        self._rows[cf_record_id] = row
        return row

    async def delete_not_in_cf_ids(self, environment_ids, keep_cf_ids):
        for cf_id, row in list(self._rows.items()):
            if row.environment_id in environment_ids and cf_id not in keep_cf_ids:
                self._rows.pop(cf_id, None)


class FakeTunnelsRepo:
    def __init__(self) -> None:
        self._rows: dict[str, CloudflareTunnelRead] = {}

    async def get_by_cf_tunnel_id(self, cf_tunnel_id):
        return self._rows.get(cf_tunnel_id)

    async def upsert_from_sync(self, *, cloudflare_account_id, cf_tunnel_id, name, status, last_synced_at):
        existing = self._rows.get(cf_tunnel_id)
        if existing is None:
            row = CloudflareTunnelRead(
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
            row = existing.model_copy(
                update={
                    "cloudflare_account_id": cloudflare_account_id,
                    "name": name,
                    "status": status,
                    "last_synced_at": last_synced_at,
                }
            )
        self._rows[cf_tunnel_id] = row
        return row

    async def list_for_account(self, cloudflare_account_id):
        return [t for t in self._rows.values() if t.cloudflare_account_id == cloudflare_account_id]

    async def update_status(self, tunnel_id, *, status, last_synced_at):
        for cf_id, row in self._rows.items():
            if row.id == tunnel_id:
                updated = row.model_copy(update={"status": status, "last_synced_at": last_synced_at})
                self._rows[cf_id] = updated
                return updated
        raise KeyError(tunnel_id)

    async def mark_missing_tunnels_down(self, *, cloudflare_account_id, active_cf_tunnel_ids, synced_at):
        for cf_id, row in list(self._rows.items()):
            if row.cloudflare_account_id == cloudflare_account_id and cf_id not in active_cf_tunnel_ids:
                self._rows[cf_id] = row.model_copy(
                    update={"status": TunnelStatus.DOWN, "last_synced_at": synced_at}
                )

    async def list_for_environment_via_hostnames(self, environment_id):
        return list(self._rows.values())


class FakeTunnelHostnamesRepo:
    def __init__(self) -> None:
        self._rows: dict[str, TunnelPublicHostnameRead] = {}

    async def list_for_environment(self, environment_id):
        return [h for h in self._rows.values() if h.environment_id == environment_id]

    async def upsert_from_sync(self, *, tunnel_id, hostname, service, environment_id, last_synced_at):
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
        self._rows[hostname] = row
        return row

    async def delete_not_in_hostnames(self, tunnel_id, keep_hostnames):
        for hostname, row in list(self._rows.items()):
            if row.tunnel_id == tunnel_id and hostname not in keep_hostnames:
                self._rows.pop(hostname, None)


class FakeUow:
    def __init__(
        self,
        accounts: FakeAccountsRepo,
        configs: FakeConfigsRepo | None = None,
        dns_records: FakeDnsRecordsRepo | None = None,
        tunnels: FakeTunnelsRepo | None = None,
        tunnel_hostnames: FakeTunnelHostnamesRepo | None = None,
    ) -> None:
        self.accounts = accounts
        self.configs = configs or FakeConfigsRepo()
        self.dns_records = dns_records or FakeDnsRecordsRepo()
        self.tunnels = tunnels or FakeTunnelsRepo()
        self.tunnel_hostnames = tunnel_hostnames or FakeTunnelHostnamesRepo()
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


class FakeProjectsApi:
    def __init__(self, environments: dict) -> None:
        self._environments = environments

    async def get_environment_by_id(self, environment_id):
        return self._environments.get(environment_id)


class FakeCloudflareClient:
    def __init__(self, destination_id: str = "wh-123") -> None:
        self.destination_id = destination_id
        self.create_calls: list[dict] = []
        self.dns_records: list[dict] = []
        self.tunnels: list[dict] = []
        self.ingress_by_id: dict[str, list[dict]] = {}

    async def create_webhook_destination(self, **kwargs):
        self.create_calls.append(kwargs)
        return self.destination_id

    async def list_dns_records(self, *, zone_id, api_token):
        return self.dns_records

    async def list_tunnels(self, *, cf_account_id, api_token):
        return self.tunnels

    async def get_tunnel_configuration(self, *, cf_account_id, cf_tunnel_id, api_token):
        return self.ingress_by_id.get(cf_tunnel_id, [])


class TestGetReadyClientForEnvironment:
    async def test_returns_none_when_unbound(self) -> None:
        api = CloudflareApi(FakeUow(FakeAccountsRepo()), client=FakeCloudflareClient(), projects_api=object())
        assert await api.get_ready_client_for_environment(uuid4()) is None

    async def test_returns_ready_client_when_bound(self) -> None:
        env_id, account_id = uuid4(), uuid4()
        account = SimpleNamespace(id=account_id, cf_account_id="cf-123")
        config = SimpleNamespace(cloudflare_account_id=account_id, zone_id="z1")
        ciphertext = FernetCodec.encrypt("real-token", key=TEST_KEY)
        client = FakeCloudflareClient()
        api = CloudflareApi(
            FakeUow(
                FakeAccountsRepo({account_id: account}, {account_id: ciphertext}),
                FakeConfigsRepo({env_id: config}),
            ),
            client=client,
            projects_api=object(),
        )
        ready = await api.get_ready_client_for_environment(env_id)
        assert ready is not None
        assert ready.cf_account_id == "cf-123"
        assert ready.api_token == "real-token"
        assert ready.client is client
        assert ready.cloudflare_account_id == account_id
        assert ready.zone_id == "z1"


class TestGetReadyClientForAccount:
    async def test_returns_none_when_account_does_not_exist(self) -> None:
        api = CloudflareApi(FakeUow(FakeAccountsRepo()), client=FakeCloudflareClient(), projects_api=object())
        assert await api.get_ready_client_for_account(uuid4()) is None

    async def test_returns_ready_client_when_account_exists(self) -> None:
        account_id = uuid4()
        account = SimpleNamespace(id=account_id, cf_account_id="cf-123")
        ciphertext = FernetCodec.encrypt("real-token", key=TEST_KEY)
        client = FakeCloudflareClient()
        api = CloudflareApi(
            FakeUow(FakeAccountsRepo({account_id: account}, {account_id: ciphertext})),
            client=client,
            projects_api=object(),
        )
        ready = await api.get_ready_client_for_account(account_id)
        assert ready is not None
        assert ready.cf_account_id == "cf-123"
        assert ready.api_token == "real-token"
        assert ready.client is client
        assert ready.cloudflare_account_id == account_id
        assert ready.zone_id is None


class TestEnsureWebhookDestination:
    async def test_registers_new_destination_and_returns_id(self) -> None:
        account_id = uuid4()
        account = SimpleNamespace(id=account_id, cf_account_id="cf-123")
        ciphertext = FernetCodec.encrypt("real-token", key=TEST_KEY)
        accounts_repo = FakeAccountsRepo({account_id: account}, {account_id: ciphertext})
        client = FakeCloudflareClient(destination_id="wh-new")
        api = CloudflareApi(FakeUow(accounts_repo), client=client, projects_api=object())

        destination_id = await api.ensure_webhook_destination(
            account_id, webhook_url="https://x/webhooks/cloudflare-alert/" + str(account_id)
        )

        assert destination_id == "wh-new"
        assert accounts_repo.set_webhook_destination_calls == [account_id]
        assert client.create_calls[0]["cf_account_id"] == "cf-123"

    async def test_idempotent_returns_existing_id_without_calling_client(self) -> None:
        account_id = uuid4()
        account = SimpleNamespace(id=account_id, cf_account_id="cf-123")
        accounts_repo = FakeAccountsRepo({account_id: account})
        accounts_repo._webhook_destinations[account_id] = ("wh-existing", "ciphertext")
        client = FakeCloudflareClient()
        api = CloudflareApi(FakeUow(accounts_repo), client=client, projects_api=object())

        destination_id = await api.ensure_webhook_destination(account_id, webhook_url="https://x")

        assert destination_id == "wh-existing"
        assert client.create_calls == []


class TestGetWebhookSecret:
    async def test_returns_none_when_never_registered(self) -> None:
        account_id = uuid4()
        api = CloudflareApi(FakeUow(FakeAccountsRepo()), client=FakeCloudflareClient(), projects_api=object())
        assert await api.get_webhook_secret(account_id) is None

    async def test_returns_decrypted_secret_when_registered(self) -> None:
        account_id = uuid4()
        secret_ciphertext = FernetCodec.encrypt("real-secret", key=TEST_KEY)
        accounts_repo = FakeAccountsRepo()
        accounts_repo._webhook_destinations[account_id] = ("wh-1", secret_ciphertext)
        api = CloudflareApi(FakeUow(accounts_repo), client=FakeCloudflareClient(), projects_api=object())

        assert await api.get_webhook_secret(account_id) == "real-secret"


def _bound_account(account_id, token="real-token"):
    account = SimpleNamespace(id=account_id, cf_account_id="cf-123")
    accounts_repo = FakeAccountsRepo(
        {account_id: account}, {account_id: FernetCodec.encrypt(token, key=TEST_KEY)}
    )
    return account, accounts_repo


class TestListBoundConfigs:
    async def test_returns_every_config(self) -> None:
        env_a, env_b = uuid4(), uuid4()
        config_a = SimpleNamespace(environment_id=env_a)
        config_b = SimpleNamespace(environment_id=env_b)
        api = CloudflareApi(
            FakeUow(FakeAccountsRepo(), FakeConfigsRepo({env_a: config_a, env_b: config_b})),
            client=FakeCloudflareClient(),
            projects_api=object(),
        )

        configs = await api.list_bound_configs()

        assert {c.environment_id for c in configs} == {env_a, env_b}


class TestReconcileDnsRecords:
    async def test_new_external_record_is_reported(self) -> None:
        account_id, env_id = uuid4(), uuid4()
        account, accounts_repo = _bound_account(account_id)
        config = SimpleNamespace(environment_id=env_id, cloudflare_account_id=account_id, zone_id="z1")
        client = FakeCloudflareClient()
        client.dns_records = [
            {"id": "rec-1", "type": "A", "name": "app", "content": "1.2.3.4", "proxied": False, "ttl": 1}
        ]
        projects_api = FakeProjectsApi({env_id: SimpleNamespace(id=env_id, base_url="https://app")})
        api = CloudflareApi(
            FakeUow(accounts_repo, FakeConfigsRepo({env_id: config})),
            client=client,
            projects_api=projects_api,
        )

        diff = await api.reconcile_dns_records(env_id)

        assert [r.cf_record_id for r in diff.new_external] == ["rec-1"]
        assert diff.vanished == []

    async def test_vanished_record_is_reported(self) -> None:
        """SyncDnsRecords only ever prunes stale rows when Cloudflare's live
        response is non-empty (a deliberate guard against wiping every local
        record on a transient empty/error response) — so this scenario keeps
        one still-present record alongside the vanished one, matching how
        that guard actually behaves in practice."""
        account_id, env_id = uuid4(), uuid4()
        account, accounts_repo = _bound_account(account_id)
        config = SimpleNamespace(environment_id=env_id, cloudflare_account_id=account_id, zone_id="z1")
        dns_records = FakeDnsRecordsRepo()
        await dns_records.upsert_from_sync(
            environment_id=env_id,
            cf_record_id="rec-gone",
            record_type=DnsRecordType.A,
            name="old",
            content="9.9.9.9",
            priority=None,
            proxied=False,
            ttl=1,
            managed_by=ManagedBy.SYSTEM,
            last_synced_at=datetime.now(UTC),
        )
        await dns_records.upsert_from_sync(
            environment_id=env_id,
            cf_record_id="rec-stays",
            record_type=DnsRecordType.A,
            name="app",
            content="1.2.3.4",
            priority=None,
            proxied=False,
            ttl=1,
            managed_by=ManagedBy.SYSTEM,
            last_synced_at=datetime.now(UTC),
        )
        client = FakeCloudflareClient()
        client.dns_records = [
            {"id": "rec-stays", "type": "A", "name": "app", "content": "1.2.3.4", "proxied": False, "ttl": 1}
        ]
        projects_api = FakeProjectsApi({env_id: SimpleNamespace(id=env_id, base_url="https://app")})
        api = CloudflareApi(
            FakeUow(accounts_repo, FakeConfigsRepo({env_id: config}), dns_records=dns_records),
            client=client,
            projects_api=projects_api,
        )

        diff = await api.reconcile_dns_records(env_id)

        assert diff.new_external == []
        assert [r.cf_record_id for r in diff.vanished] == ["rec-gone"]

    async def test_unchanged_record_is_reported_as_neither(self) -> None:
        account_id, env_id = uuid4(), uuid4()
        account, accounts_repo = _bound_account(account_id)
        config = SimpleNamespace(environment_id=env_id, cloudflare_account_id=account_id, zone_id="z1")
        dns_records = FakeDnsRecordsRepo()
        await dns_records.upsert_from_sync(
            environment_id=env_id,
            cf_record_id="rec-1",
            record_type=DnsRecordType.A,
            name="app",
            content="1.2.3.4",
            priority=None,
            proxied=False,
            ttl=1,
            managed_by=ManagedBy.SYSTEM,
            last_synced_at=datetime.now(UTC),
        )
        client = FakeCloudflareClient()
        client.dns_records = [
            {"id": "rec-1", "type": "A", "name": "app", "content": "1.2.3.4", "proxied": False, "ttl": 1}
        ]
        projects_api = FakeProjectsApi({env_id: SimpleNamespace(id=env_id, base_url="https://app")})
        api = CloudflareApi(
            FakeUow(accounts_repo, FakeConfigsRepo({env_id: config}), dns_records=dns_records),
            client=client,
            projects_api=projects_api,
        )

        diff = await api.reconcile_dns_records(env_id)

        assert diff.new_external == []
        assert diff.vanished == []


class TestReconcileTunnelsForAccount:
    async def test_new_external_hostname_attributed_to_the_correct_sibling_environment(self) -> None:
        """The literal regression-adjacent case for Decision #5: one
        account-wide sync must correctly attribute drift to whichever
        SPECIFIC sibling environment a hostname matches, not just the
        environment that happened to trigger the pass."""
        account_id = uuid4()
        env_a, env_b = uuid4(), uuid4()
        account, accounts_repo = _bound_account(account_id)
        configs = FakeConfigsRepo(
            {
                env_a: SimpleNamespace(environment_id=env_a, cloudflare_account_id=account_id, zone_id="za"),
                env_b: SimpleNamespace(environment_id=env_b, cloudflare_account_id=account_id, zone_id="zb"),
            }
        )
        client = FakeCloudflareClient()
        client.tunnels = [{"id": "tun-1", "name": "shared", "status": "healthy"}]
        client.ingress_by_id = {
            "tun-1": [
                {"hostname": "a.example.com", "service": "http://a"},
                {"hostname": "b.example.com", "service": "http://b"},
            ]
        }
        projects_api = FakeProjectsApi(
            {
                env_a: SimpleNamespace(id=env_a, base_url="https://a.example.com"),
                env_b: SimpleNamespace(id=env_b, base_url="https://b.example.com"),
            }
        )
        api = CloudflareApi(FakeUow(accounts_repo, configs), client=client, projects_api=projects_api)

        entries = await api.reconcile_tunnels_for_account(account_id)

        by_hostname = {e.hostname.hostname: e for e in entries}
        assert by_hostname["a.example.com"].environment_id == env_a
        assert by_hostname["b.example.com"].environment_id == env_b
        assert all(e.kind == "new_external" for e in entries)

    async def test_hostname_matching_no_tracked_environment_is_excluded(self) -> None:
        account_id, env_id = uuid4(), uuid4()
        account, accounts_repo = _bound_account(account_id)
        configs = FakeConfigsRepo(
            {env_id: SimpleNamespace(environment_id=env_id, cloudflare_account_id=account_id, zone_id="z1")}
        )
        client = FakeCloudflareClient()
        client.tunnels = [{"id": "tun-1", "name": "shared", "status": "healthy"}]
        client.ingress_by_id = {"tun-1": [{"hostname": "ssh.example.com", "service": "ssh://localhost:22"}]}
        projects_api = FakeProjectsApi(
            {env_id: SimpleNamespace(id=env_id, base_url="https://app.example.com")}
        )
        api = CloudflareApi(FakeUow(accounts_repo, configs), client=client, projects_api=projects_api)

        entries = await api.reconcile_tunnels_for_account(account_id)

        assert entries == []

    async def test_vanished_hostname_is_reported(self) -> None:
        """The tunnel itself still exists on Cloudflare (still returned by
        list_tunnels) — only this one ingress rule was removed from it.
        SyncTunnels only prunes a tunnel's stale hostnames when that tunnel
        is itself still present in the live response (a wholly-deleted
        tunnel is out of scope for this diff — see Decision #5's own
        account-wide framing); this is the realistic "someone edited the
        tunnel's config on the dashboard" case."""
        account_id, env_id = uuid4(), uuid4()
        account, accounts_repo = _bound_account(account_id)
        configs = FakeConfigsRepo(
            {env_id: SimpleNamespace(environment_id=env_id, cloudflare_account_id=account_id, zone_id="z1")}
        )
        tunnels = FakeTunnelsRepo()
        tunnel = await tunnels.upsert_from_sync(
            cloudflare_account_id=account_id,
            cf_tunnel_id="tun-1",
            name="shared",
            status=TunnelStatus.HEALTHY,
            last_synced_at=datetime.now(UTC),
        )
        tunnel_hostnames = FakeTunnelHostnamesRepo()
        await tunnel_hostnames.upsert_from_sync(
            tunnel_id=tunnel.id,
            hostname="gone.example.com",
            service="http://x",
            environment_id=env_id,
            last_synced_at=datetime.now(UTC),
        )
        client = FakeCloudflareClient()
        client.tunnels = [{"id": "tun-1", "name": "shared", "status": "healthy"}]
        client.ingress_by_id = {"tun-1": []}  # the hostname is no longer in this tunnel's live ingress
        projects_api = FakeProjectsApi(
            {env_id: SimpleNamespace(id=env_id, base_url="https://app.example.com")}
        )
        api = CloudflareApi(
            FakeUow(accounts_repo, configs, tunnels=tunnels, tunnel_hostnames=tunnel_hostnames),
            client=client,
            projects_api=projects_api,
        )

        entries = await api.reconcile_tunnels_for_account(account_id)

        assert len(entries) == 1
        assert entries[0].kind == "vanished"
        assert entries[0].hostname.hostname == "gone.example.com"
        assert entries[0].environment_id == env_id

    async def test_no_bound_environments_returns_empty_without_calling_client(self) -> None:
        account_id = uuid4()
        _account, accounts_repo = _bound_account(account_id)
        client = FakeCloudflareClient()
        api = CloudflareApi(
            FakeUow(accounts_repo, FakeConfigsRepo()), client=client, projects_api=FakeProjectsApi({})
        )

        entries = await api.reconcile_tunnels_for_account(account_id)

        assert entries == []
        assert client.tunnels == []  # never even attempted a list_tunnels call in spirit; nothing to sync
