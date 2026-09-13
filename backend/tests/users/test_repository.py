"""Integration tests for the users repository — real Postgres via a locally
scoped session fixture, mirroring tests/cloudflare/test_repository.py.
Nothing here commits: the session is rolled back after each test."""

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.integrations.cache.client import CacheClient
from app.modules.common.constants import UserStatus
from app.modules.users.exceptions import UserNotFound
from app.modules.users.repository import UserRepository


@pytest.fixture
async def _session(engine) -> AsyncIterator[AsyncSession]:
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


class TestUpdatesRaiseNotFoundForMissingRows:
    async def test_update_profile(self, _session: AsyncSession) -> None:
        with pytest.raises(UserNotFound):
            await UserRepository(_session, CacheClient.__new__(CacheClient)).update_profile(
                uuid4(),
                email="a@x.com",
                name="A",
                external_user_id="ext-1",
                employee_code=None,
                email_confirmed=True,
            )

    async def test_set_status(self, _session: AsyncSession) -> None:
        with pytest.raises(UserNotFound):
            await UserRepository(_session, CacheClient.__new__(CacheClient)).set_status(
                uuid4(), UserStatus.BLOCKED
            )
