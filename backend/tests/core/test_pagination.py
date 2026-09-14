"""Integration test for PageQuery against real Postgres, using the users table."""

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.pagination import PageQuery
from app.modules.common.constants import UserStatus
from app.modules.users.models import User


@pytest.fixture
async def _session(engine) -> AsyncIterator[AsyncSession]:
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


class TestPageQuery:
    async def test_returns_one_ordered_page_and_the_table_total(self, _session: AsyncSession) -> None:
        baseline = await _session.scalar(select(func.count()).select_from(User)) or 0
        emails = [f"page-{uuid4()}@example.com" for _ in range(3)]
        _session.add_all(User(email=email, name="Page", status=UserStatus.ACTIVE) for email in emails)
        await _session.flush()

        rows, total = await PageQuery.fetch_rows(
            _session, User, limit=2, offset=0, order_by=User.email.desc()
        )

        assert total == baseline + 3
        assert len(rows) == 2
        assert [row.email for row in rows] == sorted((row.email for row in rows), reverse=True)

    async def test_offset_walks_past_the_first_page(self, _session: AsyncSession) -> None:
        baseline = await _session.scalar(select(func.count()).select_from(User)) or 0
        _session.add_all(
            User(email=f"offset-{uuid4()}@example.com", name="Offset", status=UserStatus.ACTIVE)
            for _ in range(3)
        )
        await _session.flush()

        first, total = await PageQuery.fetch_rows(_session, User, limit=2, offset=0, order_by=User.id)
        second, _ = await PageQuery.fetch_rows(_session, User, limit=2, offset=2, order_by=User.id)

        assert total == baseline + 3
        assert {row.id for row in first}.isdisjoint({row.id for row in second})
