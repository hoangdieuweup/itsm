"""Integration tests for the Phase 4 repositories — real Postgres via a
locally scoped session fixture (see the module docstring on `_session`
below), not Fakes: this covers real SQL behavior (UNIQUE(environment_id), FK
cascade) the Fakes in test_services.py don't exercise. No `session` fixture
exists elsewhere in this codebase — the closest precedent is tests/conftest.py's
`client` fixture, which this mirrors (session_factory from `engine`,
truncate-after-test for isolation) but scoped to a raw AsyncSession instead
of a full HTTP client, since these tests exercise the repository layer directly."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.integrations.cache.client import CacheClient
from app.modules.cloudflare.constants import DnsRecordType, TunnelStatus
from app.modules.cloudflare.exceptions import (
    CloudflareAccountNotFound,
    CloudflareConfigNotFound,
    CloudflareTunnelNotFound,
    DnsRecordNotFound,
    TunnelPublicHostnameNotFound,
)
from app.modules.cloudflare.models import (
    CloudflareAccount,
    CloudflareAccountManager,
    CloudflareConfig,
    CloudflareTunnel,
    TunnelPublicHostname,
)
from app.modules.cloudflare.models import DnsRecord as DnsRecordModel
from app.modules.cloudflare.repository import (
    CloudflareAccountRepository,
    CloudflareConfigRepository,
    CloudflareTunnelRepository,
    DnsRecordRepository,
    TunnelHostnameRepository,
)
from app.modules.projects.models import Environment, Project


@pytest.fixture
async def _session(engine) -> AsyncIterator[AsyncSession]:
    """One AsyncSession per test, backed by the shared session-scoped
    `engine`. Rows this test created are deleted afterward so later tests
    (in this file or others sharing `engine`) start clean, mirroring
    conftest.py's `client` fixture teardown but scoped to only the tables
    this file touches."""
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()

    async with engine.begin() as conn:
        await conn.execute(delete(TunnelPublicHostname))
        await conn.execute(delete(CloudflareTunnel))
        await conn.execute(delete(DnsRecordModel))
        await conn.execute(delete(CloudflareConfig))
        await conn.execute(delete(CloudflareAccountManager))
        await conn.execute(delete(CloudflareAccount))
        await conn.execute(delete(Environment))
        await conn.execute(delete(Project))


async def _make_account(session: AsyncSession):
    repo = CloudflareAccountRepository(session, CacheClient.__new__(CacheClient))
    account = await repo.create(label="A", cf_account_id="cf-1", api_token="ciphertext", created_by=None)
    await session.commit()
    return account


async def _make_environment(session: AsyncSession):
    project = Project(name=f"P-{uuid4()}")
    session.add(project)
    await session.flush()
    env = Environment(project_id=project.id, type="dev", name="Dev", base_url=None)
    session.add(env)
    await session.flush()
    await session.refresh(env)
    await session.commit()
    return env


class TestCloudflareConfigRepository:
    async def test_create_and_get_by_environment_id(self, _session: AsyncSession) -> None:
        account = await _make_account(_session)
        env = await _make_environment(_session)
        repo = CloudflareConfigRepository(_session)

        created = await repo.create(
            environment_id=env.id, cloudflare_account_id=account.id, zone_id="z1", zone_name="a.com"
        )

        found = await repo.get_by_environment_id(env.id)
        assert found is not None
        assert found.id == created.id
        assert found.zone_name == "a.com"

    async def test_environment_id_is_unique(self, _session: AsyncSession) -> None:
        account = await _make_account(_session)
        env = await _make_environment(_session)
        repo = CloudflareConfigRepository(_session)
        await repo.create(
            environment_id=env.id, cloudflare_account_id=account.id, zone_id="z1", zone_name="a.com"
        )
        await _session.commit()

        with pytest.raises(IntegrityError):
            await repo.create(
                environment_id=env.id, cloudflare_account_id=account.id, zone_id="z2", zone_name="b.com"
            )
            await _session.commit()

    async def test_get_by_environment_id_returns_none_when_unbound(self, _session: AsyncSession) -> None:
        repo = CloudflareConfigRepository(_session)
        assert await repo.get_by_environment_id(uuid4()) is None

    async def test_list_all_returns_every_binding(self, _session: AsyncSession) -> None:
        account = await _make_account(_session)
        env_a = await _make_environment(_session)
        env_b = await _make_environment(_session)
        repo = CloudflareConfigRepository(_session)
        await repo.create(
            environment_id=env_a.id, cloudflare_account_id=account.id, zone_id="z1", zone_name="a.com"
        )
        await repo.create(
            environment_id=env_b.id, cloudflare_account_id=account.id, zone_id="z2", zone_name="b.com"
        )

        configs = await repo.list_all()

        assert {c.environment_id for c in configs} == {env_a.id, env_b.id}

    async def test_list_all_returns_empty_when_no_bindings(self, _session: AsyncSession) -> None:
        repo = CloudflareConfigRepository(_session)
        assert await repo.list_all() == []

    async def test_update_and_delete_by_environment_id(self, _session: AsyncSession) -> None:
        account = await _make_account(_session)
        env = await _make_environment(_session)
        repo = CloudflareConfigRepository(_session)
        await repo.create(
            environment_id=env.id, cloudflare_account_id=account.id, zone_id="z1", zone_name="a.com"
        )

        updated = await repo.update_by_environment_id(
            env.id, cloudflare_account_id=account.id, zone_id="z2", zone_name="b.com"
        )
        assert updated.zone_id == "z2"

        await repo.delete_by_environment_id(env.id)
        assert await repo.get_by_environment_id(env.id) is None


class TestDnsRecordRepository:
    async def test_create_and_list_for_environment(self, _session: AsyncSession) -> None:
        env = await _make_environment(_session)
        repo = DnsRecordRepository(_session)

        await repo.create(
            environment_id=env.id,
            cf_record_id=f"rec-{uuid4()}",
            record_type=DnsRecordType.A,
            name="app",
            content="1.2.3.4",
            priority=None,
            proxied=True,
            ttl=1,
            created_by=None,
        )

        records = await repo.list_for_environment(env.id)
        assert len(records) == 1

    async def test_update_and_delete(self, _session: AsyncSession) -> None:
        env = await _make_environment(_session)
        repo = DnsRecordRepository(_session)
        record = await repo.create(
            environment_id=env.id,
            cf_record_id=f"rec-{uuid4()}",
            record_type=DnsRecordType.A,
            name="app",
            content="1.2.3.4",
            priority=None,
            proxied=False,
            ttl=1,
            created_by=None,
        )

        updated = await repo.update(record.id, content="5.6.7.8", priority=None, proxied=True, ttl=300)
        assert updated.content == "5.6.7.8"

        await repo.delete(record.id)
        assert await repo.get_by_id(record.id) is None

    async def test_cf_record_id_is_unique(self, _session: AsyncSession) -> None:
        env = await _make_environment(_session)
        repo = DnsRecordRepository(_session)
        shared_id = f"rec-{uuid4()}"
        await repo.create(
            environment_id=env.id,
            cf_record_id=shared_id,
            record_type=DnsRecordType.A,
            name="app",
            content="1.2.3.4",
            priority=None,
            proxied=False,
            ttl=1,
            created_by=None,
        )
        await _session.commit()

        with pytest.raises(IntegrityError):
            await repo.create(
                environment_id=env.id,
                cf_record_id=shared_id,
                record_type=DnsRecordType.A,
                name="app2",
                content="5.6.7.8",
                priority=None,
                proxied=False,
                ttl=1,
                created_by=None,
            )
            await _session.commit()


class TestCloudflareTunnelRepository:
    async def test_create_and_get_by_id(self, _session: AsyncSession) -> None:
        account = await _make_account(_session)
        repo = CloudflareTunnelRepository(_session)
        created = await repo.create(
            cloudflare_account_id=account.id, cf_tunnel_id="tun-1", name="prod-tunnel"
        )
        assert created.status == "unknown"
        fetched = await repo.get_by_id(created.id)
        assert fetched is not None
        assert fetched.cf_tunnel_id == "tun-1"

    async def test_list_for_account_supports_many_tunnels(self, _session: AsyncSession) -> None:
        account = await _make_account(_session)
        repo = CloudflareTunnelRepository(_session)
        await repo.create(cloudflare_account_id=account.id, cf_tunnel_id="tun-a", name="a")
        await repo.create(cloudflare_account_id=account.id, cf_tunnel_id="tun-b", name="b")
        tunnels = await repo.list_for_account(account.id)
        assert len(tunnels) == 2

    async def test_list_for_environment_via_hostnames_only_returns_matched_tunnels(
        self, _session: AsyncSession
    ) -> None:
        account = await _make_account(_session)
        env = await _make_environment(_session)
        tunnel_repo = CloudflareTunnelRepository(_session)
        hostname_repo = TunnelHostnameRepository(_session)
        matched = await tunnel_repo.create(cloudflare_account_id=account.id, cf_tunnel_id="tun-a", name="a")
        unmatched = await tunnel_repo.create(cloudflare_account_id=account.id, cf_tunnel_id="tun-b", name="b")
        await hostname_repo.create(
            tunnel_id=matched.id,
            hostname="app.example.com",
            service="http://x",
            created_by=None,
            environment_id=env.id,
        )
        await hostname_repo.create(
            tunnel_id=unmatched.id, hostname="other.example.com", service="http://y", created_by=None
        )

        tunnels = await tunnel_repo.list_for_environment_via_hostnames(env.id)

        assert [t.id for t in tunnels] == [matched.id]

    async def test_update_status(self, _session: AsyncSession) -> None:
        account = await _make_account(_session)
        repo = CloudflareTunnelRepository(_session)
        created = await repo.create(
            cloudflare_account_id=account.id, cf_tunnel_id="tun-1", name="prod-tunnel"
        )
        updated = await repo.update_status(created.id, status="healthy", last_synced_at=datetime.now(UTC))
        assert updated.status == "healthy"
        assert updated.last_synced_at is not None

    async def test_upsert_from_sync_inserts_then_updates(self, _session: AsyncSession) -> None:
        account = await _make_account(_session)
        other_account = await _make_account(_session)
        repo = CloudflareTunnelRepository(_session)
        now = datetime.now(UTC)

        inserted = await repo.upsert_from_sync(
            cloudflare_account_id=account.id,
            cf_tunnel_id="tun-1",
            name="prod-tunnel",
            status="healthy",
            last_synced_at=now,
        )
        assert inserted.cloudflare_account_id == account.id

        updated = await repo.upsert_from_sync(
            cloudflare_account_id=other_account.id,
            cf_tunnel_id="tun-1",
            name="renamed",
            status="down",
            last_synced_at=now,
        )
        assert updated.id == inserted.id
        assert updated.cloudflare_account_id == other_account.id
        assert updated.name == "renamed"
        assert updated.status == "down"

    async def test_delete(self, _session: AsyncSession) -> None:
        account = await _make_account(_session)
        repo = CloudflareTunnelRepository(_session)
        created = await repo.create(
            cloudflare_account_id=account.id, cf_tunnel_id="tun-1", name="prod-tunnel"
        )
        await repo.delete(created.id)
        assert await repo.get_by_id(created.id) is None


class TestTunnelHostnameRepository:
    async def test_create_and_list_for_tunnel(self, _session: AsyncSession) -> None:
        account = await _make_account(_session)
        tunnel = await CloudflareTunnelRepository(_session).create(
            cloudflare_account_id=account.id, cf_tunnel_id="tun-1", name="prod-tunnel"
        )
        repo = TunnelHostnameRepository(_session)
        created = await repo.create(
            tunnel_id=tunnel.id, hostname="app.example.com", service="http://localhost:8080", created_by=None
        )
        assert created.managed_by == "system"
        assert created.environment_id is None
        hostnames = await repo.list_for_tunnel(tunnel.id)
        assert len(hostnames) == 1
        assert hostnames[0].hostname == "app.example.com"

    async def test_list_for_tunnel_filters_by_environment_id(self, _session: AsyncSession) -> None:
        account = await _make_account(_session)
        env = await _make_environment(_session)
        tunnel = await CloudflareTunnelRepository(_session).create(
            cloudflare_account_id=account.id, cf_tunnel_id="tun-1", name="prod-tunnel"
        )
        repo = TunnelHostnameRepository(_session)
        await repo.create(
            tunnel_id=tunnel.id,
            hostname="matched.example.com",
            service="http://x",
            created_by=None,
            environment_id=env.id,
        )
        await repo.create(
            tunnel_id=tunnel.id, hostname="unmatched.example.com", service="http://y", created_by=None
        )

        hostnames = await repo.list_for_tunnel(tunnel.id, environment_id=env.id)

        assert [h.hostname for h in hostnames] == ["matched.example.com"]

    async def test_list_for_environment_spans_every_tunnel_on_the_account(
        self, _session: AsyncSession
    ) -> None:
        """Distinct from list_for_tunnel — this is the query the drift
        reconciliation job's account-wide before/after snapshot needs, since
        a single environment's matched hostnames can live on more than one
        tunnel sharing the same Cloudflare account."""
        account = await _make_account(_session)
        env = await _make_environment(_session)
        other_env = await _make_environment(_session)
        tunnel_a = await CloudflareTunnelRepository(_session).create(
            cloudflare_account_id=account.id, cf_tunnel_id="tun-a", name="a"
        )
        tunnel_b = await CloudflareTunnelRepository(_session).create(
            cloudflare_account_id=account.id, cf_tunnel_id="tun-b", name="b"
        )
        repo = TunnelHostnameRepository(_session)
        await repo.create(
            tunnel_id=tunnel_a.id,
            hostname="on-a.example.com",
            service="http://a",
            created_by=None,
            environment_id=env.id,
        )
        await repo.create(
            tunnel_id=tunnel_b.id,
            hostname="on-b.example.com",
            service="http://b",
            created_by=None,
            environment_id=env.id,
        )
        await repo.create(
            tunnel_id=tunnel_a.id,
            hostname="other-env.example.com",
            service="http://c",
            created_by=None,
            environment_id=other_env.id,
        )

        hostnames = await repo.list_for_environment(env.id)

        assert {h.hostname for h in hostnames} == {"on-a.example.com", "on-b.example.com"}

    async def test_update_service(self, _session: AsyncSession) -> None:
        account = await _make_account(_session)
        tunnel = await CloudflareTunnelRepository(_session).create(
            cloudflare_account_id=account.id, cf_tunnel_id="tun-1", name="prod-tunnel"
        )
        repo = TunnelHostnameRepository(_session)
        created = await repo.create(
            tunnel_id=tunnel.id, hostname="app.example.com", service="http://localhost:8080", created_by=None
        )
        updated = await repo.update_service(created.id, service="http://localhost:9090")
        assert updated.service == "http://localhost:9090"

    async def test_upsert_from_sync_inserts_then_updates(self, _session: AsyncSession) -> None:
        account = await _make_account(_session)
        env = await _make_environment(_session)
        tunnel = await CloudflareTunnelRepository(_session).create(
            cloudflare_account_id=account.id, cf_tunnel_id="tun-1", name="prod-tunnel"
        )
        repo = TunnelHostnameRepository(_session)
        now = datetime.now(UTC)

        inserted = await repo.upsert_from_sync(
            tunnel_id=tunnel.id,
            hostname="app.example.com",
            service="http://old",
            environment_id=None,
            last_synced_at=now,
        )
        assert inserted.environment_id is None

        updated = await repo.upsert_from_sync(
            tunnel_id=tunnel.id,
            hostname="app.example.com",
            service="http://new",
            environment_id=env.id,
            last_synced_at=now,
        )
        assert updated.id == inserted.id
        assert updated.service == "http://new"
        assert updated.environment_id == env.id

    async def test_delete_not_in_hostnames_removes_stale_rows_only(self, _session: AsyncSession) -> None:
        account = await _make_account(_session)
        tunnel = await CloudflareTunnelRepository(_session).create(
            cloudflare_account_id=account.id, cf_tunnel_id="tun-1", name="prod-tunnel"
        )
        repo = TunnelHostnameRepository(_session)
        keep = await repo.create(
            tunnel_id=tunnel.id, hostname="keep.example.com", service="http://x", created_by=None
        )
        stale = await repo.create(
            tunnel_id=tunnel.id, hostname="stale.example.com", service="http://y", created_by=None
        )

        await repo.delete_not_in_hostnames(tunnel.id, {"keep.example.com"})

        assert await repo.get_by_id(keep.id) is not None
        assert await repo.get_by_id(stale.id) is None

    async def test_delete(self, _session: AsyncSession) -> None:
        account = await _make_account(_session)
        tunnel = await CloudflareTunnelRepository(_session).create(
            cloudflare_account_id=account.id, cf_tunnel_id="tun-1", name="prod-tunnel"
        )
        repo = TunnelHostnameRepository(_session)
        created = await repo.create(
            tunnel_id=tunnel.id, hostname="app.example.com", service="http://localhost:8080", created_by=None
        )
        await repo.delete(created.id)
        assert await repo.get_by_id(created.id) is None


class TestUpdatesRaiseNotFoundForMissingRows:
    async def test_account_update(self, _session: AsyncSession) -> None:
        with pytest.raises(CloudflareAccountNotFound):
            await CloudflareAccountRepository(_session, CacheClient.__new__(CacheClient)).update(
                uuid4(), label="x", api_token=None
            )

    async def test_account_set_webhook_destination(self, _session: AsyncSession) -> None:
        with pytest.raises(CloudflareAccountNotFound):
            await CloudflareAccountRepository(
                _session, CacheClient.__new__(CacheClient)
            ).set_webhook_destination(uuid4(), cf_webhook_destination_id="wh", secret_ciphertext="c")

    async def test_config(self, _session: AsyncSession) -> None:
        with pytest.raises(CloudflareConfigNotFound):
            await CloudflareConfigRepository(_session).update_by_environment_id(
                uuid4(), cloudflare_account_id=uuid4(), zone_id="z", zone_name="a.com"
            )

    async def test_dns_record(self, _session: AsyncSession) -> None:
        with pytest.raises(DnsRecordNotFound):
            await DnsRecordRepository(_session).update(
                uuid4(), content="1.1.1.1", priority=None, proxied=False, ttl=1
            )

    async def test_tunnel(self, _session: AsyncSession) -> None:
        with pytest.raises(CloudflareTunnelNotFound):
            await CloudflareTunnelRepository(_session).update_status(
                uuid4(), status=TunnelStatus.HEALTHY, last_synced_at=datetime.now(UTC)
            )

    async def test_tunnel_hostname(self, _session: AsyncSession) -> None:
        with pytest.raises(TunnelPublicHostnameNotFound):
            await TunnelHostnameRepository(_session).update_service(uuid4(), service="http://x")


class TestCloudflareAccountRepositoryListAll:
    async def test_returns_every_account_ordered_by_label(self, _session: AsyncSession) -> None:
        repo = CloudflareAccountRepository(_session, CacheClient.__new__(CacheClient))
        for label in ("B", "A", "C"):
            await repo.create(label=label, cf_account_id=f"cf-{label}", api_token="c", created_by=None)

        accounts = await repo.list_all()

        assert [account.label for account in accounts] == ["A", "B", "C"]
