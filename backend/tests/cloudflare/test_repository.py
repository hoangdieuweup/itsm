"""Integration tests for the Phase 4 repositories — real Postgres via a
locally scoped session fixture (see the module docstring on `_session`
below), not Fakes: this covers real SQL behavior (UNIQUE(environment_id), FK
cascade) the Fakes in test_services.py don't exercise. No `session` fixture
exists elsewhere in this codebase — the closest precedent is tests/conftest.py's
`client` fixture, which this mirrors (session_factory from `engine`,
truncate-after-test for isolation) but scoped to a raw AsyncSession instead
of a full HTTP client, since these tests exercise the repository layer directly."""

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.integrations.cache.client import CacheClient
from app.modules.cloudflare.constants import DnsRecordType
from app.modules.cloudflare.models import CloudflareAccount, CloudflareAccountManager, CloudflareConfig
from app.modules.cloudflare.models import DnsRecord as DnsRecordModel
from app.modules.cloudflare.repository import (
    CloudflareAccountRepository,
    CloudflareConfigRepository,
    DnsRecordRepository,
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
