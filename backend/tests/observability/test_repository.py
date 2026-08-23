"""Integration tests for the observability repository — real Postgres via a
locally scoped session fixture, mirroring tests/cloudflare/test_repository.py's
`_session` pattern (session_factory from the shared `engine` fixture,
truncate-after-test for isolation)."""

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.observability.constants import LokiAuthType
from app.modules.observability.models import LokiConfig
from app.modules.observability.repository import LokiConfigRepository
from app.modules.projects.models import Environment, Project


@pytest.fixture
async def _session(engine) -> AsyncIterator[AsyncSession]:
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()

    async with engine.begin() as conn:
        await conn.execute(delete(LokiConfig))
        await conn.execute(delete(Environment))
        await conn.execute(delete(Project))


async def _make_environment(session: AsyncSession) -> Environment:
    project = Project(name=f"P-{uuid4()}")
    session.add(project)
    await session.flush()
    env = Environment(project_id=project.id, type="dev", name="Dev", base_url=None)
    session.add(env)
    await session.flush()
    await session.refresh(env)
    await session.commit()
    return env


class TestLokiConfigRepository:
    async def test_create_and_get_by_environment_id(self, _session: AsyncSession) -> None:
        env = await _make_environment(_session)
        repo = LokiConfigRepository(_session)

        created = await repo.create(
            environment_id=env.id,
            endpoint_url="http://loki:3100",
            tenant_id=None,
            auth_type=LokiAuthType.NONE,
            credential=None,
            default_query="",
            default_range_minutes=60,
        )

        found = await repo.get_by_environment_id(env.id)
        assert found is not None
        assert found.id == created.id
        assert found.endpoint_url == "http://loki:3100"

    async def test_get_by_environment_id_returns_none_when_absent(self, _session: AsyncSession) -> None:
        repo = LokiConfigRepository(_session)
        assert await repo.get_by_environment_id(uuid4()) is None

    async def test_get_credential_ciphertext_returns_raw_column(self, _session: AsyncSession) -> None:
        env = await _make_environment(_session)
        repo = LokiConfigRepository(_session)
        await repo.create(
            environment_id=env.id,
            endpoint_url="http://loki:3100",
            tenant_id=None,
            auth_type=LokiAuthType.BEARER,
            credential="ciphertext-value",
            default_query="",
            default_range_minutes=60,
        )
        assert await repo.get_credential_ciphertext(env.id) == "ciphertext-value"

    async def test_get_credential_ciphertext_returns_none_when_absent(self, _session: AsyncSession) -> None:
        repo = LokiConfigRepository(_session)
        assert await repo.get_credential_ciphertext(uuid4()) is None

    async def test_environment_id_is_unique(self, _session: AsyncSession) -> None:
        env = await _make_environment(_session)
        repo = LokiConfigRepository(_session)
        await repo.create(
            environment_id=env.id,
            endpoint_url="http://loki:3100",
            tenant_id=None,
            auth_type=LokiAuthType.NONE,
            credential=None,
            default_query="",
            default_range_minutes=60,
        )
        await _session.commit()

        with pytest.raises(IntegrityError):
            await repo.create(
                environment_id=env.id,
                endpoint_url="http://loki-2:3100",
                tenant_id=None,
                auth_type=LokiAuthType.NONE,
                credential=None,
                default_query="",
                default_range_minutes=60,
            )
            await _session.commit()

    async def test_update_by_environment_id(self, _session: AsyncSession) -> None:
        env = await _make_environment(_session)
        repo = LokiConfigRepository(_session)
        await repo.create(
            environment_id=env.id,
            endpoint_url="http://loki:3100",
            tenant_id=None,
            auth_type=LokiAuthType.NONE,
            credential=None,
            default_query="",
            default_range_minutes=60,
        )
        await _session.commit()

        updated = await repo.update_by_environment_id(
            env.id,
            endpoint_url="http://loki-2:3100",
            tenant_id="tenant-a",
            auth_type=LokiAuthType.BEARER,
            credential="ciphertext",
            default_query='{job="api"}',
            default_range_minutes=120,
        )
        assert updated.endpoint_url == "http://loki-2:3100"
        assert updated.auth_type == LokiAuthType.BEARER
        assert updated.default_range_minutes == 120

    async def test_delete_by_environment_id(self, _session: AsyncSession) -> None:
        env = await _make_environment(_session)
        repo = LokiConfigRepository(_session)
        await repo.create(
            environment_id=env.id,
            endpoint_url="http://loki:3100",
            tenant_id=None,
            auth_type=LokiAuthType.NONE,
            credential=None,
            default_query="",
            default_range_minutes=60,
        )
        await _session.commit()

        await repo.delete_by_environment_id(env.id)
        await _session.commit()

        assert await repo.get_by_environment_id(env.id) is None
