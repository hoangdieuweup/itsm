# DevOps Panel — Phase 1: Projects & Environments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the `projects` backend module (projects/project_links/environments) and its frontend counterpart — the foundation every later DevOps-panel phase (Cloudflare, observability, notifications, alerting) builds on.

**Architecture:** Backend: a new `app/modules/projects/` module following this repo's existing tier convention (constants→exceptions/schemas/models→config/rules→repository/uow→services→dependencies→router→public.py), same shape as `app/modules/users/`. Frontend: `entities/project` + `entities/environment` (promoted immediately — later phases read them) and `modules/projects` (CRUD UI), same shape as `entities/role` + `modules/roles`.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, pytest + testcontainers-postgres, Pydantic v2 — backend. Next.js App Router, TanStack Query, Zod, next-intl, Tailwind/shadcn — frontend (no test runner configured in this repo today — verified via `frontend/package.json`, so frontend tasks end in manual verification, not automated tests, matching existing practice rather than inventing one).

**Spec:** `docs/tasks/devops-control-panel-schema.md` (sections 1-2, 9) is the source spec. `/Users/hoangdieu/.claude/plans/rosy-juggling-pine.md` is the 11-phase master plan this is Phase 1 of.

## Global Constraints

- Every cross-module import goes through `public.py` (or a module's `constants.py` directly) — enforced by `python scripts/check_module_boundaries.py --strict`. Nothing in Phase 1 needs to import from `rbac`/`users`/`auth` except the router's `require_permission` dependency from `rbac.public`.
- Router functions are pure HTTP→use-case translation — no merging/formatting logic inline (this repo's own stated rule #10, actively enforced in review here).
- Every mutation service pre-checks existence and raises a domain exception (`ProjectNotFound`, etc.) *before* touching the repository's write path — never rely on a repository-level `ValueError` to produce a 404.
- camelCase on the wire is automatic via `FrozenModel`/`CustomModel` (`app/core/models.py`) — never hand-roll a wire schema without inheriting from one of them.
- `eslint-plugin-boundaries` blocks module→module imports outright on the frontend — `modules/projects` may only import from `entities/project`, `entities/environment`, and `shared/`.

## File Structure

**Backend — new files:**
```
backend/alembic/versions/<new_revision>_create_projects_schema.py
backend/app/modules/projects/
  __init__.py
  constants.py       # ProjectLimits, EnvironmentType, ProjectLinkType, ProjectsEvents, ProjectsCacheKeys, ErrorCode
  exceptions.py       # ProjectNotFound, EnvironmentNotFound, EnvironmentTypeAlreadyExists, ProjectLinkNotFound
  config.py            # ProjectsConfig (DEFAULT_JIRA_URL, DEFAULT_GIT_URL)
  schemas.py           # ProjectRead/Create/Update, EnvironmentRead/Create/Update, ProjectLinkRead/Create/Update
  models.py            # Project, ProjectLink, Environment ORM models
  rules.py             # ProjectsRules.default_links()
  repository.py        # ProjectRepository, EnvironmentRepository, ProjectLinkRepository
  uow.py               # ProjectsUnitOfWork
  dependencies.py      # get_uow
  public.py            # ProjectsApi facade (get_project_by_id, get_environment_by_id)
  router.py            # 13 endpoints
  services/
    __init__.py
    create_project.py
    update_project.py
    delete_project.py
    create_environment.py
    update_environment.py
    delete_environment.py
    create_project_link.py
    update_project_link.py
    delete_project_link.py
backend/tests/projects/
  __init__.py
  test_rules.py
  test_services.py
  test_router.py
```
**Backend — modified files:** `backend/app/main.py` (register router), `backend/app/modules/rbac/constants.py` (append 8 permission tuples), `backend/.importlinter` (new `projects-facade` contract).

**Frontend — new files:**
```
frontend/src/entities/project/
  index.ts
  model/schema.ts
  api/fetchers.ts
  api/query-keys.ts
frontend/src/entities/environment/
  index.ts
  model/schema.ts
  api/fetchers.ts
  api/query-keys.ts
frontend/src/modules/projects/
  index.ts
  api/fetchers.ts            # project_links fetchers only — project/environment reads live in entities
  hooks/use-create-project.ts
  hooks/use-update-project.ts
  hooks/use-delete-project.ts
  hooks/use-create-environment.ts
  hooks/use-update-environment.ts
  hooks/use-delete-environment.ts
  hooks/use-create-project-link.ts
  hooks/use-update-project-link.ts
  hooks/use-delete-project-link.ts
  ui/projects-page-content.tsx
  ui/project-form-dialog.tsx
  ui/project-detail-view.tsx    # environment tabs + links editor
  ui/environment-form-dialog.tsx
  ui/project-link-form-dialog.tsx
frontend/src/app/[locale]/(dashboard)/admin/projects/page.tsx
frontend/src/app/[locale]/(dashboard)/admin/projects/loading.tsx
frontend/src/app/[locale]/(dashboard)/admin/projects/[projectId]/page.tsx
frontend/src/app/[locale]/(dashboard)/admin/projects/[projectId]/loading.tsx
frontend/locales/en/modules/projects.json
frontend/locales/vi/modules/projects.json
```
**Frontend — modified files:** `shared/constants/routes.ts`, `shared/constants/permissions.ts`, `shared/constants/api.ts`, `shared/lib/i18n/request.ts`, `app/[locale]/(dashboard)/dashboard-sidebar.tsx`.

---

### Task 1: Alembic migration for `projects`, `project_links`, `environments`

**Files:**
- Create: `backend/alembic/versions/b6dd7c2f4a91_create_projects_schema.py`

**Interfaces:**
- Produces: tables `projects(id, name, description, created_by, created_at, updated_at)`, `project_links(id, project_id, type, name, url, is_default, created_at, updated_at)`, `environments(id, project_id, type, name, base_url, created_at, updated_at)` with `UNIQUE(project_id, type)` on `environments`.

- [ ] **Step 1: Write the migration**

```python
"""create_projects_schema

Revision ID: b6dd7c2f4a91
Revises: 4ecb44cf310b
Create Date: 2026-08-21 21:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'b6dd7c2f4a91'
down_revision = '4ecb44cf310b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('projects',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('projects_created_by_fkey'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('projects_pkey'))
    )
    op.create_table('project_links',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('project_id', sa.UUID(), nullable=False),
    sa.Column('type', sa.Enum('JIRA', 'GIT', 'OTHER', name='projectlinktype', native_enum=False), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('url', sa.Text(), nullable=False),
    sa.Column('is_default', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('project_links_project_id_fkey'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('project_links_pkey'))
    )
    op.create_index(op.f('project_links_project_id_idx'), 'project_links', ['project_id'], unique=False)
    op.create_table('environments',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('project_id', sa.UUID(), nullable=False),
    sa.Column('type', sa.Enum('DEV', 'STAGING', 'PRODUCTION', name='environmenttype', native_enum=False), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('base_url', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('environments_project_id_fkey'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('environments_pkey')),
    sa.UniqueConstraint('project_id', 'type', name='environments_project_id_type_key')
    )
    op.create_index(op.f('environments_project_id_idx'), 'environments', ['project_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('environments_project_id_idx'), table_name='environments')
    op.drop_table('environments')
    op.drop_index(op.f('project_links_project_id_idx'), table_name='project_links')
    op.drop_table('project_links')
    op.drop_table('projects')
```

- [ ] **Step 2: Run the migration against a local Postgres and verify both directions**

Run: `cd backend && alembic upgrade head` then `alembic downgrade -1` then `alembic upgrade head` again.
Expected: all three commands exit 0; after the final upgrade, `\dt` in `psql` shows `projects`, `project_links`, `environments`.

- [ ] **Step 3: Commit**

```bash
git add backend/alembic/versions/b6dd7c2f4a91_create_projects_schema.py
git commit -m "feat(projects): add projects/project_links/environments schema"
```

---

### Task 2: Module scaffolding — constants, exceptions, config, schemas, models

No independent test cycle (pure declarations); verified structurally by Task 3's rules test and Task 8's router tests importing them successfully.

**Files:**
- Create: `backend/app/modules/projects/__init__.py` (empty)
- Create: `backend/app/modules/projects/constants.py`
- Create: `backend/app/modules/projects/exceptions.py`
- Create: `backend/app/modules/projects/config.py`
- Create: `backend/app/modules/projects/schemas.py`
- Create: `backend/app/modules/projects/models.py`

**Interfaces:**
- Produces: `EnvironmentType`, `ProjectLinkType` (StrEnum, importable directly by later phases via `app.modules.projects.constants` — no `public.py` needed for enums per this repo's boundary rule), `ProjectRead`/`EnvironmentRead`/`ProjectLinkRead` (FrozenModel, wire schemas), `Project`/`Environment`/`ProjectLink` (SQLAlchemy models).

- [ ] **Step 1: `constants.py`**

```python
"""Constants and enums owned by the projects module."""

from enum import StrEnum


class ProjectLimits:
    """Numeric limits owned by the projects module."""

    MAX_NAME_LENGTH = 255
    MAX_LINK_NAME_LENGTH = 255
    MAX_ENVIRONMENT_NAME_LENGTH = 100
    DEFAULT_PAGE_SIZE = 50


class EnvironmentType(StrEnum):
    """The three deployment tiers a project can have — at most one of each,
    enforced by UNIQUE(project_id, type)."""

    DEV = "dev"
    STAGING = "staging"
    PRODUCTION = "production"


class ProjectLinkType(StrEnum):
    """External link kinds a project can carry."""

    JIRA = "jira"
    GIT = "git"
    OTHER = "other"


class ProjectsEvents:
    """Messaging identity owned by the projects module. See references/messaging.md."""

    EXCHANGE = "projects"


class ProjectsCacheKeys:
    """Cache identity owned by the projects module. See references/caching.md."""

    PROJECT_ENTITY = "project"
    ENVIRONMENT_ENTITY = "environment"
    TTL_SECONDS = 300


class ErrorCode(StrEnum):
    """Stable error codes returned to clients by this module."""

    PROJECT_NOT_FOUND = "projects_project_not_found"
    ENVIRONMENT_NOT_FOUND = "projects_environment_not_found"
    ENVIRONMENT_TYPE_ALREADY_EXISTS = "projects_environment_type_already_exists"
    PROJECT_LINK_NOT_FOUND = "projects_project_link_not_found"
```

- [ ] **Step 2: `exceptions.py`**

```python
"""Errors owned by the projects module."""

from app.core.exceptions import ConflictError, NotFoundError
from app.modules.projects.constants import ErrorCode


class ProjectNotFound(NotFoundError):
    """Raised when no project matches the requested id."""

    code = ErrorCode.PROJECT_NOT_FOUND
    message = "Project not found"


class EnvironmentNotFound(NotFoundError):
    """Raised when no environment matches the requested id."""

    code = ErrorCode.ENVIRONMENT_NOT_FOUND
    message = "Environment not found"


class EnvironmentTypeAlreadyExists(ConflictError):
    """Raised when a project already has an environment of the requested type."""

    code = ErrorCode.ENVIRONMENT_TYPE_ALREADY_EXISTS
    message = "This project already has an environment of that type"


class ProjectLinkNotFound(NotFoundError):
    """Raised when no project link matches the requested id."""

    code = ErrorCode.PROJECT_LINK_NOT_FOUND
    message = "Project link not found"
```

- [ ] **Step 3: `config.py`**

```python
"""Settings owned by the projects module."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class ProjectsConfig(BaseSettings):
    """Environment driven settings for the projects module.

    Both default to empty: an unconfigured URL means CreateProject attaches
    no default link of that kind, per ProjectsRules.default_links().
    """

    model_config = SettingsConfigDict(env_file=".env", env_prefix="PROJECTS__", extra="ignore")

    DEFAULT_JIRA_URL: str = ""
    DEFAULT_GIT_URL: str = ""


projects_settings = ProjectsConfig()
```

- [ ] **Step 4: `schemas.py`**

```python
"""Schemas for the projects module."""

from datetime import datetime
from uuid import UUID

from app.core.models import CustomModel, FrozenModel
from app.modules.projects.constants import EnvironmentType, ProjectLinkType


class ProjectRead(FrozenModel):
    """Representation safe to round trip through the cache."""

    id: UUID
    name: str
    description: str | None = None
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime


class ProjectCreate(CustomModel):
    """Request body for POST /projects."""

    name: str
    description: str | None = None


class ProjectUpdate(CustomModel):
    """Request body for PATCH /projects/{id}. None means unchanged."""

    name: str | None = None
    description: str | None = None


class EnvironmentRead(FrozenModel):
    """Representation safe to round trip through the cache."""

    id: UUID
    project_id: UUID
    type: EnvironmentType
    name: str
    base_url: str | None = None
    created_at: datetime
    updated_at: datetime


class EnvironmentCreate(CustomModel):
    """Request body for POST /projects/{project_id}/environments."""

    type: EnvironmentType
    name: str
    base_url: str | None = None


class EnvironmentUpdate(CustomModel):
    """Request body for PATCH /environments/{id}. type is immutable — the
    UNIQUE(project_id, type) constraint models a fixed tier, not a renameable one."""

    name: str | None = None
    base_url: str | None = None


class ProjectLinkRead(FrozenModel):
    """Representation safe to round trip through the cache."""

    id: UUID
    project_id: UUID
    type: ProjectLinkType
    name: str
    url: str
    is_default: bool
    created_at: datetime
    updated_at: datetime


class ProjectLinkCreate(CustomModel):
    """Request body for POST /projects/{project_id}/links."""

    type: ProjectLinkType
    name: str
    url: str


class ProjectLinkUpdate(CustomModel):
    """Request body for PATCH /links/{id}."""

    name: str | None = None
    url: str | None = None
```

- [ ] **Step 5: `models.py`**

```python
"""ORM models owned by the projects module. No other module may query these tables."""

from datetime import datetime
import uuid

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.modules.projects.constants import EnvironmentType, ProjectLimits, ProjectLinkType


class Project(Base):
    """A project, grouping environments and external links."""

    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(ProjectLimits.MAX_NAME_LENGTH))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ProjectLink(Base):
    """An external link (Jira/Git/other) attached to a project."""

    __tablename__ = "project_links"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[ProjectLinkType] = mapped_column(Enum(ProjectLinkType, native_enum=False))
    name: Mapped[str] = mapped_column(String(ProjectLimits.MAX_LINK_NAME_LENGTH))
    url: Mapped[str] = mapped_column(Text)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Environment(Base):
    """A DEV/STAGING/PRODUCTION deployment tier of a project. At most one per type per project."""

    __tablename__ = "environments"
    __table_args__ = (UniqueConstraint("project_id", "type", name="environments_project_id_type_key"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[EnvironmentType] = mapped_column(Enum(EnvironmentType, native_enum=False))
    name: Mapped[str] = mapped_column(String(ProjectLimits.MAX_ENVIRONMENT_NAME_LENGTH))
    base_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
```

- [ ] **Step 6: Sanity-check imports**

Run: `cd backend && python -c "from app.modules.projects import constants, exceptions, config, schemas, models"`
Expected: exits 0, no ImportError.

- [ ] **Step 7: Commit**

```bash
git add backend/app/modules/projects/__init__.py backend/app/modules/projects/constants.py backend/app/modules/projects/exceptions.py backend/app/modules/projects/config.py backend/app/modules/projects/schemas.py backend/app/modules/projects/models.py
git commit -m "feat(projects): scaffold constants, exceptions, config, schemas, models"
```

---

### Task 3: `rules.py` — default project links (TDD)

**Files:**
- Create: `backend/app/modules/projects/rules.py`
- Test: `backend/tests/projects/__init__.py` (empty), `backend/tests/projects/test_rules.py`

**Interfaces:**
- Consumes: `projects_settings` (Task 2).
- Produces: `ProjectsRules.default_links() -> list[tuple[ProjectLinkType, str, str]]` — consumed by Task 5's `CreateProject`.

- [ ] **Step 1: Write the failing test**

```python
"""Unit tests for app.modules.projects.rules — pure decisions, no I/O, no fixtures."""

from app.modules.projects.config import projects_settings
from app.modules.projects.constants import ProjectLinkType
from app.modules.projects.rules import ProjectsRules


class TestDefaultLinks:
    def test_returns_jira_and_git_when_both_configured(self, monkeypatch) -> None:
        monkeypatch.setattr(projects_settings, "DEFAULT_JIRA_URL", "https://jira.weup.vn")
        monkeypatch.setattr(projects_settings, "DEFAULT_GIT_URL", "https://git.weup.vn")

        links = ProjectsRules.default_links()

        assert links == [
            (ProjectLinkType.JIRA, "Jira", "https://jira.weup.vn"),
            (ProjectLinkType.GIT, "Git", "https://git.weup.vn"),
        ]

    def test_skips_jira_when_unconfigured(self, monkeypatch) -> None:
        monkeypatch.setattr(projects_settings, "DEFAULT_JIRA_URL", "")
        monkeypatch.setattr(projects_settings, "DEFAULT_GIT_URL", "https://git.weup.vn")

        links = ProjectsRules.default_links()

        assert links == [(ProjectLinkType.GIT, "Git", "https://git.weup.vn")]

    def test_returns_empty_when_neither_configured(self, monkeypatch) -> None:
        monkeypatch.setattr(projects_settings, "DEFAULT_JIRA_URL", "")
        monkeypatch.setattr(projects_settings, "DEFAULT_GIT_URL", "")

        assert ProjectsRules.default_links() == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/projects/test_rules.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.modules.projects.rules'`

- [ ] **Step 3: Write the implementation**

```python
"""Business rules for the projects module.

Everything here is a pure decision: no I/O, no framework, no database.
"""

from app.core.base.markers import rule
from app.modules.projects.config import projects_settings
from app.modules.projects.constants import ProjectLinkType


class ProjectsRules:
    """Every business decision about a project."""

    @staticmethod
    @rule
    def default_links() -> list[tuple[ProjectLinkType, str, str]]:
        """Return the (type, name, url) rows auto-attached to every new
        project — internal WeUp Jira/Git, marked is_default by the caller.
        An unconfigured URL means no default link of that kind, not a link
        pointing at an empty string."""
        candidates = [
            (ProjectLinkType.JIRA, "Jira", projects_settings.DEFAULT_JIRA_URL),
            (ProjectLinkType.GIT, "Git", projects_settings.DEFAULT_GIT_URL),
        ]
        return [(link_type, name, url) for link_type, name, url in candidates if url]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/projects/test_rules.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/projects/rules.py backend/tests/projects/__init__.py backend/tests/projects/test_rules.py
git commit -m "feat(projects): add default-links business rule"
```

---

### Task 4: `repository.py`, `uow.py`, `dependencies.py`

No independent test cycle — exercised end-to-end by Task 8's router tests (this repo's own convention: `tests/users/` and `tests/rbac/` have no standalone repository test files either, only `test_rules.py`/`test_services.py`/`test_router.py`).

**Files:**
- Create: `backend/app/modules/projects/repository.py`
- Create: `backend/app/modules/projects/uow.py`
- Create: `backend/app/modules/projects/dependencies.py`

**Interfaces:**
- Consumes: `AbstractRepository[EntityT, IdT]`, `AbstractUnitOfWork` (`app/core/base/`), `CacheClient` (`app/integrations/cache/client.py`), `get_session`/`get_cache` deps.
- Produces: `AbstractProjectsUnitOfWork` (with `.projects`, `.environments`, `.project_links` repos, `.mark_stale`, `.commit`, `.rollback`) — consumed by every Task 5-7 service and Task 8's router.

- [ ] **Step 1: `repository.py`**

```python
"""Single access path to the projects, project_links, and environments tables."""

from abc import abstractmethod
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.markers import database, helper
from app.core.base.repository import AbstractRepository
from app.integrations.cache.client import CacheClient
from app.modules.projects.constants import EnvironmentType, ProjectLinkType, ProjectsCacheKeys
from app.modules.projects.models import Environment, Project, ProjectLink
from app.modules.projects.schemas import EnvironmentRead, ProjectLinkRead, ProjectRead


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
    async def update(self, environment_id: UUID, *, name: str | None, base_url: str | None) -> EnvironmentRead:
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
            ProjectsCacheKeys.ENVIRONMENT_ENTITY, entity_id, EnvironmentRead, lambda: self._load_by_id(entity_id)
        )

    @helper
    async def _load_by_id(self, entity_id: UUID) -> EnvironmentRead | None:
        """Direct database read backing get_by_id's cache-aside loader."""
        row = await self._session.scalar(select(Environment).where(Environment.id == entity_id))
        return EnvironmentRead.model_validate(row) if row else None

    @database
    async def list_page(self, limit: int, offset: int) -> tuple[list[EnvironmentRead], int]:
        """Required by AbstractRepository; environments are listed per-project in practice (list_for_project)."""
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
    async def update(self, environment_id: UUID, *, name: str | None, base_url: str | None) -> EnvironmentRead:
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
```

- [ ] **Step 2: `uow.py`**

```python
"""Transaction boundary for the projects module."""

import logging
from abc import abstractmethod
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.markers import database
from app.core.base.uow import AbstractUnitOfWork
from app.integrations.cache.client import CacheClient
from app.modules.projects.repository import (
    AbstractEnvironmentRepository,
    AbstractProjectLinkRepository,
    AbstractProjectRepository,
    EnvironmentRepository,
    ProjectLinkRepository,
    ProjectRepository,
)

logger = logging.getLogger(__name__)


class AbstractProjectsUnitOfWork(AbstractUnitOfWork):
    """Contract a use case depends on instead of the concrete SQLAlchemy class below."""

    projects: AbstractProjectRepository
    environments: AbstractEnvironmentRepository
    project_links: AbstractProjectLinkRepository

    @abstractmethod
    def mark_stale(self, entity: str, entity_id: UUID) -> None:
        """Queue a cache entity for invalidation once THIS uow's own commit() runs."""
        raise NotImplementedError


class ProjectsUnitOfWork(AbstractProjectsUnitOfWork):
    """Owns the transaction for the projects module's tables."""

    def __init__(self, session: AsyncSession, cache: CacheClient) -> None:
        self._session = session
        self._cache = cache
        self._stale: list[tuple[str, UUID]] = []
        self.projects = ProjectRepository(session, cache)
        self.environments = EnvironmentRepository(session, cache)
        self.project_links = ProjectLinkRepository(session)

    def mark_stale(self, entity: str, entity_id: UUID) -> None:
        """Queue a cache entity for invalidation once this transaction commits."""
        self._stale.append((entity, entity_id))

    @database
    async def commit(self) -> None:
        """Commit the transaction, then invalidate every queued cache entity — strictly
        after the database commit, per references/caching.md#order-of-operations."""
        await self._session.commit()
        for entity, entity_id in self._stale:
            await self._cache.bump_version(entity, entity_id)
        self._stale.clear()

    @database
    async def rollback(self) -> None:
        """Roll back the transaction and drop any queued invalidation."""
        await self._session.rollback()
        self._stale.clear()
        logger.warning("projects unit of work rolled back")
```

- [ ] **Step 3: `dependencies.py`**

```python
"""Dependency wiring for the projects module. The composition root: the only
place that names a concrete class (ProjectsUnitOfWork) instead of its
Abstract* contract."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.integrations.cache.client import CacheClient
from app.integrations.cache.dependencies import get_cache
from app.modules.projects.uow import ProjectsUnitOfWork


async def get_uow(
    session: AsyncSession = Depends(get_session), cache: CacheClient = Depends(get_cache)
) -> ProjectsUnitOfWork:
    """Provide a request scoped unit of work. The one place the concrete class is named."""
    return ProjectsUnitOfWork(session, cache)
```

- [ ] **Step 4: Sanity-check imports**

Run: `cd backend && python -c "from app.modules.projects import repository, uow, dependencies"`
Expected: exits 0, no ImportError.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/projects/repository.py backend/app/modules/projects/uow.py backend/app/modules/projects/dependencies.py
git commit -m "feat(projects): add repository, unit of work, dependency wiring"
```

---

### Task 5: Project services — create/update/delete (TDD, Fake-based)

**Files:**
- Create: `backend/app/modules/projects/services/__init__.py` (empty), `create_project.py`, `update_project.py`, `delete_project.py`
- Create: `backend/tests/projects/test_services.py` (this task writes the `Project*` section; Tasks 6-7 append to the same file)

**Interfaces:**
- Consumes: `AbstractProjectsUnitOfWork` (Task 4), `ProjectsRules.default_links()` (Task 3), `ProjectNotFound` (Task 2).
- Produces: `CreateProject(uow).execute(name, description) -> ProjectRead`, `UpdateProject(uow).execute(project_id, *, name, description) -> ProjectRead`, `DeleteProject(uow).execute(project_id) -> None` — consumed by Task 8's router.

- [ ] **Step 1: Write the failing tests**

```python
"""Unit tests for app.modules.projects.services — Fake-based, no database."""

from uuid import UUID, uuid4

import pytest

from app.modules.projects.constants import EnvironmentType, ProjectLinkType
from app.modules.projects.exceptions import (
    EnvironmentNotFound,
    EnvironmentTypeAlreadyExists,
    ProjectLinkNotFound,
    ProjectNotFound,
)
from app.modules.projects.repository import (
    AbstractEnvironmentRepository,
    AbstractProjectLinkRepository,
    AbstractProjectRepository,
)
from app.modules.projects.schemas import EnvironmentRead, ProjectLinkRead, ProjectRead
from app.modules.projects.uow import AbstractProjectsUnitOfWork
from datetime import UTC, datetime


class FakeProjectRepository(AbstractProjectRepository):
    def __init__(self) -> None:
        self._rows: dict[UUID, ProjectRead] = {}

    async def get_by_id(self, entity_id: UUID) -> ProjectRead | None:
        return self._rows.get(entity_id)

    async def list_page(self, limit: int, offset: int) -> tuple[list[ProjectRead], int]:
        items = list(self._rows.values())[offset : offset + limit]
        return items, len(self._rows)

    async def create(self, *, name: str, description: str | None, created_by: UUID | None) -> ProjectRead:
        project = ProjectRead(
            id=uuid4(),
            name=name,
            description=description,
            created_by=created_by,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self._rows[project.id] = project
        return project

    async def update(self, project_id: UUID, *, name: str | None, description: str | None) -> ProjectRead:
        existing = self._rows[project_id]
        updated = existing.model_copy(
            update={
                "name": name if name is not None else existing.name,
                "description": description if description is not None else existing.description,
            }
        )
        self._rows[project_id] = updated
        return updated

    async def delete(self, project_id: UUID) -> None:
        self._rows.pop(project_id, None)


class FakeEnvironmentRepository(AbstractEnvironmentRepository):
    def __init__(self) -> None:
        self._rows: dict[UUID, EnvironmentRead] = {}

    async def get_by_id(self, entity_id: UUID) -> EnvironmentRead | None:
        return self._rows.get(entity_id)

    async def list_page(self, limit: int, offset: int) -> tuple[list[EnvironmentRead], int]:
        items = list(self._rows.values())[offset : offset + limit]
        return items, len(self._rows)

    async def list_for_project(self, project_id: UUID) -> list[EnvironmentRead]:
        return [e for e in self._rows.values() if e.project_id == project_id]

    async def find_by_project_and_type(
        self, project_id: UUID, env_type: EnvironmentType
    ) -> EnvironmentRead | None:
        return next(
            (e for e in self._rows.values() if e.project_id == project_id and e.type == env_type), None
        )

    async def create(
        self, *, project_id: UUID, type: EnvironmentType, name: str, base_url: str | None
    ) -> EnvironmentRead:
        env = EnvironmentRead(
            id=uuid4(),
            project_id=project_id,
            type=type,
            name=name,
            base_url=base_url,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self._rows[env.id] = env
        return env

    async def update(self, environment_id: UUID, *, name: str | None, base_url: str | None) -> EnvironmentRead:
        existing = self._rows[environment_id]
        updated = existing.model_copy(
            update={
                "name": name if name is not None else existing.name,
                "base_url": base_url if base_url is not None else existing.base_url,
            }
        )
        self._rows[environment_id] = updated
        return updated

    async def delete(self, environment_id: UUID) -> None:
        self._rows.pop(environment_id, None)


class FakeProjectLinkRepository(AbstractProjectLinkRepository):
    def __init__(self) -> None:
        self._rows: dict[UUID, ProjectLinkRead] = {}

    async def get_by_id(self, entity_id: UUID) -> ProjectLinkRead | None:
        return self._rows.get(entity_id)

    async def list_page(self, limit: int, offset: int) -> tuple[list[ProjectLinkRead], int]:
        items = list(self._rows.values())[offset : offset + limit]
        return items, len(self._rows)

    async def list_for_project(self, project_id: UUID) -> list[ProjectLinkRead]:
        return [link for link in self._rows.values() if link.project_id == project_id]

    async def create(
        self, *, project_id: UUID, type: ProjectLinkType, name: str, url: str, is_default: bool
    ) -> ProjectLinkRead:
        link = ProjectLinkRead(
            id=uuid4(),
            project_id=project_id,
            type=type,
            name=name,
            url=url,
            is_default=is_default,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self._rows[link.id] = link
        return link

    async def update(self, link_id: UUID, *, name: str | None, url: str | None) -> ProjectLinkRead:
        existing = self._rows[link_id]
        updated = existing.model_copy(
            update={
                "name": name if name is not None else existing.name,
                "url": url if url is not None else existing.url,
            }
        )
        self._rows[link_id] = updated
        return updated

    async def delete(self, link_id: UUID) -> None:
        self._rows.pop(link_id, None)


class FakeProjectsUnitOfWork(AbstractProjectsUnitOfWork):
    """In-memory unit of work. commit/rollback are no-ops that just count calls."""

    def __init__(self) -> None:
        self.projects = FakeProjectRepository()
        self.environments = FakeEnvironmentRepository()
        self.project_links = FakeProjectLinkRepository()
        self.commits = 0
        self.rollbacks = 0
        self.stale: list[tuple[str, UUID]] = []

    def mark_stale(self, entity: str, entity_id: UUID) -> None:
        self.stale.append((entity, entity_id))

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


from app.modules.projects.services.create_project import CreateProject
from app.modules.projects.services.update_project import UpdateProject
from app.modules.projects.services.delete_project import DeleteProject


class TestCreateProject:
    async def test_creates_project_with_configured_default_links(self, monkeypatch) -> None:
        from app.modules.projects.config import projects_settings

        monkeypatch.setattr(projects_settings, "DEFAULT_JIRA_URL", "https://jira.weup.vn")
        monkeypatch.setattr(projects_settings, "DEFAULT_GIT_URL", "https://git.weup.vn")
        uow = FakeProjectsUnitOfWork()

        project = await CreateProject(uow).execute("Website A", "Marketing site")

        assert project.name == "Website A"
        links = await uow.project_links.list_for_project(project.id)
        assert {link.type for link in links} == {ProjectLinkType.JIRA, ProjectLinkType.GIT}
        assert all(link.is_default for link in links)
        assert uow.commits == 1

    async def test_creates_project_with_no_default_links_when_unconfigured(self, monkeypatch) -> None:
        from app.modules.projects.config import projects_settings

        monkeypatch.setattr(projects_settings, "DEFAULT_JIRA_URL", "")
        monkeypatch.setattr(projects_settings, "DEFAULT_GIT_URL", "")
        uow = FakeProjectsUnitOfWork()

        project = await CreateProject(uow).execute("Website B", None)

        links = await uow.project_links.list_for_project(project.id)
        assert links == []


class TestUpdateProject:
    async def test_updates_name(self) -> None:
        uow = FakeProjectsUnitOfWork()
        project = await uow.projects.create(name="Old", description=None, created_by=None)

        updated = await UpdateProject(uow).execute(project.id, name="New", description=None)

        assert updated.name == "New"
        assert uow.commits == 1

    async def test_rejects_unknown_project(self) -> None:
        uow = FakeProjectsUnitOfWork()

        with pytest.raises(ProjectNotFound):
            await UpdateProject(uow).execute(uuid4(), name="X", description=None)

        assert uow.commits == 0


class TestDeleteProject:
    async def test_deletes_project(self) -> None:
        uow = FakeProjectsUnitOfWork()
        project = await uow.projects.create(name="Gone", description=None, created_by=None)

        await DeleteProject(uow).execute(project.id)

        assert await uow.projects.get_by_id(project.id) is None
        assert uow.commits == 1

    async def test_rejects_unknown_project(self) -> None:
        uow = FakeProjectsUnitOfWork()

        with pytest.raises(ProjectNotFound):
            await DeleteProject(uow).execute(uuid4())

        assert uow.commits == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/projects/test_services.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.modules.projects.services.create_project'`

- [ ] **Step 3: Write the implementations**

```python
# backend/app/modules/projects/services/create_project.py
from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.projects.rules import ProjectsRules
from app.modules.projects.schemas import ProjectRead
from app.modules.projects.uow import AbstractProjectsUnitOfWork


class CreateProject(AbstractUseCase):
    """Create a project, then attach the configured default Jira/Git links
    (ProjectsRules.default_links) — see spec's project_links note: these are
    seeded values, not a template table, so nothing here is admin-editable."""

    def __init__(self, uow: AbstractProjectsUnitOfWork) -> None:
        self._uow = uow

    @use_case
    async def execute(self, name: str, description: str | None) -> ProjectRead:
        project = await self._uow.projects.create(name=name, description=description, created_by=None)
        for link_type, link_name, url in ProjectsRules.default_links():
            await self._uow.project_links.create(
                project_id=project.id, type=link_type, name=link_name, url=url, is_default=True
            )
        await self._uow.commit()
        return project
```

```python
# backend/app/modules/projects/services/update_project.py
from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.projects.exceptions import ProjectNotFound
from app.modules.projects.schemas import ProjectRead
from app.modules.projects.uow import AbstractProjectsUnitOfWork


class UpdateProject(AbstractUseCase):
    """Rename and/or redescribe a project."""

    def __init__(self, uow: AbstractProjectsUnitOfWork) -> None:
        self._uow = uow

    @use_case
    async def execute(self, project_id: UUID, *, name: str | None, description: str | None) -> ProjectRead:
        if await self._uow.projects.get_by_id(project_id) is None:
            raise ProjectNotFound()
        updated = await self._uow.projects.update(project_id, name=name, description=description)
        await self._uow.commit()
        return updated
```

```python
# backend/app/modules/projects/services/delete_project.py
from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.projects.exceptions import ProjectNotFound
from app.modules.projects.uow import AbstractProjectsUnitOfWork


class DeleteProject(AbstractUseCase):
    """Delete a project. Its environments and links cascade at the DB level (ondelete=CASCADE)."""

    def __init__(self, uow: AbstractProjectsUnitOfWork) -> None:
        self._uow = uow

    @use_case
    async def execute(self, project_id: UUID) -> None:
        if await self._uow.projects.get_by_id(project_id) is None:
            raise ProjectNotFound()
        await self._uow.projects.delete(project_id)
        await self._uow.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/projects/test_services.py -v`
Expected: `TestCreateProject`, `TestUpdateProject`, `TestDeleteProject` — 6 passed (Tasks 6-7 add more classes to the same file; run the whole file again after each).

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/projects/services/__init__.py backend/app/modules/projects/services/create_project.py backend/app/modules/projects/services/update_project.py backend/app/modules/projects/services/delete_project.py backend/tests/projects/test_services.py
git commit -m "feat(projects): add project create/update/delete use cases"
```

---

### Task 6: Environment services — create/update/delete (TDD, Fake-based)

**Files:**
- Create: `backend/app/modules/projects/services/create_environment.py`, `update_environment.py`, `delete_environment.py`
- Modify: `backend/tests/projects/test_services.py` (append test classes below the Task 5 classes; Fakes already defined, do not redefine)

**Interfaces:**
- Consumes: `AbstractProjectsUnitOfWork` (Task 4), `EnvironmentTypeAlreadyExists`/`ProjectNotFound`/`EnvironmentNotFound` (Task 2).
- Produces: `CreateEnvironment(uow).execute(project_id, type, name, base_url) -> EnvironmentRead`, `UpdateEnvironment(uow).execute(environment_id, *, name, base_url) -> EnvironmentRead`, `DeleteEnvironment(uow).execute(environment_id) -> None`.

- [ ] **Step 1: Append the failing tests to `test_services.py`**

```python
from app.modules.projects.services.create_environment import CreateEnvironment
from app.modules.projects.services.update_environment import UpdateEnvironment
from app.modules.projects.services.delete_environment import DeleteEnvironment


class TestCreateEnvironment:
    async def test_creates_environment(self) -> None:
        uow = FakeProjectsUnitOfWork()
        project = await uow.projects.create(name="Website A", description=None, created_by=None)

        env = await CreateEnvironment(uow).execute(
            project.id, EnvironmentType.DEV, "dev", "https://dev.website-a.example"
        )

        assert env.type is EnvironmentType.DEV
        assert uow.commits == 1

    async def test_rejects_unknown_project(self) -> None:
        uow = FakeProjectsUnitOfWork()

        with pytest.raises(ProjectNotFound):
            await CreateEnvironment(uow).execute(uuid4(), EnvironmentType.DEV, "dev", None)

    async def test_rejects_duplicate_type_for_same_project(self) -> None:
        uow = FakeProjectsUnitOfWork()
        project = await uow.projects.create(name="Website A", description=None, created_by=None)
        await uow.environments.create(project_id=project.id, type=EnvironmentType.DEV, name="dev", base_url=None)

        with pytest.raises(EnvironmentTypeAlreadyExists):
            await CreateEnvironment(uow).execute(project.id, EnvironmentType.DEV, "dev-2", None)


class TestUpdateEnvironment:
    async def test_updates_name_and_base_url(self) -> None:
        uow = FakeProjectsUnitOfWork()
        project = await uow.projects.create(name="Website A", description=None, created_by=None)
        env = await uow.environments.create(
            project_id=project.id, type=EnvironmentType.DEV, name="dev", base_url=None
        )

        updated = await UpdateEnvironment(uow).execute(env.id, name="development", base_url="https://d.example")

        assert updated.name == "development"
        assert updated.base_url == "https://d.example"

    async def test_rejects_unknown_environment(self) -> None:
        uow = FakeProjectsUnitOfWork()

        with pytest.raises(EnvironmentNotFound):
            await UpdateEnvironment(uow).execute(uuid4(), name="x", base_url=None)


class TestDeleteEnvironment:
    async def test_deletes_environment(self) -> None:
        uow = FakeProjectsUnitOfWork()
        project = await uow.projects.create(name="Website A", description=None, created_by=None)
        env = await uow.environments.create(
            project_id=project.id, type=EnvironmentType.DEV, name="dev", base_url=None
        )

        await DeleteEnvironment(uow).execute(env.id)

        assert await uow.environments.get_by_id(env.id) is None

    async def test_rejects_unknown_environment(self) -> None:
        uow = FakeProjectsUnitOfWork()

        with pytest.raises(EnvironmentNotFound):
            await DeleteEnvironment(uow).execute(uuid4())
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && pytest tests/projects/test_services.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.modules.projects.services.create_environment'`

- [ ] **Step 3: Write the implementations**

```python
# backend/app/modules/projects/services/create_environment.py
from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.projects.constants import EnvironmentType
from app.modules.projects.exceptions import EnvironmentTypeAlreadyExists, ProjectNotFound
from app.modules.projects.schemas import EnvironmentRead
from app.modules.projects.uow import AbstractProjectsUnitOfWork


class CreateEnvironment(AbstractUseCase):
    """Create an environment. Rejected if the project doesn't exist, or already
    has an environment of the requested type (UNIQUE(project_id, type))."""

    def __init__(self, uow: AbstractProjectsUnitOfWork) -> None:
        self._uow = uow

    @use_case
    async def execute(
        self, project_id: UUID, type: EnvironmentType, name: str, base_url: str | None
    ) -> EnvironmentRead:
        if await self._uow.projects.get_by_id(project_id) is None:
            raise ProjectNotFound()
        if await self._uow.environments.find_by_project_and_type(project_id, type) is not None:
            raise EnvironmentTypeAlreadyExists()
        env = await self._uow.environments.create(project_id=project_id, type=type, name=name, base_url=base_url)
        await self._uow.commit()
        return env
```

```python
# backend/app/modules/projects/services/update_environment.py
from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.projects.exceptions import EnvironmentNotFound
from app.modules.projects.schemas import EnvironmentRead
from app.modules.projects.uow import AbstractProjectsUnitOfWork


class UpdateEnvironment(AbstractUseCase):
    """Rename and/or re-point an environment. type is immutable — see schemas.EnvironmentUpdate."""

    def __init__(self, uow: AbstractProjectsUnitOfWork) -> None:
        self._uow = uow

    @use_case
    async def execute(self, environment_id: UUID, *, name: str | None, base_url: str | None) -> EnvironmentRead:
        if await self._uow.environments.get_by_id(environment_id) is None:
            raise EnvironmentNotFound()
        updated = await self._uow.environments.update(environment_id, name=name, base_url=base_url)
        await self._uow.commit()
        return updated
```

```python
# backend/app/modules/projects/services/delete_environment.py
from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.projects.exceptions import EnvironmentNotFound
from app.modules.projects.uow import AbstractProjectsUnitOfWork


class DeleteEnvironment(AbstractUseCase):
    """Delete an environment."""

    def __init__(self, uow: AbstractProjectsUnitOfWork) -> None:
        self._uow = uow

    @use_case
    async def execute(self, environment_id: UUID) -> None:
        if await self._uow.environments.get_by_id(environment_id) is None:
            raise EnvironmentNotFound()
        await self._uow.environments.delete(environment_id)
        await self._uow.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/projects/test_services.py -v`
Expected: all `TestCreateEnvironment`/`TestUpdateEnvironment`/`TestDeleteEnvironment` cases pass (7 new), plus the 6 from Task 5 still pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/projects/services/create_environment.py backend/app/modules/projects/services/update_environment.py backend/app/modules/projects/services/delete_environment.py backend/tests/projects/test_services.py
git commit -m "feat(projects): add environment create/update/delete use cases"
```

---

### Task 7: ProjectLink services — create/update/delete (TDD, Fake-based)

**Files:**
- Create: `backend/app/modules/projects/services/create_project_link.py`, `update_project_link.py`, `delete_project_link.py`
- Modify: `backend/tests/projects/test_services.py` (append test classes; Fakes already defined)

**Interfaces:**
- Consumes: `AbstractProjectsUnitOfWork` (Task 4), `ProjectNotFound`/`ProjectLinkNotFound` (Task 2).
- Produces: `CreateProjectLink(uow).execute(project_id, type, name, url) -> ProjectLinkRead`, `UpdateProjectLink(uow).execute(link_id, *, name, url) -> ProjectLinkRead`, `DeleteProjectLink(uow).execute(link_id) -> None`.

- [ ] **Step 1: Append the failing tests to `test_services.py`**

```python
from app.modules.projects.services.create_project_link import CreateProjectLink
from app.modules.projects.services.update_project_link import UpdateProjectLink
from app.modules.projects.services.delete_project_link import DeleteProjectLink


class TestCreateProjectLink:
    async def test_creates_link_not_marked_default(self) -> None:
        uow = FakeProjectsUnitOfWork()
        project = await uow.projects.create(name="Website A", description=None, created_by=None)

        link = await CreateProjectLink(uow).execute(
            project.id, ProjectLinkType.OTHER, "Runbook", "https://wiki.example/runbook"
        )

        assert link.is_default is False
        assert uow.commits == 1

    async def test_rejects_unknown_project(self) -> None:
        uow = FakeProjectsUnitOfWork()

        with pytest.raises(ProjectNotFound):
            await CreateProjectLink(uow).execute(uuid4(), ProjectLinkType.OTHER, "X", "https://x.example")


class TestUpdateProjectLink:
    async def test_updates_name_and_url(self) -> None:
        uow = FakeProjectsUnitOfWork()
        project = await uow.projects.create(name="Website A", description=None, created_by=None)
        link = await uow.project_links.create(
            project_id=project.id, type=ProjectLinkType.OTHER, name="Old", url="https://old.example", is_default=False
        )

        updated = await UpdateProjectLink(uow).execute(link.id, name="New", url="https://new.example")

        assert updated.name == "New"
        assert updated.url == "https://new.example"

    async def test_rejects_unknown_link(self) -> None:
        uow = FakeProjectsUnitOfWork()

        with pytest.raises(ProjectLinkNotFound):
            await UpdateProjectLink(uow).execute(uuid4(), name="x", url=None)


class TestDeleteProjectLink:
    async def test_deletes_link(self) -> None:
        uow = FakeProjectsUnitOfWork()
        project = await uow.projects.create(name="Website A", description=None, created_by=None)
        link = await uow.project_links.create(
            project_id=project.id, type=ProjectLinkType.OTHER, name="Old", url="https://old.example", is_default=False
        )

        await DeleteProjectLink(uow).execute(link.id)

        assert await uow.project_links.get_by_id(link.id) is None

    async def test_rejects_unknown_link(self) -> None:
        uow = FakeProjectsUnitOfWork()

        with pytest.raises(ProjectLinkNotFound):
            await DeleteProjectLink(uow).execute(uuid4())
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && pytest tests/projects/test_services.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.modules.projects.services.create_project_link'`

- [ ] **Step 3: Write the implementations**

```python
# backend/app/modules/projects/services/create_project_link.py
from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.projects.constants import ProjectLinkType
from app.modules.projects.exceptions import ProjectNotFound
from app.modules.projects.schemas import ProjectLinkRead
from app.modules.projects.uow import AbstractProjectsUnitOfWork


class CreateProjectLink(AbstractUseCase):
    """Create a project link. Always is_default=False — only CreateProject's
    seeded rows are marked default."""

    def __init__(self, uow: AbstractProjectsUnitOfWork) -> None:
        self._uow = uow

    @use_case
    async def execute(self, project_id: UUID, type: ProjectLinkType, name: str, url: str) -> ProjectLinkRead:
        if await self._uow.projects.get_by_id(project_id) is None:
            raise ProjectNotFound()
        link = await self._uow.project_links.create(
            project_id=project_id, type=type, name=name, url=url, is_default=False
        )
        await self._uow.commit()
        return link
```

```python
# backend/app/modules/projects/services/update_project_link.py
from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.projects.exceptions import ProjectLinkNotFound
from app.modules.projects.schemas import ProjectLinkRead
from app.modules.projects.uow import AbstractProjectsUnitOfWork


class UpdateProjectLink(AbstractUseCase):
    """Rename and/or re-point a project link."""

    def __init__(self, uow: AbstractProjectsUnitOfWork) -> None:
        self._uow = uow

    @use_case
    async def execute(self, link_id: UUID, *, name: str | None, url: str | None) -> ProjectLinkRead:
        if await self._uow.project_links.get_by_id(link_id) is None:
            raise ProjectLinkNotFound()
        updated = await self._uow.project_links.update(link_id, name=name, url=url)
        await self._uow.commit()
        return updated
```

```python
# backend/app/modules/projects/services/delete_project_link.py
from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.projects.exceptions import ProjectLinkNotFound
from app.modules.projects.uow import AbstractProjectsUnitOfWork


class DeleteProjectLink(AbstractUseCase):
    """Delete a project link."""

    def __init__(self, uow: AbstractProjectsUnitOfWork) -> None:
        self._uow = uow

    @use_case
    async def execute(self, link_id: UUID) -> None:
        if await self._uow.project_links.get_by_id(link_id) is None:
            raise ProjectLinkNotFound()
        await self._uow.project_links.delete(link_id)
        await self._uow.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/projects/test_services.py -v`
Expected: all pass — 19 tests total across Tasks 5-7.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/projects/services/create_project_link.py backend/app/modules/projects/services/update_project_link.py backend/app/modules/projects/services/delete_project_link.py backend/tests/projects/test_services.py
git commit -m "feat(projects): add project-link create/update/delete use cases"
```

---

### Task 8: `router.py` — 13 endpoints (TDD, testcontainers)

**Files:**
- Modify: `backend/app/modules/projects/dependencies.py` (append 9 use-case provider factories, exact shape of `rbac/dependencies.py`'s `get_create_role`/`get_update_role`/`get_delete_role`)
- Create: `backend/app/modules/projects/router.py`
- Create: `backend/tests/projects/test_router.py`

**Interfaces:**
- Consumes: `require_permission` (`app.modules.rbac.public`), all 9 use cases (Tasks 5-7), `get_uow` (Task 4), pagination (`app.core.pagination`), `ApiResponse`/`Page` (`app.core.models`).
- Produces: `router` (`APIRouter`, prefix `/projects` for project/environment/link CRUD — environment/link mutation-by-id routes live at bare `/environments/{id}` and `/links/{id}` since they're not nested under a project_id path segment, matching rbac's own `/users/{user_id}/role` vs `/roles/{role_id}` mixed-prefix pattern) — consumed by Task 11's `main.py`.

- [ ] **Step 1: Append the 9 use-case providers to `dependencies.py`**

```python
# appended to backend/app/modules/projects/dependencies.py
from app.modules.projects.services.create_environment import CreateEnvironment
from app.modules.projects.services.create_project import CreateProject
from app.modules.projects.services.create_project_link import CreateProjectLink
from app.modules.projects.services.delete_environment import DeleteEnvironment
from app.modules.projects.services.delete_project import DeleteProject
from app.modules.projects.services.delete_project_link import DeleteProjectLink
from app.modules.projects.services.update_environment import UpdateEnvironment
from app.modules.projects.services.update_project import UpdateProject
from app.modules.projects.services.update_project_link import UpdateProjectLink
from app.modules.projects.uow import AbstractProjectsUnitOfWork


async def get_create_project(uow: AbstractProjectsUnitOfWork = Depends(get_uow)) -> CreateProject:
    """Provide the create-project use case."""
    return CreateProject(uow)


async def get_update_project(uow: AbstractProjectsUnitOfWork = Depends(get_uow)) -> UpdateProject:
    """Provide the update-project use case."""
    return UpdateProject(uow)


async def get_delete_project(uow: AbstractProjectsUnitOfWork = Depends(get_uow)) -> DeleteProject:
    """Provide the delete-project use case."""
    return DeleteProject(uow)


async def get_create_environment(uow: AbstractProjectsUnitOfWork = Depends(get_uow)) -> CreateEnvironment:
    """Provide the create-environment use case."""
    return CreateEnvironment(uow)


async def get_update_environment(uow: AbstractProjectsUnitOfWork = Depends(get_uow)) -> UpdateEnvironment:
    """Provide the update-environment use case."""
    return UpdateEnvironment(uow)


async def get_delete_environment(uow: AbstractProjectsUnitOfWork = Depends(get_uow)) -> DeleteEnvironment:
    """Provide the delete-environment use case."""
    return DeleteEnvironment(uow)


async def get_create_project_link(uow: AbstractProjectsUnitOfWork = Depends(get_uow)) -> CreateProjectLink:
    """Provide the create-project-link use case."""
    return CreateProjectLink(uow)


async def get_update_project_link(uow: AbstractProjectsUnitOfWork = Depends(get_uow)) -> UpdateProjectLink:
    """Provide the update-project-link use case."""
    return UpdateProjectLink(uow)


async def get_delete_project_link(uow: AbstractProjectsUnitOfWork = Depends(get_uow)) -> DeleteProjectLink:
    """Provide the delete-project-link use case."""
    return DeleteProjectLink(uow)
```

- [ ] **Step 2: Write the failing router tests**

```python
"""Integration tests for app.modules.projects.router — real Postgres via testcontainers."""

from uuid import UUID

from httpx import AsyncClient
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.security import JwtCodec
from app.modules.auth.config import auth_settings
from app.modules.auth.constants import AuthCookies
from app.modules.rbac.models import Permission, Role, RolePermission, UserRole
from app.modules.users.models import User


async def _login_with_permissions(
    client: AsyncClient, engine: AsyncEngine, *, permissions: list[tuple[str, str]]
) -> UUID:
    """Log in a real user and grant a role carrying exactly `permissions` —
    same trick tests/users/test_router.py uses."""
    async with engine.begin() as conn:
        user_result = await conn.execute(
            insert(User).values(
                email="actor@example.com",
                name="Actor",
                status="active",
                external_user_id="dx-actor",
                employee_code=None,
                email_confirmed=True,
            )
        )
        user_id = user_result.inserted_primary_key[0]

        role_result = await conn.execute(insert(Role).values(name="test-role", is_system=False))
        role_id = role_result.inserted_primary_key[0]

        for resource, action in permissions:
            perm_result = await conn.execute(
                insert(Permission).values(resource=resource, action=action, description_key="x")
            )
            permission_id = perm_result.inserted_primary_key[0]
            await conn.execute(insert(RolePermission).values(role_id=role_id, permission_id=permission_id))

        await conn.execute(insert(UserRole).values(user_id=user_id, role_id=role_id))

    token = JwtCodec.encode(
        {"sub": str(user_id), "type": "access", "jti": "test-jti"},
        secret=auth_settings.JWT_SECRET,
        ttl_seconds=3600,
    )
    client.cookies.set(AuthCookies.ACCESS_TOKEN, token)
    return user_id


class TestCreateProject:
    async def test_requires_project_create_permission(self, client: AsyncClient, engine: AsyncEngine) -> None:
        await _login_with_permissions(client, engine, permissions=[])

        response = await client.post("/api/v1/projects", json={"name": "Website A"})

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "rbac_permission_denied"

    async def test_creates_project_with_permission(self, client: AsyncClient, engine: AsyncEngine) -> None:
        await _login_with_permissions(client, engine, permissions=[("project", "create")])

        response = await client.post(
            "/api/v1/projects", json={"name": "Website A", "description": "Marketing site"}
        )

        body = response.json()
        assert response.status_code == 200
        assert body["data"]["name"] == "Website A"


class TestProjectEnvironmentsAndLinks:
    async def test_full_lifecycle(self, client: AsyncClient, engine: AsyncEngine) -> None:
        await _login_with_permissions(
            client,
            engine,
            permissions=[
                ("project", "create"),
                ("project", "read"),
                ("project", "update"),
                ("environment", "create"),
                ("environment", "read"),
                ("environment", "update"),
                ("environment", "delete"),
            ],
        )

        create_resp = await client.post("/api/v1/projects", json={"name": "Website A"})
        project_id = create_resp.json()["data"]["id"]

        env_resp = await client.post(
            f"/api/v1/projects/{project_id}/environments",
            json={"type": "dev", "name": "dev", "baseUrl": "https://dev.example"},
        )
        assert env_resp.status_code == 200
        environment_id = env_resp.json()["data"]["id"]

        dup_resp = await client.post(
            f"/api/v1/projects/{project_id}/environments", json={"type": "dev", "name": "dev-2"}
        )
        assert dup_resp.status_code == 409
        assert dup_resp.json()["error"]["code"] == "projects_environment_type_already_exists"

        link_resp = await client.get(f"/api/v1/projects/{project_id}/links")
        assert link_resp.status_code == 200
        assert len(link_resp.json()["data"]) == 0  # PROJECTS__DEFAULT_JIRA_URL/GIT_URL unset in tests

        update_resp = await client.patch(f"/api/v1/environments/{environment_id}", json={"name": "development"})
        assert update_resp.json()["data"]["name"] == "development"

        delete_resp = await client.delete(f"/api/v1/environments/{environment_id}")
        assert delete_resp.status_code == 200

        list_resp = await client.get(f"/api/v1/projects/{project_id}/environments")
        assert list_resp.json()["data"] == []
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && pytest tests/projects/test_router.py -v`
Expected: FAIL — `404 Not Found` (no `/api/v1/projects` route registered yet) or `ModuleNotFoundError` once `router.py` is imported anywhere.

- [ ] **Step 4: Write `router.py`**

```python
"""HTTP entry points of the projects module. Router thinness (rule #10): every
function below only translates HTTP -> use-case call and wraps the result in
ApiResponse — no formatting/business logic lives here.
"""

from uuid import UUID

from fastapi import APIRouter, Depends

from app.core.models import ApiResponse
from app.core.pagination import Page, PaginationParams, pagination_params
from app.modules.projects.dependencies import (
    get_create_environment,
    get_create_project,
    get_create_project_link,
    get_delete_environment,
    get_delete_project,
    get_delete_project_link,
    get_update_environment,
    get_update_project,
    get_update_project_link,
    get_uow,
)
from app.modules.projects.exceptions import ProjectNotFound
from app.modules.projects.schemas import (
    EnvironmentCreate,
    EnvironmentRead,
    EnvironmentUpdate,
    ProjectCreate,
    ProjectLinkCreate,
    ProjectLinkRead,
    ProjectLinkUpdate,
    ProjectRead,
    ProjectUpdate,
)
from app.modules.projects.services.create_environment import CreateEnvironment
from app.modules.projects.services.create_project import CreateProject
from app.modules.projects.services.create_project_link import CreateProjectLink
from app.modules.projects.services.delete_environment import DeleteEnvironment
from app.modules.projects.services.delete_project import DeleteProject
from app.modules.projects.services.delete_project_link import DeleteProjectLink
from app.modules.projects.services.update_environment import UpdateEnvironment
from app.modules.projects.services.update_project import UpdateProject
from app.modules.projects.services.update_project_link import UpdateProjectLink
from app.modules.projects.uow import AbstractProjectsUnitOfWork
from app.modules.rbac.public import require_permission
from app.modules.users.public import UserRead

router = APIRouter(tags=["projects"])


@router.post("/projects")
async def create_project(
    body: ProjectCreate,
    use_case: CreateProject = Depends(get_create_project),
    _user: UserRead = Depends(require_permission("project", "create")),
) -> ApiResponse[ProjectRead]:
    """Create a new project — auto-attaches the configured default Jira/Git links."""
    project = await use_case.execute(body.name, body.description)
    return ApiResponse[ProjectRead](success=True, data=project)


@router.get("/projects")
async def list_projects(
    pagination: PaginationParams = Depends(pagination_params),
    uow: AbstractProjectsUnitOfWork = Depends(get_uow),
    _user: UserRead = Depends(require_permission("project", "read")),
) -> ApiResponse[Page[ProjectRead]]:
    """List projects."""
    items, total = await uow.projects.list_page(pagination.limit, pagination.offset)
    page = Page[ProjectRead](items=items, total=total, limit=pagination.limit, offset=pagination.offset)
    return ApiResponse[Page[ProjectRead]](success=True, data=page)


@router.get("/projects/{project_id}")
async def get_project(
    project_id: UUID,
    uow: AbstractProjectsUnitOfWork = Depends(get_uow),
    _user: UserRead = Depends(require_permission("project", "read")),
) -> ApiResponse[ProjectRead]:
    """Return one project, 404 if it doesn't exist."""
    project = await uow.projects.get_by_id(project_id)
    if project is None:
        raise ProjectNotFound()
    return ApiResponse[ProjectRead](success=True, data=project)


@router.patch("/projects/{project_id}")
async def update_project(
    project_id: UUID,
    body: ProjectUpdate,
    use_case: UpdateProject = Depends(get_update_project),
    _user: UserRead = Depends(require_permission("project", "update")),
) -> ApiResponse[ProjectRead]:
    """Rename and/or redescribe a project."""
    project = await use_case.execute(project_id, name=body.name, description=body.description)
    return ApiResponse[ProjectRead](success=True, data=project)


@router.delete("/projects/{project_id}")
async def delete_project(
    project_id: UUID,
    use_case: DeleteProject = Depends(get_delete_project),
    _user: UserRead = Depends(require_permission("project", "delete")),
) -> ApiResponse[None]:
    """Delete a project. Its environments and links cascade at the DB level."""
    await use_case.execute(project_id)
    return ApiResponse[None](success=True)


@router.get("/projects/{project_id}/environments")
async def list_environments(
    project_id: UUID,
    uow: AbstractProjectsUnitOfWork = Depends(get_uow),
    _user: UserRead = Depends(require_permission("environment", "read")),
) -> ApiResponse[list[EnvironmentRead]]:
    """List a project's environments."""
    environments = await uow.environments.list_for_project(project_id)
    return ApiResponse[list[EnvironmentRead]](success=True, data=environments)


@router.post("/projects/{project_id}/environments")
async def create_environment(
    project_id: UUID,
    body: EnvironmentCreate,
    use_case: CreateEnvironment = Depends(get_create_environment),
    _user: UserRead = Depends(require_permission("environment", "create")),
) -> ApiResponse[EnvironmentRead]:
    """Create an environment. Rejected if the project already has one of this type."""
    env = await use_case.execute(project_id, body.type, body.name, body.base_url)
    return ApiResponse[EnvironmentRead](success=True, data=env)


@router.patch("/environments/{environment_id}")
async def update_environment(
    environment_id: UUID,
    body: EnvironmentUpdate,
    use_case: UpdateEnvironment = Depends(get_update_environment),
    _user: UserRead = Depends(require_permission("environment", "update")),
) -> ApiResponse[EnvironmentRead]:
    """Rename and/or re-point an environment."""
    env = await use_case.execute(environment_id, name=body.name, base_url=body.base_url)
    return ApiResponse[EnvironmentRead](success=True, data=env)


@router.delete("/environments/{environment_id}")
async def delete_environment(
    environment_id: UUID,
    use_case: DeleteEnvironment = Depends(get_delete_environment),
    _user: UserRead = Depends(require_permission("environment", "delete")),
) -> ApiResponse[None]:
    """Delete an environment."""
    await use_case.execute(environment_id)
    return ApiResponse[None](success=True)


@router.get("/projects/{project_id}/links")
async def list_project_links(
    project_id: UUID,
    uow: AbstractProjectsUnitOfWork = Depends(get_uow),
    _user: UserRead = Depends(require_permission("project", "read")),
) -> ApiResponse[list[ProjectLinkRead]]:
    """List a project's external links."""
    links = await uow.project_links.list_for_project(project_id)
    return ApiResponse[list[ProjectLinkRead]](success=True, data=links)


@router.post("/projects/{project_id}/links")
async def create_project_link(
    project_id: UUID,
    body: ProjectLinkCreate,
    use_case: CreateProjectLink = Depends(get_create_project_link),
    _user: UserRead = Depends(require_permission("project", "update")),
) -> ApiResponse[ProjectLinkRead]:
    """Add an external link to a project."""
    link = await use_case.execute(project_id, body.type, body.name, body.url)
    return ApiResponse[ProjectLinkRead](success=True, data=link)


@router.patch("/links/{link_id}")
async def update_project_link(
    link_id: UUID,
    body: ProjectLinkUpdate,
    use_case: UpdateProjectLink = Depends(get_update_project_link),
    _user: UserRead = Depends(require_permission("project", "update")),
) -> ApiResponse[ProjectLinkRead]:
    """Rename and/or re-point a project link."""
    link = await use_case.execute(link_id, name=body.name, url=body.url)
    return ApiResponse[ProjectLinkRead](success=True, data=link)


@router.delete("/links/{link_id}")
async def delete_project_link(
    link_id: UUID,
    use_case: DeleteProjectLink = Depends(get_delete_project_link),
    _user: UserRead = Depends(require_permission("project", "update")),
) -> ApiResponse[None]:
    """Remove a project link."""
    await use_case.execute(link_id)
    return ApiResponse[None](success=True)
```

Note: `ProjectNotFound` is imported above and raised only by the one hand-rolled GET-by-id read (`get_project`); every mutation's not-found case (`EnvironmentNotFound`, `ProjectLinkNotFound`, and `ProjectNotFound` on the mutation paths) is raised inside its own use case (Tasks 5-7), not the router — consistent with rule #10. Router never imports an exception it doesn't itself raise.

- [ ] **Step 5: Register the router temporarily for the test to resolve it**

This module isn't wired into `main.py` until Task 11 — but `tests/conftest.py`'s `client` fixture imports the real `app.main.app`, so the router tests in this task will still 404 until Task 11 runs. **Do Task 11 immediately after this step, before running the router tests**, then return here.

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && pytest tests/projects/ -v`
Expected: all tests across `test_rules.py`, `test_services.py`, `test_router.py` pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/modules/projects/dependencies.py backend/app/modules/projects/router.py backend/tests/projects/test_router.py
git commit -m "feat(projects): add router with 13 endpoints"
```

---

### Task 9: `public.py` — facade for later phases

No independent test cycle — every later phase (Cloudflare, observability, notifications) will exercise this through their own router tests once they exist; for Phase 1 it only needs to import cleanly and be exposed correctly, verified by Step 2 below.

**Files:**
- Create: `backend/app/modules/projects/public.py`

**Interfaces:**
- Produces: `ProjectsApi.get_project_by_id(project_id) -> ProjectRead | None`, `ProjectsApi.get_environment_by_id(environment_id) -> EnvironmentRead | None`, `get_projects_api` — the two lookups Phase 3+ (Cloudflare `cloudflare_configs.environment_id`, observability `loki_configs.environment_id`, notifications `notification_channels.environment_id`) will need to validate a foreign FK before writing their own tables.

- [ ] **Step 1: Write `public.py`**

```python
"""Contract exposed to other modules. This is the ONLY file another module
may import from projects — enforced by scripts/check_module_boundaries.py.
"""

from uuid import UUID

from fastapi import Depends

from app.core.base.markers import facade
from app.modules.projects.dependencies import get_uow
from app.modules.projects.schemas import EnvironmentRead, ProjectRead
from app.modules.projects.uow import AbstractProjectsUnitOfWork

__all__ = ["ProjectRead", "EnvironmentRead", "ProjectsApi", "get_projects_api"]


class ProjectsApi:
    """Facade over projects/environments for other modules' cross-module needs:
    Cloudflare/observability/notifications validating an environment_id (and,
    transitively, the project it belongs to) before creating their own rows."""

    def __init__(self, uow: AbstractProjectsUnitOfWork) -> None:
        self._uow = uow

    @facade
    async def get_project_by_id(self, project_id: UUID) -> ProjectRead | None:
        """Look up any project by id — for a single existence check from
        another module, never for bulk reads."""
        return await self._uow.projects.get_by_id(project_id)

    @facade
    async def get_environment_by_id(self, environment_id: UUID) -> EnvironmentRead | None:
        """Look up any environment by id — for another module to validate
        an environment_id foreign key before writing its own row."""
        return await self._uow.environments.get_by_id(environment_id)


async def get_projects_api(uow: AbstractProjectsUnitOfWork = Depends(get_uow)) -> ProjectsApi:
    """Provide the facade to other modules."""
    return ProjectsApi(uow)
```

- [ ] **Step 2: Sanity-check import**

Run: `cd backend && python -c "from app.modules.projects.public import ProjectsApi, get_projects_api"`
Expected: exits 0.

- [ ] **Step 3: Commit**

```bash
git add backend/app/modules/projects/public.py
git commit -m "feat(projects): add public.py facade for later phases"
```

---

### Task 10: RBAC catalog — 8 new permissions

**Files:**
- Modify: `backend/app/modules/rbac/constants.py:22-31` (`RbacPermissionCatalog.CATALOG`)

**Interfaces:**
- Consumes: nothing new.
- Produces: 8 catalog entries consumed by `backend/app/seeds/seed_rbac.py` (unmodified — it already iterates `CATALOG` generically) and by Task 8's router `require_permission("project"/"environment", ...)` calls.

- [ ] **Step 1: Append to the catalog**

```python
# backend/app/modules/rbac/constants.py — inside RbacPermissionCatalog.CATALOG, after the existing 8 entries
        ("project", "create", "permissions.project.create"),
        ("project", "read", "permissions.project.read"),
        ("project", "update", "permissions.project.update"),
        ("project", "delete", "permissions.project.delete"),
        ("environment", "create", "permissions.environment.create"),
        ("environment", "read", "permissions.environment.read"),
        ("environment", "update", "permissions.environment.update"),
        ("environment", "delete", "permissions.environment.delete"),
```

- [ ] **Step 2: Run the seed against a local dev database**

Run: `cd backend && python -m app.seeds.seed_rbac`
Expected: exits 0; `SELECT resource, action FROM permissions WHERE resource IN ('project','environment');` returns 8 rows; existing `admin` role now also grants all 8 (seed script grants every catalog permission to `admin`, unmodified).

- [ ] **Step 3: Commit**

```bash
git add backend/app/modules/rbac/constants.py
git commit -m "feat(rbac): add project and environment permissions to the catalog"
```

---

### Task 11: Wire the module in — `main.py`, `.importlinter`, boundary check

**Files:**
- Modify: `backend/app/main.py:18-20,98-100` (import + `include_router`)
- Modify: `backend/.importlinter` (new `projects-facade` contract)

**Interfaces:**
- Consumes: `router` (Task 8).
- Produces: `/api/v1/projects/*`, `/api/v1/environments/*`, `/api/v1/links/*` live on the running app — this is what makes Task 8's router tests actually resolve (see Task 8 Step 5's forward reference).

- [ ] **Step 1: Register the router in `main.py`**

```python
# backend/app/main.py — add alongside the existing three imports (after line 20)
from app.modules.projects.router import router as projects_router
```
```python
# backend/app/main.py — add alongside the existing three include_router calls (after line 100)
app.include_router(projects_router, prefix="/api/v1")
```

- [ ] **Step 2: Add the `.importlinter` facade contract**

```ini
# backend/.importlinter — append after the existing [importlinter:contract:users-facade] block
[importlinter:contract:projects-facade]
name = Other modules reach projects only through public.py
type = forbidden
source_modules =
    app.modules.auth
    app.modules.rbac
    app.modules.users
    app.modules.common
forbidden_modules =
    app.modules.projects.repository
    app.modules.projects.models
    app.modules.projects.uow
    app.modules.projects.services
allow_indirect_imports = True
```

Also extend `root-is-mechanism`'s and any future integration's `forbidden_modules` list is **not** needed here — `projects` has no `app/integrations/` counterpart in Phase 1 (that starts in Phase 2 with `app/integrations/mongo/`).

- [ ] **Step 3: Run the boundary checks**

Run: `cd backend && python scripts/check_module_boundaries.py --strict && lint-imports`
Expected: both exit 0.

- [ ] **Step 4: Now go back and finish Task 8's Steps 6-7 (router tests)**

Run: `cd backend && pytest tests/projects/ -v`
Expected: all pass.

- [ ] **Step 5: Run the full backend suite + lint to confirm nothing else broke**

Run: `cd backend && ruff check && ruff format --check && pytest`
Expected: all pass — this includes `tests/auth/`, `tests/rbac/`, `tests/users/` alongside the new `tests/projects/`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/main.py backend/.importlinter
git commit -m "feat(projects): wire router into the app and lock the module boundary"
```

---

### Task 12: Frontend entities — `entities/project`, `entities/environment`

No automated test (no test runner configured in this repo — verified via `frontend/package.json`); verified by Step 5's manual check.

**Files:**
- Create: `frontend/src/entities/project/model/schema.ts`, `api/fetchers.ts`, `api/query-keys.ts`, `index.ts`
- Create: `frontend/src/entities/environment/model/schema.ts`, `api/fetchers.ts`, `api/query-keys.ts`, `index.ts`
- Modify: `frontend/src/shared/constants/api.ts` (add `PROJECTS` endpoint block)

**Interfaces:**
- Consumes: `apiFetch` (`shared/lib/api-client.ts`).
- Produces: `fetchProjects`, `fetchProject`, `fetchProjectEnvironments`, `projectsKeys`, `Project`/`ProjectsPage` types, `fetchEnvironments`, `environmentsKeys`, `Environment` type — consumed by Task 13's `modules/projects` and by every later phase (Cloudflare/observability/notifications need an environment selector).

- [ ] **Step 1: Add the `PROJECTS` endpoint block to `shared/constants/api.ts`**

```typescript
// frontend/src/shared/constants/api.ts — add inside ENDPOINTS, after RBAC
    PROJECTS: {
      ROOT: "/projects",
      DETAIL: (id: string) => `/projects/${id}`,
      ENVIRONMENTS: (projectId: string) => `/projects/${projectId}/environments`,
      ENVIRONMENT_DETAIL: (id: string) => `/environments/${id}`,
      LINKS: (projectId: string) => `/projects/${projectId}/links`,
      LINK_DETAIL: (id: string) => `/links/${id}`,
    },
```

- [ ] **Step 2: `entities/project/model/schema.ts`**

```typescript
import { z } from "zod";

export const projectSchema = z.object({
  id: z.uuid(),
  name: z.string(),
  description: z.string().nullable(),
  createdBy: z.uuid().nullable(),
  createdAt: z.string(),
  updatedAt: z.string(),
});

export type Project = z.infer<typeof projectSchema>;

export const projectsPageSchema = z.object({
  items: z.array(projectSchema),
  total: z.number(),
  limit: z.number(),
  offset: z.number(),
});

export type ProjectsPage = z.infer<typeof projectsPageSchema>;
```

- [ ] **Step 3: `entities/project/api/query-keys.ts`, `api/fetchers.ts`, `index.ts`**

```typescript
// frontend/src/entities/project/api/query-keys.ts
/**
 * Hierarchical query key factory for the project entity.
 */
export const projectsKeys = {
  all: ["projects"] as const,
  lists: () => [...projectsKeys.all, "list"] as const,
  list: (filters?: { limit?: number; offset?: number }) =>
    [...projectsKeys.lists(), filters] as const,
  detail: (id: string) => [...projectsKeys.all, "detail", id] as const,
};
```

```typescript
// frontend/src/entities/project/api/fetchers.ts
import { apiFetch } from "@/shared/lib/api-client";
import { API_CONFIG } from "@/shared/constants/api";
import { projectSchema, projectsPageSchema, type Project, type ProjectsPage } from "../model/schema";

/**
 * Fetches paginated projects from GET /projects.
 */
export async function fetchProjects(limit = 50, offset = 0): Promise<ProjectsPage> {
  const raw = await apiFetch<unknown>(
    `${API_CONFIG.ENDPOINTS.PROJECTS.ROOT}?limit=${limit}&offset=${offset}`,
  );
  return projectsPageSchema.parse(raw);
}

/**
 * Fetches one project from GET /projects/{id}.
 */
export async function fetchProject(id: string): Promise<Project> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.PROJECTS.DETAIL(id));
  return projectSchema.parse(raw);
}
```

```typescript
// frontend/src/entities/project/index.ts
export { fetchProjects, fetchProject } from "./api/fetchers";
export { projectsKeys } from "./api/query-keys";
export { projectSchema, projectsPageSchema } from "./model/schema";
export type { Project, ProjectsPage } from "./model/schema";
```

- [ ] **Step 4: `entities/environment/model/schema.ts`, `api/query-keys.ts`, `api/fetchers.ts`, `index.ts`**

```typescript
// frontend/src/entities/environment/model/schema.ts
import { z } from "zod";

export const ENVIRONMENT_TYPES = ["dev", "staging", "production"] as const;
export type EnvironmentType = (typeof ENVIRONMENT_TYPES)[number];

export const environmentSchema = z.object({
  id: z.uuid(),
  projectId: z.uuid(),
  type: z.enum(ENVIRONMENT_TYPES),
  name: z.string(),
  baseUrl: z.string().nullable(),
  createdAt: z.string(),
  updatedAt: z.string(),
});

export type Environment = z.infer<typeof environmentSchema>;
```

```typescript
// frontend/src/entities/environment/api/query-keys.ts
/**
 * Hierarchical query key factory for the environment entity.
 */
export const environmentsKeys = {
  all: ["environments"] as const,
  forProject: (projectId: string) => [...environmentsKeys.all, "project", projectId] as const,
  detail: (id: string) => [...environmentsKeys.all, "detail", id] as const,
};
```

```typescript
// frontend/src/entities/environment/api/fetchers.ts
import { apiFetch } from "@/shared/lib/api-client";
import { API_CONFIG } from "@/shared/constants/api";
import { environmentSchema, type Environment } from "../model/schema";

/**
 * Fetches all environments for a project from GET /projects/{projectId}/environments.
 */
export async function fetchProjectEnvironments(projectId: string): Promise<Environment[]> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.PROJECTS.ENVIRONMENTS(projectId));
  return environmentSchema.array().parse(raw);
}
```

```typescript
// frontend/src/entities/environment/index.ts
export { fetchProjectEnvironments } from "./api/fetchers";
export { environmentsKeys } from "./api/query-keys";
export { environmentSchema, ENVIRONMENT_TYPES } from "./model/schema";
export type { Environment, EnvironmentType } from "./model/schema";
```

- [ ] **Step 5: Read hooks — `entities/project/hooks/use-projects.ts`, `entities/environment/hooks/use-environments.ts`**

Read hooks live in the entity (not `modules/projects`) because Phase 3+ (Cloudflare/observability/notifications) will consume them directly, same reasoning as `entities/role/hooks/use-roles.ts`.

```typescript
// frontend/src/entities/project/hooks/use-projects.ts
"use client";

import { useSuspenseQuery } from "@tanstack/react-query";
import { fetchProjects, fetchProject, projectsKeys } from "@/entities/project";

export function useProjectsQuery(limit = 50, offset = 0) {
  return useSuspenseQuery({
    queryKey: projectsKeys.list({ limit, offset }),
    queryFn: () => fetchProjects(limit, offset),
  });
}

export function useProjectQuery(id: string) {
  return useSuspenseQuery({
    queryKey: projectsKeys.detail(id),
    queryFn: () => fetchProject(id),
  });
}
```

```typescript
// frontend/src/entities/environment/hooks/use-environments.ts
"use client";

import { useSuspenseQuery } from "@tanstack/react-query";
import { fetchProjectEnvironments, environmentsKeys } from "@/entities/environment";

export function useProjectEnvironmentsQuery(projectId: string) {
  return useSuspenseQuery({
    queryKey: environmentsKeys.forProject(projectId),
    queryFn: () => fetchProjectEnvironments(projectId),
  });
}
```

Update `entities/project/index.ts` to also export `{ useProjectsQuery, useProjectQuery } from "./hooks/use-projects"`, and `entities/environment/index.ts` to also export `{ useProjectEnvironmentsQuery } from "./hooks/use-environments"`.

- [ ] **Step 6: Manual verification**

Run: `cd frontend && npx tsc --noEmit`
Expected: no type errors referencing `entities/project` or `entities/environment`.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/shared/constants/api.ts frontend/src/entities/project frontend/src/entities/environment
git commit -m "feat(projects): add project and environment entities"
```

---

### Task 13: `modules/projects` — mutation hooks + fetchers for links

No automated test; verified by Step 4's manual check.

**Files:**
- Create: `frontend/src/modules/projects/api/fetchers.ts` (project_links CRUD only — project/environment reads come from the entities)
- Create: `frontend/src/modules/projects/hooks/use-create-project.ts`, `use-update-project.ts`, `use-delete-project.ts`, `use-create-environment.ts`, `use-update-environment.ts`, `use-delete-environment.ts`, `use-create-project-link.ts`, `use-update-project-link.ts`, `use-delete-project-link.ts`

**Interfaces:**
- Consumes: `projectsKeys` (`entities/project`), `environmentsKeys` (`entities/environment`), `apiFetch` (`shared/lib/api-client`).
- Produces: 9 mutation hooks — consumed by Task 14's UI.

- [ ] **Step 1: `modules/projects/api/fetchers.ts`**

```typescript
import { apiFetch } from "@/shared/lib/api-client";
import { API_CONFIG } from "@/shared/constants/api";
import type { Project } from "@/entities/project";
import type { Environment } from "@/entities/environment";

export async function createProject(name: string, description?: string): Promise<Project> {
  return apiFetch<Project>(API_CONFIG.ENDPOINTS.PROJECTS.ROOT, {
    method: "POST",
    data: { name, description },
  });
}

export async function updateProject(
  id: string,
  data: { name?: string; description?: string },
): Promise<Project> {
  return apiFetch<Project>(API_CONFIG.ENDPOINTS.PROJECTS.DETAIL(id), { method: "PATCH", data });
}

export async function deleteProject(id: string): Promise<void> {
  await apiFetch<null>(API_CONFIG.ENDPOINTS.PROJECTS.DETAIL(id), { method: "DELETE" });
}

export async function createEnvironment(
  projectId: string,
  data: { type: string; name: string; baseUrl?: string },
): Promise<Environment> {
  return apiFetch<Environment>(API_CONFIG.ENDPOINTS.PROJECTS.ENVIRONMENTS(projectId), {
    method: "POST",
    data,
  });
}

export async function updateEnvironment(
  id: string,
  data: { name?: string; baseUrl?: string },
): Promise<Environment> {
  return apiFetch<Environment>(API_CONFIG.ENDPOINTS.PROJECTS.ENVIRONMENT_DETAIL(id), {
    method: "PATCH",
    data,
  });
}

export async function deleteEnvironment(id: string): Promise<void> {
  await apiFetch<null>(API_CONFIG.ENDPOINTS.PROJECTS.ENVIRONMENT_DETAIL(id), { method: "DELETE" });
}

export interface ProjectLink {
  id: string;
  projectId: string;
  type: "jira" | "git" | "other";
  name: string;
  url: string;
  isDefault: boolean;
}

export async function fetchProjectLinks(projectId: string): Promise<ProjectLink[]> {
  return apiFetch<ProjectLink[]>(API_CONFIG.ENDPOINTS.PROJECTS.LINKS(projectId));
}

export async function createProjectLink(
  projectId: string,
  data: { type: string; name: string; url: string },
): Promise<ProjectLink> {
  return apiFetch<ProjectLink>(API_CONFIG.ENDPOINTS.PROJECTS.LINKS(projectId), { method: "POST", data });
}

export async function updateProjectLink(
  id: string,
  data: { name?: string; url?: string },
): Promise<ProjectLink> {
  return apiFetch<ProjectLink>(API_CONFIG.ENDPOINTS.PROJECTS.LINK_DETAIL(id), { method: "PATCH", data });
}

export async function deleteProjectLink(id: string): Promise<void> {
  await apiFetch<null>(API_CONFIG.ENDPOINTS.PROJECTS.LINK_DETAIL(id), { method: "DELETE" });
}
```

- [ ] **Step 2: Project mutation hooks**

```typescript
// frontend/src/modules/projects/hooks/use-create-project.ts
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createProject } from "../api/fetchers";
import { projectsKeys } from "@/entities/project";

export function useCreateProject() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ name, description }: { name: string; description?: string }) =>
      createProject(name, description),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: projectsKeys.all });
    },
  });
}
```

```typescript
// frontend/src/modules/projects/hooks/use-update-project.ts
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { updateProject } from "../api/fetchers";
import { projectsKeys } from "@/entities/project";

export function useUpdateProject() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      id,
      data,
    }: {
      id: string;
      data: { name?: string; description?: string };
    }) => updateProject(id, data),
    onSuccess: (_result, variables) => {
      queryClient.invalidateQueries({ queryKey: projectsKeys.all });
      queryClient.invalidateQueries({ queryKey: projectsKeys.detail(variables.id) });
    },
  });
}
```

```typescript
// frontend/src/modules/projects/hooks/use-delete-project.ts
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { deleteProject } from "../api/fetchers";
import { projectsKeys } from "@/entities/project";

export function useDeleteProject() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => deleteProject(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: projectsKeys.all });
    },
  });
}
```

- [ ] **Step 3: Environment and project-link mutation hooks (same shape, condensed)**

```typescript
// frontend/src/modules/projects/hooks/use-create-environment.ts
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createEnvironment } from "../api/fetchers";
import { environmentsKeys } from "@/entities/environment";

export function useCreateEnvironment(projectId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: { type: string; name: string; baseUrl?: string }) =>
      createEnvironment(projectId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: environmentsKeys.forProject(projectId) });
    },
  });
}
```

```typescript
// frontend/src/modules/projects/hooks/use-update-environment.ts
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { updateEnvironment } from "../api/fetchers";
import { environmentsKeys } from "@/entities/environment";

export function useUpdateEnvironment(projectId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: { name?: string; baseUrl?: string } }) =>
      updateEnvironment(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: environmentsKeys.forProject(projectId) });
    },
  });
}
```

```typescript
// frontend/src/modules/projects/hooks/use-delete-environment.ts
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { deleteEnvironment } from "../api/fetchers";
import { environmentsKeys } from "@/entities/environment";

export function useDeleteEnvironment(projectId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => deleteEnvironment(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: environmentsKeys.forProject(projectId) });
    },
  });
}
```

```typescript
// frontend/src/modules/projects/hooks/use-create-project-link.ts
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createProjectLink } from "../api/fetchers";

export function useCreateProjectLink(projectId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: { type: string; name: string; url: string }) =>
      createProjectLink(projectId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects", "links", projectId] });
    },
  });
}
```

```typescript
// frontend/src/modules/projects/hooks/use-update-project-link.ts
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { updateProjectLink } from "../api/fetchers";

export function useUpdateProjectLink(projectId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: { name?: string; url?: string } }) =>
      updateProjectLink(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects", "links", projectId] });
    },
  });
}
```

```typescript
// frontend/src/modules/projects/hooks/use-delete-project-link.ts
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { deleteProjectLink } from "../api/fetchers";

export function useDeleteProjectLink(projectId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => deleteProjectLink(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects", "links", projectId] });
    },
  });
}
```

- [ ] **Step 4: Manual verification**

Run: `cd frontend && npx tsc --noEmit`
Expected: no type errors referencing `modules/projects/hooks` or `modules/projects/api`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/modules/projects/api frontend/src/modules/projects/hooks
git commit -m "feat(projects): add project/environment/link mutation hooks"
```

---

### Task 14: `modules/projects` UI — list page, form dialogs, detail view

No automated test; verified by Step 5's manual check. No `@radix-ui/*` packages are installed in this repo (verified via `package.json`) — every `shared/ui/*` component here is a hand-built Tailwind component, not a Radix wrapper (`confirm-dialog.tsx` is a plain fixed-position modal). The environment tabs below follow that same hand-rolled convention rather than introducing a new dependency for one screen.

**Files:**
- Create: `frontend/src/modules/projects/ui/projects-page-content.tsx`
- Create: `frontend/src/modules/projects/ui/project-form-dialog.tsx`
- Create: `frontend/src/modules/projects/ui/environment-form-dialog.tsx`
- Create: `frontend/src/modules/projects/ui/project-link-form-dialog.tsx`
- Create: `frontend/src/modules/projects/ui/project-detail-view.tsx`
- Create: `frontend/src/modules/projects/index.ts`

**Interfaces:**
- Consumes: `useProjectsQuery`/`useProjectQuery` (`entities/project`), `useProjectEnvironmentsQuery` (`entities/environment`), all 9 mutation hooks (Task 13), `Can`/`RequirePermission` (`entities/permission`), `Button`/`Input`/`Label`/`ConfirmDialog`/`Skeleton` (`shared/ui`).
- Produces: `ProjectsPageContent`, `ProjectDetailView` — consumed by Task 15's `admin/projects/page.tsx` and `admin/projects/[projectId]/page.tsx`.

- [ ] **Step 1: `ui/projects-page-content.tsx`**

```typescript
"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { FolderKanban, Plus, Pencil, Trash2 } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { ConfirmDialog } from "@/shared/ui/confirm-dialog";
import { Can } from "@/entities/permission";
import { useProjectsQuery, type Project } from "@/entities/project";
import { Link } from "@/shared/lib/i18n/navigation";
import { ROUTES } from "@/shared/constants/routes";
import { useDeleteProject } from "../hooks/use-delete-project";
import { ProjectFormDialog } from "./project-form-dialog";

export function ProjectsPageContent() {
  const t = useTranslations("projects");
  const { data } = useProjectsQuery(50, 0);
  const deleteProject = useDeleteProject();

  const [formTarget, setFormTarget] = useState<Project | "create" | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Project | null>(null);

  return (
    <div className="flex flex-1 flex-col gap-6">
      <div className="flex items-center justify-between">
        <div className="flex flex-col gap-1">
          <h1 className="text-xl font-bold text-foreground">{t("title")}</h1>
          <p className="text-sm text-muted-foreground">{t("description")}</p>
        </div>
        <Can I="create" a="project">
          <Button onClick={() => setFormTarget("create")}>
            <Plus className="mr-2 size-4" />
            {t("actions.create")}
          </Button>
        </Can>
      </div>

      {data.items.length === 0 ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-3 rounded-xl border bg-card py-16 text-center">
          <div className="flex size-12 items-center justify-center rounded-xl bg-muted text-muted-foreground">
            <FolderKanban className="size-6" aria-hidden />
          </div>
          <h2 className="text-lg font-semibold text-foreground">{t("empty.title")}</h2>
          <p className="max-w-sm text-sm text-muted-foreground">{t("empty.description")}</p>
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border bg-card">
          <table className="w-full text-sm">
            <thead className="border-b bg-muted/40 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              <tr>
                <th className="px-4 py-3">{t("table.name")}</th>
                <th className="px-4 py-3">{t("table.description")}</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y">
              {data.items.map((project) => (
                <tr key={project.id} className="hover:bg-muted/30">
                  <td className="px-4 py-3 font-medium text-foreground">
                    <Link
                      href={`${ROUTES.adminProjects}/${project.id}`}
                      className="hover:underline"
                    >
                      {project.name}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {project.description ?? "—"}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex justify-end gap-2">
                      <Can I="update" a="project">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setFormTarget(project)}
                        >
                          <Pencil className="size-3.5" />
                        </Button>
                      </Can>
                      <Can I="delete" a="project">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setDeleteTarget(project)}
                        >
                          <Trash2 className="size-3.5" />
                        </Button>
                      </Can>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {formTarget !== null && (
        <ProjectFormDialog
          isOpen
          onClose={() => setFormTarget(null)}
          project={formTarget === "create" ? null : formTarget}
        />
      )}

      <ConfirmDialog
        isOpen={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => {
          if (deleteTarget) {
            deleteProject.mutate(deleteTarget.id, { onSuccess: () => setDeleteTarget(null) });
          }
        }}
        title={t("deleteConfirm.title")}
        description={t("deleteConfirm.description", { name: deleteTarget?.name ?? "" })}
        isLoading={deleteProject.isPending}
      />
    </div>
  );
}
```

- [ ] **Step 2: `ui/project-form-dialog.tsx`**

```typescript
"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { X, FolderKanban } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { Label } from "@/shared/ui/label";
import { useApiErrorMessage } from "@/shared/lib/handle-api-error";
import type { Project } from "@/entities/project";
import { useCreateProject } from "../hooks/use-create-project";
import { useUpdateProject } from "../hooks/use-update-project";

interface ProjectFormDialogProps {
  isOpen: boolean;
  onClose: () => void;
  project?: Project | null;
}

export function ProjectFormDialog({ isOpen, onClose, project }: ProjectFormDialogProps) {
  const t = useTranslations("projects");
  const getErrorMessage = useApiErrorMessage("projects");
  const createProject = useCreateProject();
  const updateProject = useUpdateProject();

  const isEditing = Boolean(project);
  const [name, setName] = useState(() => project?.name ?? "");
  const [description, setDescription] = useState(() => project?.description ?? "");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  if (!isOpen) return null;

  const isPending = createProject.isPending || updateProject.isPending;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);
    const callbacks = {
      onSuccess: () => onClose(),
      onError: (err: unknown) => setErrorMessage(getErrorMessage(err)),
    };

    if (isEditing && project) {
      updateProject.mutate({ id: project.id, data: { name, description } }, callbacks);
    } else {
      createProject.mutate({ name, description }, callbacks);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-xs animate-in fade-in-0"
      role="dialog"
      aria-modal="true"
    >
      <div className="flex w-full max-w-md flex-col rounded-2xl border bg-card shadow-2xl animate-in zoom-in-95">
        <div className="flex items-center justify-between border-b px-6 py-4">
          <div className="flex items-center gap-2.5">
            <div className="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <FolderKanban className="size-4" />
            </div>
            <h2 className="text-lg font-bold text-foreground">
              {isEditing ? t("editProject") : t("createProject")}
            </h2>
          </div>
          <button type="button" onClick={onClose} className="cursor-pointer rounded-lg p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground">
            <X className="size-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4 p-6">
          {errorMessage && (
            <div role="alert" className="rounded-lg border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive">
              {errorMessage}
            </div>
          )}

          <div className="space-y-2">
            <Label htmlFor="project-name">{t("form.nameLabel")}</Label>
            <Input id="project-name" value={name} onChange={(e) => setName(e.target.value)} required className="h-10" />
          </div>

          <div className="space-y-2">
            <Label htmlFor="project-description">{t("form.descriptionLabel")}</Label>
            <Input id="project-description" value={description} onChange={(e) => setDescription(e.target.value)} className="h-10" />
          </div>

          <div className="mt-2 flex items-center justify-end gap-3">
            <Button type="button" variant="outline" onClick={onClose} disabled={isPending}>
              {t("form.cancel")}
            </Button>
            <Button type="submit" disabled={isPending || !name.trim()}>
              {isPending ? t("form.saving") : isEditing ? t("form.save") : t("form.create")}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: `ui/environment-form-dialog.tsx`, `ui/project-link-form-dialog.tsx`** — same shape as Step 2, condensed (full file, not a placeholder):

```typescript
// frontend/src/modules/projects/ui/environment-form-dialog.tsx
"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { X, Server } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { Label } from "@/shared/ui/label";
import { useApiErrorMessage } from "@/shared/lib/handle-api-error";
import { ENVIRONMENT_TYPES, type Environment, type EnvironmentType } from "@/entities/environment";
import { useCreateEnvironment } from "../hooks/use-create-environment";
import { useUpdateEnvironment } from "../hooks/use-update-environment";

interface EnvironmentFormDialogProps {
  isOpen: boolean;
  onClose: () => void;
  projectId: string;
  environment?: Environment | null;
  existingTypes: EnvironmentType[];
}

export function EnvironmentFormDialog({
  isOpen,
  onClose,
  projectId,
  environment,
  existingTypes,
}: EnvironmentFormDialogProps) {
  const t = useTranslations("projects");
  const getErrorMessage = useApiErrorMessage("projects");
  const createEnvironment = useCreateEnvironment(projectId);
  const updateEnvironment = useUpdateEnvironment(projectId);

  const isEditing = Boolean(environment);
  const [type, setType] = useState<EnvironmentType>(environment?.type ?? "dev");
  const [name, setName] = useState(() => environment?.name ?? "");
  const [baseUrl, setBaseUrl] = useState(() => environment?.baseUrl ?? "");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  if (!isOpen) return null;

  const isPending = createEnvironment.isPending || updateEnvironment.isPending;
  const availableTypes = ENVIRONMENT_TYPES.filter(
    (t) => t === environment?.type || !existingTypes.includes(t),
  );

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);
    const callbacks = {
      onSuccess: () => onClose(),
      onError: (err: unknown) => setErrorMessage(getErrorMessage(err)),
    };

    if (isEditing && environment) {
      updateEnvironment.mutate({ id: environment.id, data: { name, baseUrl } }, callbacks);
    } else {
      createEnvironment.mutate({ type, name, baseUrl }, callbacks);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-xs animate-in fade-in-0" role="dialog" aria-modal="true">
      <div className="flex w-full max-w-md flex-col rounded-2xl border bg-card shadow-2xl animate-in zoom-in-95">
        <div className="flex items-center justify-between border-b px-6 py-4">
          <div className="flex items-center gap-2.5">
            <div className="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Server className="size-4" />
            </div>
            <h2 className="text-lg font-bold text-foreground">
              {isEditing ? t("editEnvironment") : t("createEnvironment")}
            </h2>
          </div>
          <button type="button" onClick={onClose} className="cursor-pointer rounded-lg p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground">
            <X className="size-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4 p-6">
          {errorMessage && (
            <div role="alert" className="rounded-lg border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive">
              {errorMessage}
            </div>
          )}

          <div className="space-y-2">
            <Label htmlFor="env-type">{t("form.typeLabel")}</Label>
            <select
              id="env-type"
              value={type}
              onChange={(e) => setType(e.target.value as EnvironmentType)}
              disabled={isEditing}
              className="h-10 w-full rounded-md border bg-background px-3 text-sm disabled:opacity-60"
            >
              {availableTypes.map((envType) => (
                <option key={envType} value={envType}>
                  {t(`environmentTypes.${envType}`)}
                </option>
              ))}
            </select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="env-name">{t("form.nameLabel")}</Label>
            <Input id="env-name" value={name} onChange={(e) => setName(e.target.value)} required className="h-10" />
          </div>

          <div className="space-y-2">
            <Label htmlFor="env-base-url">{t("form.baseUrlLabel")}</Label>
            <Input id="env-base-url" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} className="h-10" />
          </div>

          <div className="mt-2 flex items-center justify-end gap-3">
            <Button type="button" variant="outline" onClick={onClose} disabled={isPending}>
              {t("form.cancel")}
            </Button>
            <Button type="submit" disabled={isPending || !name.trim()}>
              {isPending ? t("form.saving") : isEditing ? t("form.save") : t("form.create")}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
```

```typescript
// frontend/src/modules/projects/ui/project-link-form-dialog.tsx
"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { X, Link2 } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { Label } from "@/shared/ui/label";
import { useApiErrorMessage } from "@/shared/lib/handle-api-error";
import type { ProjectLink } from "../api/fetchers";
import { useCreateProjectLink } from "../hooks/use-create-project-link";
import { useUpdateProjectLink } from "../hooks/use-update-project-link";

interface ProjectLinkFormDialogProps {
  isOpen: boolean;
  onClose: () => void;
  projectId: string;
  link?: ProjectLink | null;
}

export function ProjectLinkFormDialog({ isOpen, onClose, projectId, link }: ProjectLinkFormDialogProps) {
  const t = useTranslations("projects");
  const getErrorMessage = useApiErrorMessage("projects");
  const createLink = useCreateProjectLink(projectId);
  const updateLink = useUpdateProjectLink(projectId);

  const isEditing = Boolean(link);
  const [type, setType] = useState(link?.type ?? "other");
  const [name, setName] = useState(() => link?.name ?? "");
  const [url, setUrl] = useState(() => link?.url ?? "");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  if (!isOpen) return null;

  const isPending = createLink.isPending || updateLink.isPending;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);
    const callbacks = {
      onSuccess: () => onClose(),
      onError: (err: unknown) => setErrorMessage(getErrorMessage(err)),
    };

    if (isEditing && link) {
      updateLink.mutate({ id: link.id, data: { name, url } }, callbacks);
    } else {
      createLink.mutate({ type, name, url }, callbacks);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-xs animate-in fade-in-0" role="dialog" aria-modal="true">
      <div className="flex w-full max-w-md flex-col rounded-2xl border bg-card shadow-2xl animate-in zoom-in-95">
        <div className="flex items-center justify-between border-b px-6 py-4">
          <div className="flex items-center gap-2.5">
            <div className="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Link2 className="size-4" />
            </div>
            <h2 className="text-lg font-bold text-foreground">
              {isEditing ? t("editLink") : t("createLink")}
            </h2>
          </div>
          <button type="button" onClick={onClose} className="cursor-pointer rounded-lg p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground">
            <X className="size-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4 p-6">
          {errorMessage && (
            <div role="alert" className="rounded-lg border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive">
              {errorMessage}
            </div>
          )}

          <div className="space-y-2">
            <Label htmlFor="link-type">{t("form.linkTypeLabel")}</Label>
            <select
              id="link-type"
              value={type}
              onChange={(e) => setType(e.target.value as "jira" | "git" | "other")}
              disabled={isEditing}
              className="h-10 w-full rounded-md border bg-background px-3 text-sm disabled:opacity-60"
            >
              <option value="jira">{t("linkTypes.jira")}</option>
              <option value="git">{t("linkTypes.git")}</option>
              <option value="other">{t("linkTypes.other")}</option>
            </select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="link-name">{t("form.nameLabel")}</Label>
            <Input id="link-name" value={name} onChange={(e) => setName(e.target.value)} required className="h-10" />
          </div>

          <div className="space-y-2">
            <Label htmlFor="link-url">{t("form.urlLabel")}</Label>
            <Input id="link-url" value={url} onChange={(e) => setUrl(e.target.value)} required className="h-10" />
          </div>

          <div className="mt-2 flex items-center justify-end gap-3">
            <Button type="button" variant="outline" onClick={onClose} disabled={isPending}>
              {t("form.cancel")}
            </Button>
            <Button type="submit" disabled={isPending || !name.trim() || !url.trim()}>
              {isPending ? t("form.saving") : isEditing ? t("form.save") : t("form.create")}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: `ui/project-detail-view.tsx` — environment tabs (hand-rolled, no Radix) + links list**

```typescript
"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { Plus, Pencil, Trash2, Server, Link2 } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { ConfirmDialog } from "@/shared/ui/confirm-dialog";
import { Can } from "@/entities/permission";
import { useProjectQuery } from "@/entities/project";
import { useProjectEnvironmentsQuery, type Environment } from "@/entities/environment";
import { fetchProjectLinks, type ProjectLink } from "../api/fetchers";
import { useDeleteEnvironment } from "../hooks/use-delete-environment";
import { useDeleteProjectLink } from "../hooks/use-delete-project-link";
import { EnvironmentFormDialog } from "./environment-form-dialog";
import { ProjectLinkFormDialog } from "./project-link-form-dialog";

export function ProjectDetailView({ projectId }: { projectId: string }) {
  const t = useTranslations("projects");
  const { data: project } = useProjectQuery(projectId);
  const { data: environments } = useProjectEnvironmentsQuery(projectId);
  const { data: links = [] } = useQuery({
    queryKey: ["projects", "links", projectId],
    queryFn: () => fetchProjectLinks(projectId),
  });

  const deleteEnvironment = useDeleteEnvironment(projectId);
  const deleteLink = useDeleteProjectLink(projectId);

  const [envFormTarget, setEnvFormTarget] = useState<Environment | "create" | null>(null);
  const [envDeleteTarget, setEnvDeleteTarget] = useState<Environment | null>(null);
  const [linkFormTarget, setLinkFormTarget] = useState<ProjectLink | "create" | null>(null);
  const [linkDeleteTarget, setLinkDeleteTarget] = useState<ProjectLink | null>(null);

  return (
    <div className="flex flex-1 flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-xl font-bold text-foreground">{project.name}</h1>
        {project.description && <p className="text-sm text-muted-foreground">{project.description}</p>}
      </div>

      <section className="flex flex-col gap-3 rounded-xl border bg-card p-5">
        <div className="flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-sm font-bold text-foreground">
            <Server className="size-4" /> {t("sections.environments")}
          </h2>
          <Can I="create" a="environment">
            <Button size="sm" onClick={() => setEnvFormTarget("create")}>
              <Plus className="mr-1.5 size-3.5" /> {t("actions.addEnvironment")}
            </Button>
          </Can>
        </div>
        <div className="flex flex-wrap gap-2">
          {environments.length === 0 && (
            <p className="text-sm text-muted-foreground">{t("empty.environments")}</p>
          )}
          {environments.map((env) => (
            <div
              key={env.id}
              className="flex items-center gap-2 rounded-lg border bg-muted/30 px-3 py-2 text-sm"
            >
              <span className="font-semibold uppercase tracking-wide text-foreground">
                {t(`environmentTypes.${env.type}`)}
              </span>
              <span className="text-muted-foreground">{env.name}</span>
              <Can I="update" a="environment">
                <button
                  type="button"
                  onClick={() => setEnvFormTarget(env)}
                  className="cursor-pointer text-muted-foreground hover:text-foreground"
                >
                  <Pencil className="size-3.5" />
                </button>
              </Can>
              <Can I="delete" a="environment">
                <button
                  type="button"
                  onClick={() => setEnvDeleteTarget(env)}
                  className="cursor-pointer text-muted-foreground hover:text-destructive"
                >
                  <Trash2 className="size-3.5" />
                </button>
              </Can>
            </div>
          ))}
        </div>
      </section>

      <section className="flex flex-col gap-3 rounded-xl border bg-card p-5">
        <div className="flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-sm font-bold text-foreground">
            <Link2 className="size-4" /> {t("sections.links")}
          </h2>
          <Can I="update" a="project">
            <Button size="sm" onClick={() => setLinkFormTarget("create")}>
              <Plus className="mr-1.5 size-3.5" /> {t("actions.addLink")}
            </Button>
          </Can>
        </div>
        <div className="flex flex-col divide-y">
          {links.length === 0 && <p className="text-sm text-muted-foreground">{t("empty.links")}</p>}
          {links.map((link) => (
            <div key={link.id} className="flex items-center justify-between py-2 text-sm">
              <div className="flex items-center gap-2">
                <span className="font-medium text-foreground">{link.name}</span>
                {link.isDefault && (
                  <span className="rounded-full bg-blue-50 px-2 py-0.5 text-[10px] font-bold uppercase text-blue-700 dark:bg-blue-950/60 dark:text-blue-300">
                    {t("badges.default")}
                  </span>
                )}
                <a
                  href={link.url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-muted-foreground hover:underline"
                >
                  {link.url}
                </a>
              </div>
              <Can I="update" a="project">
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => setLinkFormTarget(link)}
                    className="cursor-pointer text-muted-foreground hover:text-foreground"
                  >
                    <Pencil className="size-3.5" />
                  </button>
                  <button
                    type="button"
                    onClick={() => setLinkDeleteTarget(link)}
                    className="cursor-pointer text-muted-foreground hover:text-destructive"
                  >
                    <Trash2 className="size-3.5" />
                  </button>
                </div>
              </Can>
            </div>
          ))}
        </div>
      </section>

      {envFormTarget !== null && (
        <EnvironmentFormDialog
          isOpen
          onClose={() => setEnvFormTarget(null)}
          projectId={projectId}
          environment={envFormTarget === "create" ? null : envFormTarget}
          existingTypes={environments.map((e) => e.type)}
        />
      )}
      <ConfirmDialog
        isOpen={envDeleteTarget !== null}
        onClose={() => setEnvDeleteTarget(null)}
        onConfirm={() => {
          if (envDeleteTarget) {
            deleteEnvironment.mutate(envDeleteTarget.id, { onSuccess: () => setEnvDeleteTarget(null) });
          }
        }}
        title={t("deleteConfirm.environmentTitle")}
        description={t("deleteConfirm.environmentDescription", { name: envDeleteTarget?.name ?? "" })}
        isLoading={deleteEnvironment.isPending}
      />

      {linkFormTarget !== null && (
        <ProjectLinkFormDialog
          isOpen
          onClose={() => setLinkFormTarget(null)}
          projectId={projectId}
          link={linkFormTarget === "create" ? null : linkFormTarget}
        />
      )}
      <ConfirmDialog
        isOpen={linkDeleteTarget !== null}
        onClose={() => setLinkDeleteTarget(null)}
        onConfirm={() => {
          if (linkDeleteTarget) {
            deleteLink.mutate(linkDeleteTarget.id, { onSuccess: () => setLinkDeleteTarget(null) });
          }
        }}
        title={t("deleteConfirm.linkTitle")}
        description={t("deleteConfirm.linkDescription", { name: linkDeleteTarget?.name ?? "" })}
        isLoading={deleteLink.isPending}
      />
    </div>
  );
}
```

- [ ] **Step 5: `index.ts` + manual verification**

```typescript
// frontend/src/modules/projects/index.ts
export { ProjectsPageContent } from "./ui/projects-page-content";
export { ProjectDetailView } from "./ui/project-detail-view";
export { createProject, updateProject, deleteProject, fetchProjectLinks } from "./api/fetchers";
export type { ProjectLink } from "./api/fetchers";
```

Run: `cd frontend && npx tsc --noEmit && npm run lint`
Expected: no errors. `eslint-plugin-boundaries` must show zero violations — `modules/projects` only imports `entities/project`, `entities/environment`, `entities/permission`, and `shared/*`.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/modules/projects/ui frontend/src/modules/projects/index.ts
git commit -m "feat(projects): add projects list, detail, and form UI"
```

---

### Task 15: Route wiring — routes, permissions, sidebar, pages, i18n

No automated test; verified by Step 8's manual check (this is where Phase 1 becomes clickable end-to-end).

**Files:**
- Modify: `frontend/src/shared/constants/routes.ts`, `frontend/src/shared/constants/permissions.ts`, `frontend/src/app/[locale]/(dashboard)/dashboard-sidebar.tsx`, `frontend/src/shared/lib/i18n/request.ts`
- Create: `frontend/src/app/[locale]/(dashboard)/admin/projects/page.tsx`, `.../loading.tsx`, `.../[projectId]/page.tsx`, `.../[projectId]/loading.tsx`
- Create: `frontend/locales/en/modules/projects.json`, `frontend/locales/vi/modules/projects.json`

**Interfaces:**
- Consumes: `ProjectsPageContent`/`ProjectDetailView` (Task 14), `fetchProjects`/`fetchProject`/`projectsKeys` (Task 12), `fetchProjectEnvironments`/`environmentsKeys` (Task 12), `hasPermission`/`RequirePermission`/`NoPermission` (`entities/permission`), `fetchAuthSession` (`modules/auth`).
- Produces: `/admin/projects` and `/admin/projects/{id}` live routes.

- [ ] **Step 1: `shared/constants/routes.ts`**

```typescript
export const ROUTES = {
  login: "/login",
  dashboard: "/dashboard",
  adminUsers: "/admin/users",
  adminRoles: "/admin/roles",
  adminProjects: "/admin/projects",
} as const;
```

- [ ] **Step 2: `shared/constants/permissions.ts`**

```typescript
// frontend/src/shared/constants/permissions.ts — additions
export const RESOURCES = {
  ROLE: "role",
  PERMISSION: "permission",
  USER: "user",
  PROJECT: "project",
  ENVIRONMENT: "environment",
} as const;

export type Resource = (typeof RESOURCES)[keyof typeof RESOURCES];

export const ACTIONS = {
  CREATE: "create",
  READ: "read",
  UPDATE: "update",
  DELETE: "delete",
  UPDATE_STATUS: "update_status",
  ASSIGN_ROLE: "assign_role",
} as const;

export type Action = (typeof ACTIONS)[keyof typeof ACTIONS];

export const PERMISSIONS = {
  ROLE: {
    RESOURCE: RESOURCES.ROLE,
    CREATE: `${RESOURCES.ROLE}.${ACTIONS.CREATE}` as const,
    READ: `${RESOURCES.ROLE}.${ACTIONS.READ}` as const,
    UPDATE: `${RESOURCES.ROLE}.${ACTIONS.UPDATE}` as const,
    DELETE: `${RESOURCES.ROLE}.${ACTIONS.DELETE}` as const,
  },
  PERMISSION: {
    RESOURCE: RESOURCES.PERMISSION,
    READ: `${RESOURCES.PERMISSION}.${ACTIONS.READ}` as const,
  },
  USER: {
    RESOURCE: RESOURCES.USER,
    READ: `${RESOURCES.USER}.${ACTIONS.READ}` as const,
    UPDATE_STATUS: `${RESOURCES.USER}.${ACTIONS.UPDATE_STATUS}` as const,
    ASSIGN_ROLE: `${RESOURCES.USER}.${ACTIONS.ASSIGN_ROLE}` as const,
  },
  PROJECT: {
    RESOURCE: RESOURCES.PROJECT,
    CREATE: `${RESOURCES.PROJECT}.${ACTIONS.CREATE}` as const,
    READ: `${RESOURCES.PROJECT}.${ACTIONS.READ}` as const,
    UPDATE: `${RESOURCES.PROJECT}.${ACTIONS.UPDATE}` as const,
    DELETE: `${RESOURCES.PROJECT}.${ACTIONS.DELETE}` as const,
  },
  ENVIRONMENT: {
    RESOURCE: RESOURCES.ENVIRONMENT,
    CREATE: `${RESOURCES.ENVIRONMENT}.${ACTIONS.CREATE}` as const,
    READ: `${RESOURCES.ENVIRONMENT}.${ACTIONS.READ}` as const,
    UPDATE: `${RESOURCES.ENVIRONMENT}.${ACTIONS.UPDATE}` as const,
    DELETE: `${RESOURCES.ENVIRONMENT}.${ACTIONS.DELETE}` as const,
  },
} as const;
```

- [ ] **Step 3: `admin/projects/page.tsx` + `loading.tsx`**

```typescript
// frontend/src/app/[locale]/(dashboard)/admin/projects/page.tsx
import { setRequestLocale } from "next-intl/server";
import { HydrationBoundary, dehydrate } from "@tanstack/react-query";
import { createQueryClient } from "@/shared/lib/query-client";
import { RequirePermission, NoPermission, hasPermission } from "@/entities/permission";
import { fetchAuthSession } from "@/modules/auth";
import { RESOURCES, ACTIONS } from "@/shared/constants/permissions";
import { fetchProjects, projectsKeys } from "@/entities/project";
import { ProjectsPageContent } from "@/modules/projects";

export default async function AdminProjectsPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);

  const session = await fetchAuthSession();
  const canReadProjects = hasPermission(session, RESOURCES.PROJECT, ACTIONS.READ);

  const queryClient = createQueryClient();
  if (canReadProjects) {
    await queryClient.prefetchQuery({
      queryKey: projectsKeys.list({ limit: 50, offset: 0 }),
      queryFn: () => fetchProjects(50, 0),
    });
  }

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <RequirePermission
        resource={RESOURCES.PROJECT}
        action={ACTIONS.READ}
        fallback={<NoPermission />}
      >
        <ProjectsPageContent />
      </RequirePermission>
    </HydrationBoundary>
  );
}
```

```typescript
// frontend/src/app/[locale]/(dashboard)/admin/projects/loading.tsx
import { Skeleton } from "@/shared/ui/skeleton";

export default function AdminProjectsLoading() {
  return (
    <div className="flex flex-1 flex-col gap-6">
      <div className="flex flex-col gap-2">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-4 w-72" />
      </div>
      <div className="overflow-hidden rounded-xl border bg-card p-6">
        <div className="space-y-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="flex items-center justify-between py-2">
              <Skeleton className="h-4 w-40" />
              <Skeleton className="h-4 w-56" />
              <div className="flex gap-2">
                <Skeleton className="h-8 w-8 rounded-md" />
                <Skeleton className="h-8 w-8 rounded-md" />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: `admin/projects/[projectId]/page.tsx` + `loading.tsx`**

Fetching both the project and its environments in one `Promise.all` before deciding what to render is the same pattern `admin/roles/page.tsx` uses for roles+permissions — not new here, just applied to a second resource pair.

```typescript
// frontend/src/app/[locale]/(dashboard)/admin/projects/[projectId]/page.tsx
import { setRequestLocale } from "next-intl/server";
import { HydrationBoundary, dehydrate } from "@tanstack/react-query";
import { createQueryClient } from "@/shared/lib/query-client";
import { RequirePermission, NoPermission, hasPermission } from "@/entities/permission";
import { fetchAuthSession } from "@/modules/auth";
import { RESOURCES, ACTIONS } from "@/shared/constants/permissions";
import { fetchProject, projectsKeys } from "@/entities/project";
import { fetchProjectEnvironments, environmentsKeys } from "@/entities/environment";
import { ProjectDetailView } from "@/modules/projects";

export default async function AdminProjectDetailPage({
  params,
}: {
  params: Promise<{ locale: string; projectId: string }>;
}) {
  const { locale, projectId } = await params;
  setRequestLocale(locale);

  const session = await fetchAuthSession();
  const canReadProjects = hasPermission(session, RESOURCES.PROJECT, ACTIONS.READ);

  const queryClient = createQueryClient();
  if (canReadProjects) {
    await Promise.all([
      queryClient.prefetchQuery({
        queryKey: projectsKeys.detail(projectId),
        queryFn: () => fetchProject(projectId),
      }),
      queryClient.prefetchQuery({
        queryKey: environmentsKeys.forProject(projectId),
        queryFn: () => fetchProjectEnvironments(projectId),
      }),
    ]);
  }

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <RequirePermission
        resource={RESOURCES.PROJECT}
        action={ACTIONS.READ}
        fallback={<NoPermission />}
      >
        <ProjectDetailView projectId={projectId} />
      </RequirePermission>
    </HydrationBoundary>
  );
}
```

```typescript
// frontend/src/app/[locale]/(dashboard)/admin/projects/[projectId]/loading.tsx
import { Skeleton } from "@/shared/ui/skeleton";

export default function AdminProjectDetailLoading() {
  return (
    <div className="flex flex-1 flex-col gap-6">
      <Skeleton className="h-8 w-64" />
      <div className="rounded-xl border bg-card p-5">
        <Skeleton className="h-24 w-full" />
      </div>
      <div className="rounded-xl border bg-card p-5">
        <Skeleton className="h-24 w-full" />
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Sidebar nav entry**

```typescript
// frontend/src/app/[locale]/(dashboard)/dashboard-sidebar.tsx — add to navItems (after adminRoles), and add the FolderKanban import alongside the existing lucide-react imports
    {
      href: ROUTES.adminProjects,
      label: t("projects"),
      icon: FolderKanban,
      active: pathname === ROUTES.adminProjects,
      permission: { action: "read", resource: "project" },
    },
```

- [ ] **Step 6: i18n — `locales/en/modules/projects.json`, `locales/vi/modules/projects.json`, register in `request.ts`**

```json
// frontend/locales/en/modules/projects.json
{
  "title": "Projects",
  "description": "Manage projects, their environments, and external links.",
  "createProject": "Create Project",
  "editProject": "Edit Project",
  "createEnvironment": "Add Environment",
  "editEnvironment": "Edit Environment",
  "createLink": "Add Link",
  "editLink": "Edit Link",
  "actions": {
    "create": "New Project",
    "addEnvironment": "Add",
    "addLink": "Add"
  },
  "table": {
    "name": "Name",
    "description": "Description"
  },
  "sections": {
    "environments": "Environments",
    "links": "External Links"
  },
  "environmentTypes": {
    "dev": "Dev",
    "staging": "Staging",
    "production": "Production"
  },
  "linkTypes": {
    "jira": "Jira",
    "git": "Git",
    "other": "Other"
  },
  "badges": {
    "default": "Default"
  },
  "empty": {
    "title": "No projects yet",
    "description": "Create your first project to start managing environments, Cloudflare, and logs.",
    "environments": "No environments yet.",
    "links": "No links yet."
  },
  "form": {
    "nameLabel": "Name",
    "descriptionLabel": "Description",
    "typeLabel": "Type",
    "baseUrlLabel": "Base URL",
    "linkTypeLabel": "Link type",
    "urlLabel": "URL",
    "cancel": "Cancel",
    "save": "Save",
    "create": "Create",
    "saving": "Saving..."
  },
  "deleteConfirm": {
    "title": "Delete project?",
    "description": "This will permanently delete \"{name}\" and every environment and link attached to it.",
    "environmentTitle": "Delete environment?",
    "environmentDescription": "This will permanently delete the \"{name}\" environment.",
    "linkTitle": "Delete link?",
    "linkDescription": "This will permanently delete the \"{name}\" link."
  },
  "errors": {
    "projects_project_not_found": "Project not found.",
    "projects_environment_not_found": "Environment not found.",
    "projects_environment_type_already_exists": "This project already has an environment of that type.",
    "projects_project_link_not_found": "Link not found."
  }
}
```

```json
// frontend/locales/vi/modules/projects.json
{
  "title": "Dự án",
  "description": "Quản lý dự án, môi trường, và các liên kết ngoài.",
  "createProject": "Tạo dự án",
  "editProject": "Sửa dự án",
  "createEnvironment": "Thêm môi trường",
  "editEnvironment": "Sửa môi trường",
  "createLink": "Thêm liên kết",
  "editLink": "Sửa liên kết",
  "actions": {
    "create": "Dự án mới",
    "addEnvironment": "Thêm",
    "addLink": "Thêm"
  },
  "table": {
    "name": "Tên",
    "description": "Mô tả"
  },
  "sections": {
    "environments": "Môi trường",
    "links": "Liên kết ngoài"
  },
  "environmentTypes": {
    "dev": "Dev",
    "staging": "Staging",
    "production": "Production"
  },
  "linkTypes": {
    "jira": "Jira",
    "git": "Git",
    "other": "Khác"
  },
  "badges": {
    "default": "Mặc định"
  },
  "empty": {
    "title": "Chưa có dự án nào",
    "description": "Tạo dự án đầu tiên để bắt đầu quản lý môi trường, Cloudflare và log.",
    "environments": "Chưa có môi trường nào.",
    "links": "Chưa có liên kết nào."
  },
  "form": {
    "nameLabel": "Tên",
    "descriptionLabel": "Mô tả",
    "typeLabel": "Loại",
    "baseUrlLabel": "Base URL",
    "linkTypeLabel": "Loại liên kết",
    "urlLabel": "URL",
    "cancel": "Huỷ",
    "save": "Lưu",
    "create": "Tạo",
    "saving": "Đang lưu..."
  },
  "deleteConfirm": {
    "title": "Xoá dự án?",
    "description": "Thao tác này sẽ xoá vĩnh viễn \"{name}\" cùng mọi môi trường và liên kết thuộc dự án.",
    "environmentTitle": "Xoá môi trường?",
    "environmentDescription": "Thao tác này sẽ xoá vĩnh viễn môi trường \"{name}\".",
    "linkTitle": "Xoá liên kết?",
    "linkDescription": "Thao tác này sẽ xoá vĩnh viễn liên kết \"{name}\"."
  },
  "errors": {
    "projects_project_not_found": "Không tìm thấy dự án.",
    "projects_environment_not_found": "Không tìm thấy môi trường.",
    "projects_environment_type_already_exists": "Dự án đã có môi trường loại này.",
    "projects_project_link_not_found": "Không tìm thấy liên kết."
  }
}
```

```typescript
// frontend/src/shared/lib/i18n/request.ts — full replacement
import { getRequestConfig } from "next-intl/server";
import { hasLocale } from "next-intl";
import { routing } from "./routing";

export default getRequestConfig(async ({ requestLocale }) => {
  const requested = await requestLocale;
  const locale = hasLocale(routing.locales, requested)
    ? requested
    : routing.defaultLocale;

  const [common, auth, users, roles, projects] = await Promise.all([
    import(`../../../../locales/${locale}/common.json`),
    import(`../../../../locales/${locale}/modules/auth.json`),
    import(`../../../../locales/${locale}/modules/users.json`),
    import(`../../../../locales/${locale}/modules/roles.json`),
    import(`../../../../locales/${locale}/modules/projects.json`),
  ]);

  return {
    locale,
    messages: {
      common: common.default,
      auth: auth.default,
      users: users.default,
      roles: roles.default,
      projects: projects.default,
    },
  };
});
```

Also add `"projects": "Projects"` / `"projects": "Dự án"` to the `nav` block of `locales/{en,vi}/common.json` — `dashboard-sidebar.tsx`'s `t("projects")` (Step 5) reads from `common.nav`, same namespace as the existing `dashboard`/`users`/`roles` nav labels.

- [ ] **Step 7: Run boundary + type checks**

Run: `cd frontend && npm run lint && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 8: Manual end-to-end verification**

Run: `cd backend && uvicorn app.main:app --reload` (separate terminal) and `cd frontend && npm run dev`, then in a browser:
1. Log in as a user with `project:*`/`environment:*` permissions (or the seeded admin).
2. Navigate to `/admin/projects` — sidebar shows "Projects"/"Dự án" entry.
3. Create a project named "Website A" — if `PROJECTS__DEFAULT_JIRA_URL`/`PROJECTS__DEFAULT_GIT_URL` are set in `backend/.env`, opening its detail page shows 2 default links; otherwise 0, per `ProjectsRules.default_links()`.
4. Add a DEV, then STAGING, then PRODUCTION environment — the type dropdown excludes already-used types on the next add.
5. Attempt a 4th environment of an existing type via a direct API call (`curl -X POST .../environments -d '{"type":"dev","name":"x"}'`) — confirm `409 projects_environment_type_already_exists`.
6. Edit and delete an environment; add, edit, and delete a project link.
7. Log in as a user with none of these permissions — `/admin/projects` shows the "No permission" fallback, not the list.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/shared/constants/routes.ts frontend/src/shared/constants/permissions.ts frontend/src/app/[locale]/\(dashboard\)/dashboard-sidebar.tsx frontend/src/app/[locale]/\(dashboard\)/admin/projects frontend/src/shared/lib/i18n/request.ts frontend/locales/en/modules/projects.json frontend/locales/vi/modules/projects.json frontend/locales/en/common.json frontend/locales/vi/common.json
git commit -m "feat(projects): wire routes, permissions, sidebar, and i18n"
```

---

## Self-Review

**1. Spec coverage** (against `docs/tasks/devops-control-panel-schema.md` §2, §9, and the master plan's Phase 1 line):
- `projects`/`project_links`/`environments` tables → Task 1. ✅
- "tầng ứng dụng tự điền sẵn 2 dòng mặc định trỏ tới Jira/Git" → Task 3 (`ProjectsRules.default_links`) + Task 5 (`CreateProject`). ✅
- `environments.type` UNIQUE(project_id, type) → Task 1 (DB constraint) + Task 6 (`CreateEnvironment`'s pre-check + `EnvironmentTypeAlreadyExists`). ✅
- "Module đề xuất... projects (projects, project_links, environments)" → Task 2-11 is exactly this one module, no more. ✅
- Master plan's Phase 1 frontend line ("environment tabs (UNIQUE(project_id,type) enforced), links editor") → Task 14 (`ProjectDetailView`). ✅
- Master plan's Phase 1 demo script (create project → 2 links → add 3 environments → edit link → permission-gated list) → Task 15 Step 8 covers all five, plus the two negative cases (duplicate type, no-permission fallback) the demo script implied but didn't spell out.
- Gap found: the master plan's RBAC line said `entities/project`, `entities/environment` "promoted immediately" — Task 12 does this from the start (not deferred), confirmed no gap.

**2. Placeholder scan:** searched every task above for "TBD"/"TODO"/"implement later"/"add appropriate error handling" — none found. Every code block is complete, runnable code, not a description of code.

**3. Type consistency:** verified every service's `execute()` signature (Tasks 5-7) matches its router call site (Task 8) and its Fake-based test call site (Tasks 5-7) — all consistent. One inconsistency was found and fixed during this pass: `router.py` originally imported `EnvironmentNotFound`/`ProjectLinkNotFound` without ever raising them there (those are raised inside the use cases, not the router) — removed the unused imports, since `ruff`'s `F401` would fail Task 11 Step 5's full-suite run otherwise.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-08-21-devops-panel-phase1-projects-environments.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
