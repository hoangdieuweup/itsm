"""Single access path to the auth tables (users, departments)."""

from abc import abstractmethod

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import Department, User
from app.auth.schemas import DepartmentRead, UserRead
from app.markers import database
from app.repository import AbstractRepository


class AbstractUserRepository(AbstractRepository[UserRead]):
    """Contract a use case depends on instead of the concrete SQLAlchemy class below.

    get_by_id and list_page come from AbstractRepository; this adds the
    lookups specific to users. Upsert-from-DX-profile write methods belong
    to the SSO sync service (out of scope for this issue) and are added to
    this contract there.
    """

    @abstractmethod
    async def find_by_email(self, email: str) -> UserRead | None:
        """Look up a user by email."""
        raise NotImplementedError

    @abstractmethod
    async def find_by_external_id(self, external_user_id: str) -> UserRead | None:
        """Look up a user by the DX subject identifier."""
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


class AbstractDepartmentRepository(AbstractRepository[DepartmentRead]):
    """Contract a use case depends on instead of the concrete SQLAlchemy class below."""

    @abstractmethod
    async def find_by_code(self, code: str) -> DepartmentRead | None:
        """Look up a department by its DX code."""
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
