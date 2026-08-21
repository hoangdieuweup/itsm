"""Single access path to the rbac tables (roles, permissions, role_permissions, user_roles)."""

from abc import ABC, abstractmethod

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.base.markers import database
from app.core.base.repository import AbstractRepository
from app.modules.rbac.models import Permission, Role, RolePermission, UserRole
from app.modules.rbac.schemas import PermissionRead, RoleRead


class AbstractRoleRepository(AbstractRepository[RoleRead]):
    """Contract a use case depends on instead of the concrete SQLAlchemy class below."""

    @abstractmethod
    async def find_by_name(self, name: str) -> RoleRead | None:
        """Look up a role by its unique name."""
        raise NotImplementedError

    @abstractmethod
    async def create(self, *, name: str, is_system: bool, permission_ids: list[int]) -> RoleRead:
        """Create a role with an initial permission set."""
        raise NotImplementedError

    @abstractmethod
    async def update(self, role_id: int, *, name: str | None, permission_ids: list[int] | None) -> RoleRead:
        """Rename and/or replace a role's permission set. None means unchanged."""
        raise NotImplementedError

    @abstractmethod
    async def delete(self, role_id: int) -> None:
        """Delete a role. Caller is responsible for the is_system/in-use checks."""
        raise NotImplementedError

    @abstractmethod
    async def count_users_with_role(self, role_id: int) -> int:
        """Count how many users currently hold this role."""
        raise NotImplementedError


class RoleRepository(AbstractRoleRepository):
    """SQLAlchemy implementation. Every read/write of roles+role_permissions goes through this class."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _get(self, role_id: int) -> Role | None:
        return await self._session.scalar(
            select(Role).options(selectinload(Role.permissions)).where(Role.id == role_id)
        )

    @database
    async def get_by_id(self, entity_id: int) -> RoleRead | None:
        """Return one role with its permissions, or None when it does not exist."""
        row = await self._get(entity_id)
        return RoleRead.model_validate(row) if row else None

    @database
    async def find_by_name(self, name: str) -> RoleRead | None:
        """Look up a role by its unique name."""
        row = await self._session.scalar(
            select(Role).options(selectinload(Role.permissions)).where(Role.name == name)
        )
        return RoleRead.model_validate(row) if row else None

    @database
    async def list_page(self, limit: int, offset: int) -> tuple[list[RoleRead], int]:
        """Return one page of roles, each with its permissions, plus the total count."""
        rows = await self._session.scalars(
            select(Role).options(selectinload(Role.permissions)).order_by(Role.id).limit(limit).offset(offset)
        )
        items = [RoleRead.model_validate(row) for row in rows]
        total = await self._session.scalar(select(func.count()).select_from(Role))
        return items, total or 0

    @database
    async def create(self, *, name: str, is_system: bool, permission_ids: list[int]) -> RoleRead:
        """Create a role with an initial permission set."""
        row = Role(name=name, is_system=is_system)
        self._session.add(row)
        await self._session.flush()
        for permission_id in permission_ids:
            self._session.add(RolePermission(role_id=row.id, permission_id=permission_id))
        await self._session.flush()
        result = await self.get_by_id(row.id)
        assert result is not None  # the row we just inserted always exists
        return result

    @database
    async def update(self, role_id: int, *, name: str | None, permission_ids: list[int] | None) -> RoleRead:
        """Rename and/or replace a role's permission set. None means unchanged."""
        row = await self._session.get(Role, role_id)
        if row is None:
            raise ValueError(f"role {role_id} does not exist")
        if name is not None:
            row.name = name
        if permission_ids is not None:
            await self._session.execute(delete(RolePermission).where(RolePermission.role_id == role_id))
            for permission_id in permission_ids:
                self._session.add(RolePermission(role_id=role_id, permission_id=permission_id))
        await self._session.flush()
        result = await self.get_by_id(role_id)
        assert result is not None  # role_id was already confirmed to exist above
        return result

    @database
    async def delete(self, role_id: int) -> None:
        """Delete a role. Caller is responsible for the is_system/in-use checks."""
        row = await self._session.get(Role, role_id)
        if row is not None:
            await self._session.delete(row)
            await self._session.flush()

    @database
    async def count_users_with_role(self, role_id: int) -> int:
        """Count how many users currently hold this role."""
        total = await self._session.scalar(
            select(func.count()).select_from(UserRole).where(UserRole.role_id == role_id)
        )
        return total or 0


