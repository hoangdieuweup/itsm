"""Single access path to the projects, project_links, and environments tables."""

from abc import abstractmethod
from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.markers import database, helper
from app.core.base.repository import AbstractRepository
from app.core.models import FrozenModel
from app.integrations.cache.client import CacheClient
from app.modules.projects.constants import EnvironmentType, ProjectLinkType, ProjectsCacheKeys
from app.modules.projects.models import (
    Environment,
    Project,
    ProjectLink,
    ProjectMember,
    ProjectRole,
    ProjectRolePermission,
)
from app.modules.projects.schemas import EnvironmentRead, ProjectLinkRead, ProjectRead


class ProjectMemberRow(FrozenModel):
    """Raw membership row — no email/name (the repository has no cross-module
    knowledge of users; enrichment happens in the service layer via UsersApi)."""

    project_id: UUID
    user_id: UUID
    created_at: datetime
    project_role_id: UUID | None = None


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


class AbstractProjectRepository(AbstractRepository[ProjectRead, UUID]):
    """Contract a use case depends on instead of the concrete SQLAlchemy class below."""

    @abstractmethod
    async def create(self, *, name: str, description: str | None, created_by: UUID | None) -> ProjectRead:
        """Create a new project."""
        raise NotImplementedError

    @abstractmethod
    async def update(self, project_id: UUID, *, name: str | None, description: str | None) -> ProjectRead:
        """Rename and/or redescribe a project. None means unchanged."""
        raise NotImplementedError

    @abstractmethod
    async def delete(self, project_id: UUID) -> None:
        """Delete a project. Cascades to its environments and links at the DB level."""
        raise NotImplementedError

    @abstractmethod
    async def list_for_ids(self, project_ids: list[UUID]) -> list[ProjectRead]:
        """Return every project whose id is in project_ids, in no particular
        order — backs the membership-filtered GET /projects list."""
        raise NotImplementedError


class ProjectRepository(AbstractProjectRepository):
    """SQLAlchemy implementation. Every read/write of the projects table goes through this class."""

    def __init__(self, session: AsyncSession, cache: CacheClient) -> None:
        self._session = session
        self._cache = cache

    @database
    async def get_by_id(self, entity_id: UUID) -> ProjectRead | None:
        """Return one project, or None when it does not exist. Cache-aside."""
        return await self._cache.get_or_load(
            ProjectsCacheKeys.PROJECT_ENTITY, entity_id, ProjectRead, lambda: self._load_by_id(entity_id)
        )

    @helper
    async def _load_by_id(self, entity_id: UUID) -> ProjectRead | None:
        """Direct database read backing get_by_id's cache-aside loader."""
        row = await self._session.scalar(select(Project).where(Project.id == entity_id))
        return ProjectRead.model_validate(row) if row else None

    @database
    async def list_page(self, limit: int, offset: int) -> tuple[list[ProjectRead], int]:
        """Return one page of projects together with the total count."""
        rows = await self._session.scalars(select(Project).order_by(Project.id).limit(limit).offset(offset))
        items = [ProjectRead.model_validate(row) for row in rows]
        total = await self._session.scalar(select(func.count()).select_from(Project))
        return items, total or 0

    @database
    async def create(self, *, name: str, description: str | None, created_by: UUID | None) -> ProjectRead:
        """Create a new project."""
        row = Project(name=name, description=description, created_by=created_by)
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return ProjectRead.model_validate(row)

    @database
    async def update(self, project_id: UUID, *, name: str | None, description: str | None) -> ProjectRead:
        """Rename and/or redescribe a project. Caller must confirm project_id exists first."""
        row = await self._session.get(Project, project_id)
        if row is None:
            raise ValueError(f"project {project_id} does not exist")
        if name is not None:
            row.name = name
        if description is not None:
            row.description = description
        await self._session.flush()
        await self._session.refresh(row)
        return ProjectRead.model_validate(row)

    @database
    async def delete(self, project_id: UUID) -> None:
        """Delete a project. Caller must confirm project_id exists first."""
        row = await self._session.get(Project, project_id)
        if row is not None:
            await self._session.delete(row)
            await self._session.flush()

    @database
    async def list_for_ids(self, project_ids: list[UUID]) -> list[ProjectRead]:
        """Return every project whose id is in project_ids."""
        if not project_ids:
            return []
        rows = await self._session.scalars(select(Project).where(Project.id.in_(project_ids)))
        return [ProjectRead.model_validate(row) for row in rows]


