"""Unit tests for app.core.uow — fake session and cache, no database."""

from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.uow import CachedSqlAlchemyUnitOfWork, SqlAlchemyUnitOfWork


class RecordingSession:
    """Stand-in for AsyncSession that records the calls a unit of work makes."""

    def __init__(self, log: list[str]) -> None:
        self._log = log

    async def commit(self) -> None:
        self._log.append("commit")

    async def rollback(self) -> None:
        self._log.append("rollback")


class RecordingBumper:
    """Stand-in for the cache, satisfying CacheVersionBumper."""

    def __init__(self, log: list[str]) -> None:
        self._log = log

    async def bump_version(self, entity: str, entity_id) -> None:
        self._log.append(f"bump:{entity}:{entity_id}")


def _cached(log: list[str]) -> CachedSqlAlchemyUnitOfWork:
    return CachedSqlAlchemyUnitOfWork(cast(AsyncSession, RecordingSession(log)), RecordingBumper(log))


class TestSqlAlchemyUnitOfWork:
    async def test_commit_and_rollback_delegate_to_the_session(self) -> None:
        log: list[str] = []
        uow = SqlAlchemyUnitOfWork(cast(AsyncSession, RecordingSession(log)))

        await uow.commit()
        await uow.rollback()

        assert log == ["commit", "rollback"]


class TestCachedSqlAlchemyUnitOfWork:
    async def test_bumps_queued_entities_after_the_commit_in_order(self) -> None:
        """Bumping before the commit would let a concurrent reader repopulate the
        cache from the pre-commit row."""
        log: list[str] = []
        uow = _cached(log)
        uow.mark_stale("project", 1)
        uow.mark_stale("environment", 2)

        await uow.commit()

        assert log == ["commit", "bump:project:1", "bump:environment:2"]

    async def test_a_second_commit_does_not_bump_again(self) -> None:
        log: list[str] = []
        uow = _cached(log)
        uow.mark_stale("project", 1)
        await uow.commit()

        await uow.commit()

        assert log == ["commit", "bump:project:1", "commit"]

    async def test_rollback_drops_the_queue_without_bumping(self) -> None:
        log: list[str] = []
        uow = _cached(log)
        uow.mark_stale("project", 1)

        await uow.rollback()
        await uow.commit()

        assert log == ["rollback", "commit"]
