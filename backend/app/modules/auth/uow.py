"""Transaction boundary for the auth module.

The login flow writes across users (via UsersApi) and this module's own
dx_tokens table within one atomic transaction; this unit of work owns that
commit boundary and exposes the DX token repository. See
docs/superpowers/specs/2026-08-21-users-module-split-design.md.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.uow import AbstractUnitOfWork
from app.core.uow import SqlAlchemyUnitOfWork
from app.modules.auth.repository import AbstractDxTokenRepository, DxTokenRepository


class AbstractAuthUnitOfWork(AbstractUnitOfWork):
    """Contract a use case depends on instead of the concrete SQLAlchemy class below."""

    dx_tokens: AbstractDxTokenRepository


class AuthUnitOfWork(AbstractAuthUnitOfWork, SqlAlchemyUnitOfWork):
    """Owns the shared session's commit boundary and the DX token repository."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.dx_tokens = DxTokenRepository(session)
