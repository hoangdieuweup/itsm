"""Dependency wiring for the users module.

The composition root: the only place that names a concrete class
(UsersUnitOfWork) instead of its Abstract* contract. Deliberately imports
nothing from rbac: get_update_user_status needs RbacApi (rbac.public), and
rbac.public needs users.public (for AssignRole's existence/protection
checks), which needs get_uow from this very file — so that factory lives
in users/router.py instead, which is never imported by anything else and
can safely reach into rbac.public without closing that cycle.
"""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.integrations.cache.client import CacheClient
from app.integrations.cache.dependencies import get_cache
from app.modules.users.uow import UsersUnitOfWork


async def get_uow(
    session: AsyncSession = Depends(get_session), cache: CacheClient = Depends(get_cache)
) -> UsersUnitOfWork:
    """Provide a request scoped unit of work. The one place the concrete class is named."""
    return UsersUnitOfWork(session, cache)
