"""Single access path to the rbac tables (roles, permissions, role_permissions, user_roles)."""

import asyncio
from abc import ABC, abstractmethod
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.base.markers import database, helper
from app.core.base.repository import AbstractRepository
from app.integrations.cache.client import CacheClient
from app.modules.rbac.constants import RbacCacheKeys
from app.modules.rbac.exceptions import RoleNotFound
from app.modules.rbac.models import Permission, Role, RolePermission, UserRole
from app.modules.rbac.schemas import PermissionRead, RoleRead


class AbstractRoleRepository(AbstractRepository[RoleRead, UUID]):
    """Contract a use case depends on instead of the concrete SQLAlchemy class below."""

    @abstractmethod
    async def find_by_name(self, name: str) -> RoleRead | None:
        """Look up a role by its unique name."""
        raise NotImplementedError

    @abstractmethod
    async def create(self, *, name: str, is_system: bool, permission_ids: list[UUID]) -> RoleRead:
        """Create a role with an initial permission set."""
        raise NotImplementedError

    @abstractmethod
    async def update(self, role_id: UUID, *, name: str | None, permission_ids: list[UUID] | None) -> RoleRead:
        """Rename and/or replace a role's permission set. None means unchanged."""
        raise NotImplementedError

    @abstractmethod
    async def delete(self, role_id: UUID) -> None:
        """Delete a role. Caller is responsible for the is_system/in-use checks."""
        raise NotImplementedError

    @abstractmethod
    async def count_users_with_role(self, role_id: UUID) -> int:
        """Count how many users currently hold this role."""
        raise NotImplementedError


class RoleRepository(AbstractRoleRepository):
    """SQLAlchemy implementation. Every read/write of roles+role_permissions goes through this class."""

    def __init__(self, session: AsyncSession, cache: CacheClient) -> None:
        self._session = session
        self._cache = cache

    @helper
    async def _get(self, role_id: UUID) -> Role | None:
        return await self._session.scalar(
            select(Role).options(selectinload(Role.permissions)).where(Role.id == role_id)
        )

    @database
    async def get_by_id(self, entity_id: UUID) -> RoleRead | None:
        """Return one role with its permissions, or None when it does not
        exist. Cache-aside: a miss loads from the database and populates
        the cache."""
        return await self._cache.get_or_load(
            RbacCacheKeys.ROLE_ENTITY, entity_id, RoleRead, lambda: self._load_by_id(entity_id)
        )

    @helper
    async def _load_by_id(self, entity_id: UUID) -> RoleRead | None:
        """Direct database read backing get_by_id's cache-aside loader."""
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
    async def create(self, *, name: str, is_system: bool, permission_ids: list[UUID]) -> RoleRead:
        """Create a role with an initial permission set."""
        row = Role(name=name, is_system=is_system)
        self._session.add(row)
        await self._session.flush()
        for permission_id in permission_ids:
            self._session.add(RolePermission(role_id=row.id, permission_id=permission_id))
        await self._session.flush()
        result = await self._load_by_id(row.id)
        assert result is not None  # the row we just inserted always exists
        return result

    @database
    async def update(self, role_id: UUID, *, name: str | None, permission_ids: list[UUID] | None) -> RoleRead:
        """Rename and/or replace a role's permission set. None means unchanged."""
        row = await self._session.get(Role, role_id)
        if row is None:
            raise RoleNotFound()
        if name is not None:
            row.name = name
        if permission_ids is not None:
            await self._session.execute(delete(RolePermission).where(RolePermission.role_id == role_id))
            for permission_id in permission_ids:
                self._session.add(RolePermission(role_id=role_id, permission_id=permission_id))
        await self._session.flush()
        # Reads fresh, not via the cached get_by_id: the cache for role_id isn't
        # invalidated until the caller's uow.commit() runs after this returns —
        # using get_by_id here could hand back stale pre-update data.
        result = await self._load_by_id(role_id)
        assert result is not None  # role_id was already confirmed to exist above
        return result

    @database
    async def delete(self, role_id: UUID) -> None:
        """Delete a role. Caller is responsible for the is_system/in-use checks."""
        row = await self._session.get(Role, role_id)
        if row is not None:
            await self._session.delete(row)
            await self._session.flush()

    @database
    async def count_users_with_role(self, role_id: UUID) -> int:
        """Count how many users currently hold this role."""
        total = await self._session.scalar(
            select(func.count()).select_from(UserRole).where(UserRole.role_id == role_id)
        )
        return total or 0


class AbstractPermissionRepository(AbstractRepository[PermissionRead, UUID]):
    """Contract a use case depends on instead of the concrete SQLAlchemy class below."""

    @abstractmethod
    async def list_all(self) -> list[PermissionRead]:
        """Return the full permission catalog, unpaginated (it's small and fixed)."""
        raise NotImplementedError

    @abstractmethod
    async def find_by_ids(self, ids: list[UUID]) -> list[PermissionRead]:
        """Return the permissions matching the given ids (fewer than requested if some don't exist)."""
        raise NotImplementedError


