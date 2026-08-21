"""Contract exposed to other modules. This is the ONLY file another module
may import from users — enforced by scripts/check_module_boundaries.py.
"""

from datetime import datetime

from fastapi import Depends

from app.core.base.markers import facade
from app.modules.users.constants import UsersCacheKeys, UserStatus
from app.modules.users.dependencies import get_uow
from app.modules.users.events import UserCreated
from app.modules.users.rules import UsersRules
from app.modules.users.schemas import UserRead
from app.modules.users.uow import AbstractUsersUnitOfWork

__all__ = [
    "UserCreated",
    "UserRead",
    "UserStatus",
    "UsersApi",
    "get_users_api",
]


class UsersApi:
    """Facade over the users table for other modules' cross-module needs:
    auth resolving/syncing the signed in user, rbac checking a role
    assignment's target user."""

    def __init__(self, uow: AbstractUsersUnitOfWork) -> None:
        self._uow = uow

    @facade
    async def get_user_by_id(self, user_id: int) -> UserRead | None:
        """Look up any user by id. For a single existence check from another
        module — never for bulk reads, which would mean that module wants its
        own list_page-shaped facade method instead."""
        return await self._uow.users.get_by_id(user_id)

    @facade
    async def is_protected_admin(self, user_id: int) -> bool:
        """True when user_id is the seeded break-glass admin account —
        used by rbac's AssignRole to reject reassigning its role."""
        user = await self.get_user_by_id(user_id)
        return user is not None and UsersRules.is_protected_admin_email(user.email)

    @facade
    async def find_by_email(self, email: str) -> UserRead | None:
        """Look up a user by email — for auth's DX-sync flow only."""
        return await self._uow.users.find_by_email(email)

    @facade
    async def find_by_external_id(self, external_user_id: str) -> UserRead | None:
        """Look up a user by the DX subject identifier — for auth's DX-sync flow only."""
        return await self._uow.users.find_by_external_id(external_user_id)

    @facade
    async def create(
        self,
        *,
        email: str,
        name: str,
        external_user_id: str,
        employee_code: str | None,
        email_confirmed: bool,
    ) -> UserRead:
        """Create a new user synced from a DX profile — for auth's DX-sync
        flow only. Does not commit or invalidate: participates in the
        caller's own transaction. Safe without a matching invalidate_user
        call too, but the caller makes one anyway (see invalidate_user)."""
        return await self._uow.users.create(
            email=email,
            name=name,
            external_user_id=external_user_id,
            employee_code=employee_code,
            email_confirmed=email_confirmed,
        )

    @facade
    async def update_profile(
        self,
        user_id: int,
        *,
        email: str,
        name: str,
        external_user_id: str,
        employee_code: str | None,
        email_confirmed: bool,
    ) -> UserRead:
        """Sync an existing user's profile fields from DX — for auth's DX-sync
        flow only. Does not commit or invalidate: participates in the
        caller's own transaction. The caller MUST call invalidate_user(user_id)
        after its own commit succeeds — a returning user's profile is very
        likely already cached, unlike create's brand-new user_id."""
        return await self._uow.users.update_profile(
            user_id,
            email=email,
            name=name,
            external_user_id=external_user_id,
            employee_code=employee_code,
            email_confirmed=email_confirmed,
        )

    @facade
    async def set_last_login(self, user_id: int, at: datetime) -> None:
        """Record a completed login's timestamp — for auth's login flow only.
        Does not commit or invalidate: participates in the caller's own
        transaction. Covered by the same invalidate_user call as
        create/update_profile within one login."""
        await self._uow.users.set_last_login(user_id, at)

    @facade
    async def invalidate_user(self, user_id: int) -> None:
        """Bump this user's cache version immediately. For a cross-module
        orchestrator (auth's login flow) that wrote via create/update_profile/
        set_last_login above but commits its OWN unit of work, not this one
        — call this right after that commit succeeds. See uow.py's
        invalidate_now docstring."""
        await self._uow.invalidate_now(UsersCacheKeys.ENTITY, user_id)


async def get_users_api(uow: AbstractUsersUnitOfWork = Depends(get_uow)) -> UsersApi:
    """Provide the facade to other modules."""
    return UsersApi(uow)
