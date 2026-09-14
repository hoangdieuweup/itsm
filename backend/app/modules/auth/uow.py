"""Transaction boundary for the auth module.

The login flow writes across users (via UsersApi) and this module's own
dx_tokens table within one atomic transaction; this unit of work owns that
commit boundary and exposes the DX token repository. See
docs/superpowers/specs/2026-08-21-users-module-split-design.md.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.markers import database
from app.core.base.uow import AbstractUnitOfWork
from app.modules.auth.repository import AbstractDxTokenRepository, DxTokenRepository

logger = logging.getLogger(__name__)


class AbstractAuthUnitOfWork(AbstractUnitOfWork):
    """Contract a use case depends on instead of the concrete SQLAlchemy class below."""

    dx_tokens: AbstractDxTokenRepository


class AuthUnitOfWork(AbstractAuthUnitOfWork):
    """Owns the shared session's commit boundary and the DX token repository."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.dx_tokens = DxTokenRepository(session)

    @database
    async def commit(self) -> None:
        """Commit the transaction."""
        await self._session.commit()

    @database
    async def rollback(self) -> None:
        """Roll back the transaction."""
        await self._session.rollback()
        logger.warning("auth unit of work rolled back")