class AbstractPermissionRepository(AbstractRepository[PermissionRead]):
    """Contract a use case depends on instead of the concrete SQLAlchemy class below."""

    @abstractmethod
    async def list_all(self) -> list[PermissionRead]:
        """Return the full permission catalog, unpaginated (it's small and fixed)."""
        raise NotImplementedError

    @abstractmethod
    async def find_by_ids(self, ids: list[int]) -> list[PermissionRead]:
        """Return the permissions matching the given ids (fewer than requested if some don't exist)."""
        raise NotImplementedError


class PermissionRepository(AbstractPermissionRepository):
    """SQLAlchemy implementation. Read-only — the catalog is written only by the seed script."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @database
    async def get_by_id(self, entity_id: int) -> PermissionRead | None:
        """Return one permission, or None when it does not exist."""
        row = await self._session.get(Permission, entity_id)
        return PermissionRead.model_validate(row) if row else None

    @database
    async def list_page(self, limit: int, offset: int) -> tuple[list[PermissionRead], int]:
        """Return one page of the permission catalog together with the total count."""
        rows = await self._session.scalars(
            select(Permission).order_by(Permission.id).limit(limit).offset(offset)
        )
        items = [PermissionRead.model_validate(row) for row in rows]
        total = await self._session.scalar(select(func.count()).select_from(Permission))
        return items, total or 0

    @database
    async def list_all(self) -> list[PermissionRead]:
        """Return the full permission catalog, unpaginated (it's small and fixed)."""
        rows = await self._session.scalars(
            select(Permission).order_by(Permission.resource, Permission.action)
        )
        return [PermissionRead.model_validate(row) for row in rows]

    @database
    async def find_by_ids(self, ids: list[int]) -> list[PermissionRead]:
        """Return the permissions matching the given ids (fewer than requested if some don't exist)."""
        if not ids:
            return []
        rows = await self._session.scalars(select(Permission).where(Permission.id.in_(ids)))
        return [PermissionRead.model_validate(row) for row in rows]


class AbstractUserRoleRepository(ABC):
    """Contract for the single-role-per-user grant. Not an AbstractRepository[T]: this
    store is one row per user with no listing use case, the same shape as
    app.integrations.dx_core.repository.AbstractDxTokenRepository — see that file's
    docstring for why forcing get_by_id/list_page here would add nothing."""

    @abstractmethod
    async def get_role_for_user(self, user_id: int) -> RoleRead | None:
        """Return the role currently granted to a user, or None if never assigned."""
        raise NotImplementedError

    @abstractmethod
    async def assign(self, user_id: int, role_id: int) -> None:
        """Upsert a user's single role grant."""
        raise NotImplementedError

    @abstractmethod
    async def user_has_permission(self, user_id: int, resource: str, action: str) -> bool:
        """Return whether user_id's granted role includes resource.action."""
        raise NotImplementedError


class UserRoleRepository(AbstractUserRoleRepository):
    """SQLAlchemy implementation. Every read/write of user_roles goes through this class."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @database
    async def get_role_for_user(self, user_id: int) -> RoleRead | None:
        """Return the role currently granted to a user, or None if never assigned."""
        row = await self._session.scalar(
            select(Role)
            .join(UserRole, UserRole.role_id == Role.id)
            .options(selectinload(Role.permissions))
            .where(UserRole.user_id == user_id)
        )
        return RoleRead.model_validate(row) if row else None

    @database
    async def assign(self, user_id: int, role_id: int) -> None:
        """Upsert a user's single role grant."""
        row = await self._session.get(UserRole, user_id)
        if row is None:
            self._session.add(UserRole(user_id=user_id, role_id=role_id))
        else:
            row.role_id = role_id
        await self._session.flush()

    @database
    async def user_has_permission(self, user_id: int, resource: str, action: str) -> bool:
        """Return whether user_id's granted role includes resource.action."""
        stmt = (
            select(Permission.id)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(Role, Role.id == RolePermission.role_id)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id, Permission.resource == resource, Permission.action == action)
        )
        result = await self._session.execute(stmt)
        return result.first() is not None
