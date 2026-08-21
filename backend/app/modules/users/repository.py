"""Single access path to the users table."""

from abc import abstractmethod
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.markers import database, helper
from app.core.base.repository import AbstractRepository
from app.integrations.cache.client import CacheClient
from app.modules.common.constants import UserStatus
from app.modules.users.constants import UsersCacheKeys
from app.modules.users.models import User
from app.modules.users.schemas import UserRead


class AbstractUserRepository(AbstractRepository[UserRead]):
    """Contract a use case depends on instead of the concrete SQLAlchemy class below."""

    @abstractmethod
    async def find_by_email(self, email: str) -> UserRead | None:
        """Look up a user by email."""
        raise NotImplementedError

    @abstractmethod
    async def find_by_external_id(self, external_user_id: str) -> UserRead | None:
        """Look up a user by the DX subject identifier."""
        raise NotImplementedError

    @abstractmethod
    async def create(
        self,
        *,
        email: str,
        name: str,
        external_user_id: str,
        employee_code: str | None,
        email_confirmed: bool,
    ) -> UserRead:
        """Create a new user synced from a DX profile."""
        raise NotImplementedError

    @abstractmethod
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
        """Sync an existing user's profile fields from DX. Deliberately excludes
        status: a local admin's suspension must never be silently overwritten by
        the next DX login."""
        raise NotImplementedError

    @abstractmethod
    async def set_last_login(self, user_id: int, at: datetime) -> None:
        """Record the timestamp of a completed login."""
        raise NotImplementedError

    @abstractmethod
    async def set_status(self, user_id: int, status: UserStatus) -> UserRead:
        """Block or unblock a user."""
        raise NotImplementedError


class UserRepository(AbstractUserRepository):
    """SQLAlchemy implementation. Every read of the users table goes through this class."""

    def __init__(self, session: AsyncSession, cache: CacheClient) -> None:
        self._session = session
        self._cache = cache

    @database
    async def get_by_id(self, entity_id: int) -> UserRead | None:
        """Return one user, or None when it does not exist. Cache-aside: a
        miss loads from the database and populates the cache."""
        return await self._cache.get_or_load(
            UsersCacheKeys.ENTITY, entity_id, UserRead, lambda: self._load_by_id(entity_id)
        )

    @helper
    async def _load_by_id(self, entity_id: int) -> UserRead | None:
        """Direct database read backing get_by_id's cache-aside loader."""
        row = await self._session.scalar(select(User).where(User.id == entity_id))
        return UserRead.model_validate(row) if row else None

    @database
    async def find_by_email(self, email: str) -> UserRead | None:
        """Look up a user by email."""
        row = await self._session.scalar(select(User).where(User.email == email))
        return UserRead.model_validate(row) if row else None

    @database
    async def find_by_external_id(self, external_user_id: str) -> UserRead | None:
        """Look up a user by the DX subject identifier."""
        row = await self._session.scalar(select(User).where(User.external_user_id == external_user_id))
        return UserRead.model_validate(row) if row else None

    @database
    async def list_page(self, limit: int, offset: int) -> tuple[list[UserRead], int]:
        """Return one page of users together with the total count."""
        rows = await self._session.scalars(select(User).order_by(User.id).limit(limit).offset(offset))
        items = [UserRead.model_validate(row) for row in rows]
        total = await self._session.scalar(select(func.count()).select_from(User))
        return items, total or 0

    @database
    async def create(
        self,
        *,
        email: str,
        name: str,
        external_user_id: str,
        employee_code: str | None,
        email_confirmed: bool,
    ) -> UserRead:
        """Create a new user synced from a DX profile.

        status is set to ACTIVE (not the model's PENDING default): DX is
        this app's identity provider, so a profile it hands back has
        already been authenticated there — see docs/tasks/sso-login.md #5.4.
        """
        row = User(
            email=email,
            name=name,
            status=UserStatus.ACTIVE,
            external_user_id=external_user_id,
            employee_code=employee_code,
            email_confirmed=email_confirmed,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return UserRead.model_validate(row)

    @database
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
        """Sync an existing user's profile fields from DX (status untouched)."""
        row = await self._session.get(User, user_id)
        if row is None:
            raise ValueError(f"user {user_id} does not exist")
        row.email = email
        row.name = name
        row.external_user_id = external_user_id
        row.employee_code = employee_code
        row.email_confirmed = email_confirmed
        await self._session.flush()
        await self._session.refresh(row)
        return UserRead.model_validate(row)

    @database
    async def set_last_login(self, user_id: int, at: datetime) -> None:
        """Record the timestamp of a completed login."""
        row = await self._session.get(User, user_id)
        if row is not None:
            row.last_login_at = at
            await self._session.flush()

    @database
    async def set_status(self, user_id: int, status: UserStatus) -> UserRead:
        """Block or unblock a user."""
        row = await self._session.get(User, user_id)
        if row is None:
            raise ValueError(f"user {user_id} does not exist")
        row.status = status
        await self._session.flush()
        await self._session.refresh(row)
        return UserRead.model_validate(row)
