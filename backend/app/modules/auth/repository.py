"""Single access path to the auth tables (users, departments)."""

from abc import abstractmethod
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.markers import database
from app.core.base.repository import AbstractRepository
from app.modules.auth.constants import UserRole, UserStatus
from app.modules.auth.models import Department, User
from app.modules.auth.schemas import DepartmentRead, UserRead


class AbstractUserRepository(AbstractRepository[UserRead]):
    """Contract a use case depends on instead of the concrete SQLAlchemy class below.

    get_by_id and list_page come from AbstractRepository; this adds the
    lookups and upsert-from-DX-profile writes the SSO sync use case
    (app.modules.auth.services.sync_external_user) needs.
    """

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
        role: UserRole,
        external_user_id: str,
        employee_code: str | None,
        email_confirmed: bool,
        department_id: int | None,
    ) -> UserRead:
        """Create a new user synced from a DX profile. role is set only here —
        a later profile sync never overwrites it, see update_profile."""
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
        department_id: int | None,
    ) -> UserRead:
        """Sync an existing user's profile fields from DX. Deliberately excludes
        role and status: a local admin's promotion/demotion or suspension must
        never be silently overwritten by the next DX login."""
        raise NotImplementedError

    @abstractmethod
    async def set_last_login(self, user_id: int, at: datetime) -> None:
        """Record the timestamp of a completed login."""
        raise NotImplementedError


class UserRepository(AbstractUserRepository):
    """SQLAlchemy implementation. Every read of the users table goes through this class."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @database
    async def get_by_id(self, entity_id: int) -> UserRead | None:
        """Return one user, or None when it does not exist."""
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
        role: UserRole,
        external_user_id: str,
        employee_code: str | None,
        email_confirmed: bool,
        department_id: int | None,
    ) -> UserRead:
        """Create a new user synced from a DX profile.

        status is set to ACTIVE (not the model's PENDING default): DX is
        this app's identity provider, so a profile it hands back has
        already been authenticated there — see docs/tasks/sso-login.md #5.4.
        """
        row = User(
            email=email,
            name=name,
            role=role,
            status=UserStatus.ACTIVE,
            external_user_id=external_user_id,
            employee_code=employee_code,
            email_confirmed=email_confirmed,
            department_id=department_id,
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
        department_id: int | None,
    ) -> UserRead:
        """Sync an existing user's profile fields from DX (role/status untouched)."""
        row = await self._session.get(User, user_id)
        if row is None:
            raise ValueError(f"user {user_id} does not exist")
        row.email = email
        row.name = name
        row.external_user_id = external_user_id
        row.employee_code = employee_code
        row.email_confirmed = email_confirmed
        row.department_id = department_id
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


class AbstractDepartmentRepository(AbstractRepository[DepartmentRead]):
    """Contract a use case depends on instead of the concrete SQLAlchemy class below."""

    @abstractmethod
    async def find_by_code(self, code: str) -> DepartmentRead | None:
        """Look up a department by its DX code."""
        raise NotImplementedError

    @abstractmethod
    async def get_or_create_by_code(self, code: str, name: str) -> DepartmentRead:
        """Return the department for code, creating it from a DX profile if new."""
        raise NotImplementedError


class DepartmentRepository(AbstractDepartmentRepository):
    """SQLAlchemy implementation. Every read of the departments table goes through this class."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @database
    async def get_by_id(self, entity_id: int) -> DepartmentRead | None:
        """Return one department, or None when it does not exist."""
        row = await self._session.scalar(select(Department).where(Department.id == entity_id))
        return DepartmentRead.model_validate(row) if row else None

    @database
    async def find_by_code(self, code: str) -> DepartmentRead | None:
        """Look up a department by its DX code."""
        row = await self._session.scalar(select(Department).where(Department.code == code))
        return DepartmentRead.model_validate(row) if row else None

    @database
    async def list_page(self, limit: int, offset: int) -> tuple[list[DepartmentRead], int]:
        """Return one page of departments together with the total count."""
        rows = await self._session.scalars(
            select(Department).order_by(Department.id).limit(limit).offset(offset)
        )
        items = [DepartmentRead.model_validate(row) for row in rows]
        total = await self._session.scalar(select(func.count()).select_from(Department))
        return items, total or 0

    @database
    async def get_or_create_by_code(self, code: str, name: str) -> DepartmentRead:
        """Return the department for code, creating it from a DX profile if new."""
        row = await self._session.scalar(select(Department).where(Department.code == code))
        if row is None:
            row = Department(code=code, name=name)
            self._session.add(row)
            await self._session.flush()
            await self._session.refresh(row)
        return DepartmentRead.model_validate(row)
