"""Dependency wiring for the auth module.

The composition root: the only place that names a concrete class
(AuthUnitOfWork) instead of its Abstract* contract. See
references/layer-examples.md.

get_current_user / require_auth are structural stubs: the JWT session
mechanism (app/core/security.py) that would decode a cookie into a user
does not exist yet in this issue's scope, so both raise 501 rather than
silently accepting every request. The real implementation is owned by the
SSO integration issue and replaces the bodies below without changing the
signature other modules already depend on.
"""

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.modules.auth.schemas import UserRead
from app.modules.auth.uow import AbstractAuthUnitOfWork, AuthUnitOfWork


async def get_uow(session: AsyncSession = Depends(get_session)) -> AuthUnitOfWork:
    """Provide a request scoped unit of work. The one place the concrete class is named."""
    return AuthUnitOfWork(session)


async def get_current_user(uow: AbstractAuthUnitOfWork = Depends(get_uow)) -> UserRead:
    """Resolve the signed in user from the session cookie.

    Stub: no session mechanism is implemented yet. See module docstring.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Session auth not implemented yet"
    )


async def require_auth(user: UserRead = Depends(get_current_user)) -> UserRead:
    """Guard a route behind an authenticated session.

    Stub: delegates to get_current_user, which is itself not implemented yet.
    """
    return user