class AbstractEnvironmentRepository(AbstractRepository[EnvironmentRead, UUID]):
    """Contract a use case depends on instead of the concrete SQLAlchemy class below."""

    @abstractmethod
    async def list_for_project(self, project_id: UUID) -> list[EnvironmentRead]:
        """Return every environment belonging to a project."""
        raise NotImplementedError

    @abstractmethod
    async def find_by_project_and_type(
        self, project_id: UUID, env_type: EnvironmentType
    ) -> EnvironmentRead | None:
        """Look up an environment by its (project_id, type) unique key."""
        raise NotImplementedError

    @abstractmethod
    async def create(
        self, *, project_id: UUID, type: EnvironmentType, name: str, base_url: str | None
    ) -> EnvironmentRead:
        """Create a new environment."""
        raise NotImplementedError

    @abstractmethod
    async def update(
        self, environment_id: UUID, *, name: str | None, base_url: str | None
    ) -> EnvironmentRead:
        """Rename and/or re-point an environment. type is immutable."""
        raise NotImplementedError

    @abstractmethod
    async def delete(self, environment_id: UUID) -> None:
        """Delete an environment."""
        raise NotImplementedError


class EnvironmentRepository(AbstractEnvironmentRepository):
    """SQLAlchemy implementation. Every read/write of the environments table goes through this class."""

    def __init__(self, session: AsyncSession, cache: CacheClient) -> None:
        self._session = session
        self._cache = cache

    @database
    async def get_by_id(self, entity_id: UUID) -> EnvironmentRead | None:
        """Return one environment, or None when it does not exist. Cache-aside."""
        return await self._cache.get_or_load(
            ProjectsCacheKeys.ENVIRONMENT_ENTITY,
            entity_id,
            EnvironmentRead,
            lambda: self._load_by_id(entity_id),
        )

    @helper
    async def _load_by_id(self, entity_id: UUID) -> EnvironmentRead | None:
        """Direct database read backing get_by_id's cache-aside loader."""
        row = await self._session.scalar(select(Environment).where(Environment.id == entity_id))
        return EnvironmentRead.model_validate(row) if row else None

    @database
    async def list_page(self, limit: int, offset: int) -> tuple[list[EnvironmentRead], int]:
        """Required by AbstractRepository; environments are listed per-project
        in practice (list_for_project)."""
        rows = await self._session.scalars(
            select(Environment).order_by(Environment.id).limit(limit).offset(offset)
        )
        items = [EnvironmentRead.model_validate(row) for row in rows]
        total = await self._session.scalar(select(func.count()).select_from(Environment))
        return items, total or 0

    @database
    async def list_for_project(self, project_id: UUID) -> list[EnvironmentRead]:
        """Return every environment belonging to a project."""
        rows = await self._session.scalars(
            select(Environment).where(Environment.project_id == project_id).order_by(Environment.type)
        )
        return [EnvironmentRead.model_validate(row) for row in rows]

    @database
    async def find_by_project_and_type(
        self, project_id: UUID, env_type: EnvironmentType
    ) -> EnvironmentRead | None:
        """Look up an environment by its (project_id, type) unique key."""
        row = await self._session.scalar(
            select(Environment).where(Environment.project_id == project_id, Environment.type == env_type)
        )
        return EnvironmentRead.model_validate(row) if row else None

    @database
    async def create(
        self, *, project_id: UUID, type: EnvironmentType, name: str, base_url: str | None
    ) -> EnvironmentRead:
        """Create a new environment. Caller must confirm no (project_id, type) collision first."""
        row = Environment(project_id=project_id, type=type, name=name, base_url=base_url)
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return EnvironmentRead.model_validate(row)

    @database
    async def update(
        self, environment_id: UUID, *, name: str | None, base_url: str | None
    ) -> EnvironmentRead:
        """Rename and/or re-point an environment. Caller must confirm environment_id exists first."""
        row = await self._session.get(Environment, environment_id)
        if row is None:
            raise ValueError(f"environment {environment_id} does not exist")
        if name is not None:
            row.name = name
        if base_url is not None:
            row.base_url = base_url
        await self._session.flush()
        await self._session.refresh(row)
        return EnvironmentRead.model_validate(row)

    @database
    async def delete(self, environment_id: UUID) -> None:
        """Delete an environment. Caller must confirm environment_id exists first."""
        row = await self._session.get(Environment, environment_id)
        if row is not None:
            await self._session.delete(row)
            await self._session.flush()


