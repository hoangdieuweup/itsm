"""Integration tests for the projects repositories — real Postgres via a
locally scoped session fixture, mirroring tests/cloudflare/test_repository.py.
Nothing here commits: the session is rolled back after each test."""

from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.integrations.cache.client import CacheClient
from app.modules.projects.exceptions import (
    EnvironmentNotFound,
    ProjectLinkNotFound,
    ProjectNotFound,
    ProjectRoleNotFound,
)
from app.modules.projects.models import Project
from app.modules.projects.repository import (
    EnvironmentRepository,
    ProjectLinkRepository,
    ProjectRepository,
    ProjectRoleRepository,
)
from app.modules.rbac.models import Permission


@pytest.fixture
async def _session(engine) -> AsyncIterator[AsyncSession]:
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


@contextmanager
def _count_statements(engine: AsyncEngine) -> Iterator[list[str]]:
    """Collects every SQL statement the engine sends while the block runs."""
    statements: list[str] = []

    def _record(_conn, _cursor, statement, _parameters, _context, _executemany) -> None:
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", _record)
    try:
        yield statements
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _record)


async def _make_project(session: AsyncSession) -> Project:
    project = Project(name=f"P-{uuid4()}")
    session.add(project)
    await session.flush()
    return project


async def _make_permissions(session: AsyncSession, count: int) -> list[UUID]:
    rows = [
        Permission(
            resource=f"test_{uuid4().hex[:12]}", action="read", description_key="permissions.test.read"
        )
        for _ in range(count)
    ]
    session.add_all(rows)
    await session.flush()
    return [row.id for row in rows]


async def _make_three_roles(session: AsyncSession) -> tuple[Project, ProjectRoleRepository]:
    project = await _make_project(session)
    permission_ids = await _make_permissions(session, 3)
    repo = ProjectRoleRepository(session)
    for index in range(3):
        await repo.create(
            project_id=project.id, name=f"role-{index}", permission_ids=permission_ids[: index + 1]
        )
    return project, repo


class TestProjectRoleRepositoryBatchLoading:
    async def test_list_for_project_loads_all_permissions_in_one_query(
        self, _session: AsyncSession, engine: AsyncEngine
    ) -> None:
        project, repo = await _make_three_roles(_session)

        with _count_statements(engine) as statements:
            roles = await repo.list_for_project(project.id)

        assert [len(role.permission_ids) for role in roles] == [1, 2, 3]
        assert len(statements) == 2

    async def test_list_page_loads_all_permissions_in_one_query(
        self, _session: AsyncSession, engine: AsyncEngine
    ) -> None:
        _, repo = await _make_three_roles(_session)

        with _count_statements(engine) as statements:
            roles, total = await repo.list_page(limit=50, offset=0)

        assert total == 3
        assert sorted(len(role.permission_ids) for role in roles) == [1, 2, 3]
        assert len(statements) == 3


class TestUpdatesRaiseNotFoundForMissingRows:
    async def test_project(self, _session: AsyncSession) -> None:
        with pytest.raises(ProjectNotFound):
            await ProjectRepository(_session, CacheClient.__new__(CacheClient)).update(
                uuid4(), name="x", description=None
            )

    async def test_environment(self, _session: AsyncSession) -> None:
        with pytest.raises(EnvironmentNotFound):
            await EnvironmentRepository(_session, CacheClient.__new__(CacheClient)).update(
                uuid4(), name="x", base_url=None
            )

    async def test_project_link(self, _session: AsyncSession) -> None:
        with pytest.raises(ProjectLinkNotFound):
            await ProjectLinkRepository(_session).update(uuid4(), name="x", url=None)

    async def test_project_role(self, _session: AsyncSession) -> None:
        with pytest.raises(ProjectRoleNotFound):
            await ProjectRoleRepository(_session).update(uuid4(), name="x", permission_ids=None)
