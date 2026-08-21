"""Transaction boundary for the auth module.

auth owns no tables after the users module split — this exists purely as
the shared request-scoped session's commit boundary for the login flow,
which writes across users (via UsersApi) and dx_core (DxTokenRepository)
within one atomic transaction. See
docs/superpowers/specs/2026-08-21-users-module-split-design.md.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.markers import database
from app.core.base.uow import AbstractUnitOfWork

logger = logging.getLogger(__name__)


class AbstractAuthUnitOfWork(AbstractUnitOfWork):
    """Contract a use case depends on instead of the concrete SQLAlchemy class below."""


class AuthUnitOfWork(AbstractAuthUnitOfWork):
    """Owns the shared session's commit boundary for the login flow. Owns no repository."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @database
    async def commit(self) -> None:
        """Commit the transaction."""
        await self._session.commit()

    @database
    async def rollback(self) -> None:
        """Roll back the transaction."""
        await self._session.rollback()
        logger.warning("auth unit of work rolled back")
