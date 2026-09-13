"""Integration tests for the rbac repository — real Postgres via a locally
scoped session fixture, mirroring tests/cloudflare/test_repository.py.
Nothing here commits: the session is rolled back after each test."""

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.integrations.cache.client import CacheClient
from app.modules.rbac.exceptions import RoleNotFound
from app.modules.rbac.repository import RoleRepository


@pytest.fixture
async def _session(engine) -> AsyncIterator[AsyncSession]:
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


class TestRoleRepositoryUpdate:
    async def test_raises_role_not_found_for_missing_row(self, _session: AsyncSession) -> None:
        with pytest.raises(RoleNotFound):
            await RoleRepository(_session, CacheClient.__new__(CacheClient)).update(
                uuid4(), name="x", permission_ids=None
            )
