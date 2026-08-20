"""Database connection, declarative base and naming conventions."""

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "%(column_0_label)s_idx",
    "uq": "%(table_name)s_%(column_0_name)s_key",
    "ck": "%(table_name)s_%(constraint_name)s_check",
    "fk": "%(table_name)s_%(column_0_name)s_fkey",
    "pk": "%(table_name)s_pkey",
}


class Base(DeclarativeBase):
    """Declarative base with explicit index and constraint naming."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a request scoped session, committing on success and rolling back on failure.

    This is the transaction boundary for any module using `--minimal` (no
    uow.py): a repository only ever calls flush(), never commit() — see
    references/architecture.md#transactions — so something has to commit
    once the request finishes cleanly. For a module WITH a unit of work,
    uow.commit() already ran before the route handler returned; committing
    an already-committed, empty transaction here is a harmless no-op, not a
    double write.
    """
    factory = request.app.state.session_factory
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