class AbstractProjectLinkRepository(AbstractRepository[ProjectLinkRead, UUID]):
    """Contract a use case depends on instead of the concrete SQLAlchemy class below."""

    @abstractmethod
    async def list_for_project(self, project_id: UUID) -> list[ProjectLinkRead]:
        """Return every link belonging to a project."""
        raise NotImplementedError

    @abstractmethod
    async def create(
        self, *, project_id: UUID, type: ProjectLinkType, name: str, url: str, is_default: bool
    ) -> ProjectLinkRead:
        """Create a new project link."""
        raise NotImplementedError

    @abstractmethod
    async def update(self, link_id: UUID, *, name: str | None, url: str | None) -> ProjectLinkRead:
        """Rename and/or re-point a link. type/is_default are immutable after creation."""
        raise NotImplementedError

    @abstractmethod
    async def delete(self, link_id: UUID) -> None:
        """Delete a project link."""
        raise NotImplementedError


class ProjectLinkRepository(AbstractProjectLinkRepository):
    """SQLAlchemy implementation. Every read/write of the project_links table goes through this class."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @database
    async def get_by_id(self, entity_id: UUID) -> ProjectLinkRead | None:
        """Return one link, or None when it does not exist. Not cached — links are read in small,
        already-cheap per-project batches (list_for_project), never hot single-row lookups."""
        row = await self._session.get(ProjectLink, entity_id)
        return ProjectLinkRead.model_validate(row) if row else None

    @database
    async def list_page(self, limit: int, offset: int) -> tuple[list[ProjectLinkRead], int]:
        """Required by AbstractRepository; links are listed per-project in practice (list_for_project)."""
        rows = await self._session.scalars(
            select(ProjectLink).order_by(ProjectLink.id).limit(limit).offset(offset)
        )
        items = [ProjectLinkRead.model_validate(row) for row in rows]
        total = await self._session.scalar(select(func.count()).select_from(ProjectLink))
        return items, total or 0

    @database
    async def list_for_project(self, project_id: UUID) -> list[ProjectLinkRead]:
        """Return every link belonging to a project."""
        rows = await self._session.scalars(
            select(ProjectLink).where(ProjectLink.project_id == project_id).order_by(ProjectLink.created_at)
        )
        return [ProjectLinkRead.model_validate(row) for row in rows]

    @database
    async def create(
        self, *, project_id: UUID, type: ProjectLinkType, name: str, url: str, is_default: bool
    ) -> ProjectLinkRead:
        """Create a new project link."""
        row = ProjectLink(project_id=project_id, type=type, name=name, url=url, is_default=is_default)
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return ProjectLinkRead.model_validate(row)

    @database
    async def update(self, link_id: UUID, *, name: str | None, url: str | None) -> ProjectLinkRead:
        """Rename and/or re-point a link. Caller must confirm link_id exists first."""
        row = await self._session.get(ProjectLink, link_id)
        if row is None:
            raise ValueError(f"project link {link_id} does not exist")
        if name is not None:
            row.name = name
        if url is not None:
            row.url = url
        await self._session.flush()
        await self._session.refresh(row)
        return ProjectLinkRead.model_validate(row)

    @database
    async def delete(self, link_id: UUID) -> None:
        """Delete a project link. Caller must confirm link_id exists first."""
        row = await self._session.get(ProjectLink, link_id)
        if row is not None:
            await self._session.delete(row)
            await self._session.flush()


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

    @database
    async def get_by_id(self, entity_id: UUID) -> ProjectRoleRow | None:
        return await self._load_by_id(entity_id)

    @database
    async def list_page(self, limit: int, offset: int) -> tuple[list[ProjectRoleRow], int]:
        rows = await self._session.scalars(
            select(ProjectRole).order_by(ProjectRole.id).limit(limit).offset(offset)
        )
        items = [await self._load_by_id(row.id) for row in rows]
        total = await self._session.scalar(select(func.count()).select_from(ProjectRole))
        return [i for i in items if i is not None], total or 0

    @database
    async def list_for_project(self, project_id: UUID) -> list[ProjectRoleRow]:
        rows = await self._session.scalars(
            select(ProjectRole).where(ProjectRole.project_id == project_id).order_by(ProjectRole.name)
        )
        results = [await self._load_by_id(row.id) for row in rows]
        return [r for r in results if r is not None]

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
            raise ValueError(f"project role {project_role_id} does not exist")
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