class PermissionRepository(AbstractPermissionRepository):
    """SQLAlchemy implementation. Read-only — the catalog is written only by the seed script."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @database
    async def get_by_id(self, entity_id: UUID) -> PermissionRead | None:
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
    async def find_by_ids(self, ids: list[UUID]) -> list[PermissionRead]:
        """Return the permissions matching the given ids (fewer than requested if some don't exist)."""
        if not ids:
            return []
        rows = await self._session.scalars(select(Permission).where(Permission.id.in_(ids)))
        return [PermissionRead.model_validate(row) for row in rows]


class AbstractUserRoleRepository(ABC):
    """Contract for user role grants supporting multiple roles per user."""

    @abstractmethod
    async def get_roles_for_user(self, user_id: UUID) -> list[RoleRead]:
        """Return all roles currently granted to a user, or empty list if none."""
        raise NotImplementedError

    @abstractmethod
    async def get_role_for_user(self, user_id: UUID) -> RoleRead | None:
        """Return the primary role currently granted to a user, or None if none."""
        raise NotImplementedError

    @abstractmethod
    async def get_roles_for_users(self, user_ids: list[UUID]) -> dict[UUID, list[str]]:
        """Return a mapping of user_id -> list[role_name] for a batch of users."""
        raise NotImplementedError

    @abstractmethod
    async def assign_roles(self, user_id: UUID, role_ids: set[UUID] | list[UUID]) -> None:
        """Replace a user's role grants with the given set of role_ids atomically."""
        raise NotImplementedError

    @abstractmethod
    async def assign(self, user_id: UUID, role_id: UUID) -> None:
        """Assign a single role to user (backwards compatible helper)."""
        raise NotImplementedError

    @abstractmethod
    async def user_has_permission(self, user_id: UUID, resource: str, action: str) -> bool:
        """Return whether any of user_id's granted roles includes resource.action."""
        raise NotImplementedError


class UserRoleRepository(AbstractUserRoleRepository):
    """SQLAlchemy implementation. Every read/write of user_roles goes through this class."""

    def __init__(self, session: AsyncSession, cache: CacheClient) -> None:
        self._session = session
        self._cache = cache
        self._roles = RoleRepository(session, cache)

    @database
    async def get_roles_for_users(self, user_ids: list[UUID]) -> dict[UUID, list[str]]:
        """Return a mapping of user_id -> list[role_name] for a batch of users."""
        if not user_ids:
            return {}
        result = await self._session.execute(
            select(UserRole.user_id, Role.name)
            .join(Role, Role.id == UserRole.role_id)
            .where(UserRole.user_id.in_(user_ids))
        )
        mapping: dict[UUID, list[str]] = {uid: [] for uid in user_ids}
        for uid, rname in result.all():
            mapping[uid].append(rname)
        return mapping

    @database
    async def get_roles_for_user(self, user_id: UUID) -> list[RoleRead]:
        """Return all roles granted to user_id, each resolved through the cached RoleRepository."""
        role_ids = await self._load_role_ids_for_user(user_id)
        if not role_ids:
            return []
        roles = await asyncio.gather(*(self._roles.get_by_id(rid) for rid in role_ids))
        return [r for r in roles if r is not None]

    @database
    async def get_role_for_user(self, user_id: UUID) -> RoleRead | None:
        """Return the primary (first) role granted to user_id, or None if none."""
        roles = await self.get_roles_for_user(user_id)
        return roles[0] if roles else None

    @helper
    async def _load_role_ids_for_user(self, user_id: UUID) -> list[UUID]:
        """Direct database read of all role_ids assigned to user_id."""
        rows = await self._session.scalars(select(UserRole.role_id).where(UserRole.user_id == user_id))
        return list(rows)

    @database
    async def assign_roles(self, user_id: UUID, role_ids: set[UUID] | list[UUID]) -> None:
        """Replace a user's role grants with the given set of role_ids atomically."""
        target_ids = set(role_ids)
        current_ids = set(await self._load_role_ids_for_user(user_id))

        to_remove = current_ids - target_ids
        to_add = target_ids - current_ids

        if to_remove:
            await self._session.execute(
                delete(UserRole).where(UserRole.user_id == user_id, UserRole.role_id.in_(to_remove))
            )
        for rid in to_add:
            self._session.add(UserRole(user_id=user_id, role_id=rid))
        await self._session.flush()

    @database
    async def assign(self, user_id: UUID, role_id: UUID) -> None:
        """Assign a single role to user (backwards compatible helper)."""
        await self.assign_roles(user_id, {role_id})

    @database
    async def user_has_permission(self, user_id: UUID, resource: str, action: str) -> bool:
        """Return whether any of user_id's granted roles includes resource.action."""
        roles = await self.get_roles_for_user(user_id)
        for role in roles:
            if any(p.resource == resource and p.action == action for p in role.permissions):
                return True
        return False
