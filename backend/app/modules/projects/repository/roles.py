"""Single access path to the project_members, project_roles and project_role_permissions tables."""

from abc import abstractmethod
from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.markers import database, helper
from app.core.base.repository import AbstractRepository
from app.core.models import FrozenModel
from app.core.pagination import PageQuery
from app.modules.projects.exceptions import ProjectRoleNotFound
from app.modules.projects.models import (
    ProjectMember,
    ProjectRole,
    ProjectRolePermission,
)


class ProjectRoleRow(FrozenModel):
    """Raw project-role row — permission ids only, no description text
    (the repository has no cross-module knowledge of rbac; enrichment to
    PermissionRead happens in the service layer via RbacApi)."""

    id: UUID
    project_id: UUID
    name: str
    permission_ids: list[UUID]
    created_at: datetime
    updated_at: datetime


class AbstractProjectRoleRepository(AbstractRepository[ProjectRoleRow, UUID]):
    """Contract a use case depends on instead of the concrete SQLAlchemy class below."""

    @abstractmethod
    async def list_for_project(self, project_id: UUID) -> list[ProjectRoleRow]:
        raise NotImplementedError

    @abstractmethod
    async def find_by_name(self, project_id: UUID, name: str) -> ProjectRoleRow | None:
        raise NotImplementedError

    @abstractmethod
    async def create(self, *, project_id: UUID, name: str, permission_ids: list[UUID]) -> ProjectRoleRow:
        raise NotImplementedError

    @abstractmethod
    async def update(
        self, project_role_id: UUID, *, name: str | None, permission_ids: list[UUID] | None
    ) -> ProjectRoleRow:
        """None means unchanged; a non-None permission_ids REPLACES the set entirely (same
        replace-set semantics as rbac's RoleRepository.update)."""
        raise NotImplementedError

    @abstractmethod
    async def delete(self, project_role_id: UUID) -> None:
        raise NotImplementedError

    @abstractmethod
    async def permission_ids_for_member(self, project_id: UUID, user_id: UUID) -> list[UUID]:
        """The hot-path join: project_members -> project_role_permissions
        for this specific (project_id, user_id). Empty list if the member
        has no project_role_id or the role grants nothing."""
        raise NotImplementedError


class ProjectRoleRepository(AbstractProjectRoleRepository):
    """SQLAlchemy implementation. Every read/write of project_roles and
    project_role_permissions goes through this class — mirrors how
    RoleRepository owns both roles and role_permissions in rbac."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @helper
    async def _load_by_id(self, project_role_id: UUID) -> ProjectRoleRow | None:
        row = await self._session.get(ProjectRole, project_role_id)
        if row is None:
            return None
        perm_ids = await self._session.scalars(
            select(ProjectRolePermission.permission_id).where(
                ProjectRolePermission.project_role_id == project_role_id
            )
        )
        return ProjectRoleRow(
            id=row.id,
            project_id=row.project_id,
            name=row.name,
            permission_ids=list(perm_ids),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    @helper
    async def _load_many(self, rows: list[ProjectRole]) -> list[ProjectRoleRow]:
        """Batch counterpart of _load_by_id: one permission query for every
        row instead of one per row."""
        if not rows:
            return []
        links = await self._session.execute(
            select(ProjectRolePermission.project_role_id, ProjectRolePermission.permission_id).where(
                ProjectRolePermission.project_role_id.in_([row.id for row in rows])
            )
        )
        permission_ids: dict[UUID, list[UUID]] = {row.id: [] for row in rows}
        for project_role_id, permission_id in links:
            permission_ids[project_role_id].append(permission_id)
        return [
            ProjectRoleRow(
                id=row.id,
                project_id=row.project_id,
                name=row.name,
                permission_ids=permission_ids[row.id],
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        ]

    @database
    async def get_by_id(self, entity_id: UUID) -> ProjectRoleRow | None:
        return await self._load_by_id(entity_id)

    @database
    async def list_page(self, limit: int, offset: int) -> tuple[list[ProjectRoleRow], int]:
        rows, total = await PageQuery.fetch_rows(
            self._session,
            ProjectRole,
            limit=limit,
            offset=offset,
            order_by=ProjectRole.id,
        )
        return await self._load_many(rows), total

    @database
    async def list_for_project(self, project_id: UUID) -> list[ProjectRoleRow]:
        rows = list(
            await self._session.scalars(
                select(ProjectRole).where(ProjectRole.project_id == project_id).order_by(ProjectRole.name)
            )
        )
        return await self._load_many(rows)

    @database
    async def find_by_name(self, project_id: UUID, name: str) -> ProjectRoleRow | None:
        row = await self._session.scalar(
            select(ProjectRole).where(ProjectRole.project_id == project_id, ProjectRole.name == name)
        )
        return await self._load_by_id(row.id) if row else None

    @database
    async def create(self, *, project_id: UUID, name: str, permission_ids: list[UUID]) -> ProjectRoleRow:
        row = ProjectRole(project_id=project_id, name=name)
        self._session.add(row)
        await self._session.flush()
        for permission_id in permission_ids:
            self._session.add(ProjectRolePermission(project_role_id=row.id, permission_id=permission_id))
        await self._session.flush()
        result = await self._load_by_id(row.id)
        assert result is not None  # the row we just inserted always exists
        return result

    @database
    async def update(
        self, project_role_id: UUID, *, name: str | None, permission_ids: list[UUID] | None
    ) -> ProjectRoleRow:
        row = await self._session.get(ProjectRole, project_role_id)
        if row is None:
            raise ProjectRoleNotFound()
        if name is not None:
            row.name = name
        if permission_ids is not None:
            await self._session.execute(
                delete(ProjectRolePermission).where(ProjectRolePermission.project_role_id == project_role_id)
            )
            for permission_id in permission_ids:
                self._session.add(
                    ProjectRolePermission(project_role_id=project_role_id, permission_id=permission_id)
                )
        await self._session.flush()
        result = await self._load_by_id(project_role_id)
        assert result is not None  # project_role_id was already confirmed to exist above
        return result

    @database
    async def delete(self, project_role_id: UUID) -> None:
        row = await self._session.get(ProjectRole, project_role_id)
        if row is not None:
            await self._session.delete(row)
            await self._session.flush()

    @database
    async def permission_ids_for_member(self, project_id: UUID, user_id: UUID) -> list[UUID]:
        member = await self._session.get(ProjectMember, (project_id, user_id))
        if member is None or member.project_role_id is None:
            return []
        rows = await self._session.scalars(
            select(ProjectRolePermission.permission_id).where(
                ProjectRolePermission.project_role_id == member.project_role_id
            )
        )
        return list(rows)
