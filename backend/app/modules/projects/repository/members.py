"""Single access path to the project_members table."""

from abc import abstractmethod
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.markers import database
from app.core.base.repository import AbstractRepository
from app.core.models import FrozenModel
from app.modules.projects.models import (
    ProjectMember,
)


class ProjectMemberRow(FrozenModel):
    """Raw membership row — no email/name (the repository has no cross-module
    knowledge of users; enrichment happens in the service layer via UsersApi)."""

    project_id: UUID
    user_id: UUID
    created_at: datetime
    project_role_id: UUID | None = None


class AbstractProjectMemberRepository(AbstractRepository[ProjectMemberRow, tuple]):
    """Contract a use case depends on instead of the concrete SQLAlchemy class below."""

    @abstractmethod
    async def is_member(self, project_id: UUID, user_id: UUID) -> bool:
        """True if user_id has a membership row on project_id."""
        raise NotImplementedError

    @abstractmethod
    async def list_for_project(self, project_id: UUID) -> list[ProjectMemberRow]:
        """Return every membership row for one project."""
        raise NotImplementedError

    @abstractmethod
    async def list_project_ids_for_user(self, user_id: UUID) -> list[UUID]:
        """Return every project_id a user is a member of — backs the
        membership-filtered GET /projects list."""
        raise NotImplementedError

    @abstractmethod
    async def add(self, project_id: UUID, user_id: UUID) -> None:
        """Insert a membership row. Caller must confirm no existing row first."""
        raise NotImplementedError

    @abstractmethod
    async def remove(self, project_id: UUID, user_id: UUID) -> None:
        """Delete a membership row. A no-op if it does not exist."""
        raise NotImplementedError

    @abstractmethod
    async def set_project_role(self, project_id: UUID, user_id: UUID, project_role_id: UUID | None) -> None:
        """Assign or clear (None) a member's project-scoped role."""
        raise NotImplementedError


class ProjectMemberRepository(AbstractProjectMemberRepository):
    """SQLAlchemy implementation. Every read/write of the project_members table goes through this class."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @database
    async def get_by_id(self, entity_id: tuple) -> ProjectMemberRow | None:
        """Required by AbstractRepository; membership is looked up via
        is_member/list_for_project in practice, not by composite-key id."""
        project_id, user_id = entity_id
        row = await self._session.get(ProjectMember, (project_id, user_id))
        return ProjectMemberRow.model_validate(row) if row else None

    @database
    async def list_page(self, limit: int, offset: int) -> tuple[list[ProjectMemberRow], int]:
        """Required by AbstractRepository; membership is listed per-project
        in practice (list_for_project)."""
        rows = await self._session.scalars(
            select(ProjectMember).order_by(ProjectMember.created_at).limit(limit).offset(offset)
        )
        items = [ProjectMemberRow.model_validate(row) for row in rows]
        total = await self._session.scalar(select(func.count()).select_from(ProjectMember))
        return items, total or 0

    @database
    async def is_member(self, project_id: UUID, user_id: UUID) -> bool:
        """True if user_id has a membership row on project_id."""
        row = await self._session.get(ProjectMember, (project_id, user_id))
        return row is not None

    @database
    async def list_for_project(self, project_id: UUID) -> list[ProjectMemberRow]:
        """Return every membership row for one project."""
        rows = await self._session.scalars(
            select(ProjectMember)
            .where(ProjectMember.project_id == project_id)
            .order_by(ProjectMember.created_at)
        )
        return [ProjectMemberRow.model_validate(row) for row in rows]

    @database
    async def list_project_ids_for_user(self, user_id: UUID) -> list[UUID]:
        """Return every project_id a user is a member of."""
        rows = await self._session.scalars(
            select(ProjectMember.project_id).where(ProjectMember.user_id == user_id)
        )
        return list(rows)

    @database
    async def add(self, project_id: UUID, user_id: UUID) -> None:
        """Insert a membership row. Caller must confirm no existing row first."""
        self._session.add(ProjectMember(project_id=project_id, user_id=user_id))
        await self._session.flush()

    @database
    async def remove(self, project_id: UUID, user_id: UUID) -> None:
        """Delete a membership row. A no-op if it does not exist."""
        row = await self._session.get(ProjectMember, (project_id, user_id))
        if row is not None:
            await self._session.delete(row)
            await self._session.flush()

    @database
    async def set_project_role(self, project_id: UUID, user_id: UUID, project_role_id: UUID | None) -> None:
        """Assign or clear (None) a member's project-scoped role."""
        row = await self._session.get(ProjectMember, (project_id, user_id))
        if row is not None:
            row.project_role_id = project_role_id
            await self._session.flush()
