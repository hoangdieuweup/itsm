"""Templates for one domain module. The module owns everything it needs."""


def _cls(name: str) -> str:
    """Convert a module name into a class prefix."""
    return "".join(p.capitalize() for p in name.replace("-", "_").split("_"))


def constants(name: str) -> str:
    """Render the module owned enums, constants and error codes."""
    cls = _cls(name)
    return f'''
"""Constants and enums owned by the {name} module.

Other modules import these with an explicit alias:
    from app.modules.{name} import constants as {name}_constants

DO:
  - Define enums, error codes, numeric limits, cache identity, type aliases here.
  - Group every constant inside a class (e.g. {cls}Limits.MAX_NAME_LENGTH).
  - Expose type aliases (Literal, TypeAlias, TypeVar) as class attributes.

DO NOT:
  - Put bare top-level constants outside a class.
  - Define I/O, database calls, or framework imports here.
  - Import from other domain modules — constants are leaf nodes.
"""

from enum import StrEnum


class {cls}Limits:
    """Numeric limits owned by the {name} module."""

    MAX_NAME_LENGTH = 255
    MIN_NAME_LENGTH = 2
    DEFAULT_PAGE_SIZE = 50


class {cls}CacheKeys:
    """Cache identity owned by the {name} module. See references/caching.md."""

    ENTITY = "{name}"
    TTL_SECONDS = 300


class {cls}Events:
    """Messaging identity owned by the {name} module. See references/messaging.md."""

    EXCHANGE = "{name}"


class {cls}Status(StrEnum):
    """Lifecycle state of a {name}."""

    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"

    @property
    def is_visible(self) -> bool:
        """Return whether entities in this state appear in public listings."""
        return self is {cls}Status.ACTIVE


class ErrorCode(StrEnum):
    """Stable error codes returned to clients by this module."""

    NOT_FOUND = "{name}_not_found"
    NAME_TAKEN = "{name}_name_taken"
    INVALID_NAME = "{name}_invalid_name"
    NOT_ACTIVE = "{name}_not_active"
'''


def exceptions(name: str) -> str:
    """Render the concrete errors of this module, built on the shared bases."""
    cls = _cls(name)
    return f'''
"""Errors owned by the {name} module.

These live here rather than in a global module because each one encodes a fact
about {name}: what counts as missing, what counts as a conflict. The mechanism
they build on lives in app.core.exceptions.

DO:
  - Define concrete exception classes that extend base errors from app.core.exceptions.
  - Attach a stable ErrorCode and a fallback message to each class.
  - Import error codes from this module's own constants.py.

DO NOT:
  - Define generic/base exception classes here — those live in app.core.exceptions.
  - Include business logic, I/O, or framework imports.
  - Import from other domain modules.
"""

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.modules.{name}.constants import ErrorCode


class {cls}NotFound(NotFoundError):
    """Raised when no {name} matches the requested identifier."""

    code = ErrorCode.NOT_FOUND
    message = "{cls} not found"


class {cls}NameTaken(ConflictError):
    """Raised when another {name} already holds the requested name."""

    code = ErrorCode.NAME_TAKEN
    message = "Name already taken"


class Invalid{cls}Name(ValidationFailedError):
    """Raised when a name is well formed but violates the naming rule."""

    code = ErrorCode.INVALID_NAME
    message = "Name length out of range"


class {cls}NotActive(ValidationFailedError):
    """Raised when an operation requires an active {name}."""

    code = ErrorCode.NOT_ACTIVE
    message = "{cls} is not active"
'''


def config(name: str) -> str:
    """Render the module local settings."""
    cls = _cls(name)
    upper = name.upper()
    return f'''
"""Settings owned by the {name} module.

Splitting settings per module keeps the global config from turning into a
dumping ground and lets a module be extracted with its configuration intact.

DO:
  - Define settings this module reads from env vars (prefix {upper}__).
  - Use BaseSettings with SettingsConfigDict for typed env parsing.
  - Reference default values from this module's own constants.py.

DO NOT:
  - Put global settings here (DATABASE_URL, CORS_ORIGINS → app/config.py).
  - Use vendor names as prefix (e.g. REDIS__ → use CACHE__ instead).
  - Import from other domain modules.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.modules.{name}.constants import {cls}CacheKeys


class {cls}Config(BaseSettings):
    """Environment driven settings for the {name} module."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="{upper}__", extra="ignore")

    CACHE_TTL: int = {cls}CacheKeys.TTL_SECONDS
    LIST_PAGE_SIZE: int = 50


{name}_settings = {cls}Config()
'''


def schemas(name: str) -> str:
    """Render the Pydantic schemas of this module.

    Validation and serialization for a field live on the schema that owns
    that field, via Pydantic's own field_validator/field_serializer — never
    reimplemented ad hoc in the router or the service. A schema validator
    still calls into rules.py/utils/ rather than repeating their logic, so
    there is exactly one implementation of "what makes a name valid", invoked
    at the wire boundary here and defensively again in the use case, which
    remains independently callable from a worker, a CLI or a test. See
    references/layer-examples.md.
    """
    cls = _cls(name)
    return f'''
"""Schemas for the {name} module.

DO:
  - Define Pydantic models for request/response payloads.
  - Put field_validator / field_serializer on the schema that owns the field.
  - Call into rules.py / utils/ from validators — never reimplement their logic.
  - Inherit from CustomModel (mutable payloads) or FrozenModel (read responses).

DO NOT:
  - Define ORM models here — those live in models.py.
  - Put business logic beyond validation — that belongs in services/.
  - Return schemas that don't inherit CustomModel/FrozenModel (they miss camelCase alias).
  - Import from other domain modules — use public.py types if cross-module data is needed.
"""

from datetime import datetime

from pydantic import field_validator

from app.core.models import CustomModel, FrozenModel
from app.modules.{name}.constants import {cls}Status
from app.modules.{name}.rules import {cls}Rules
from app.modules.{name}.utils import {cls}TextUtils


class {cls}Read(FrozenModel):
    """Representation safe to round trip through the cache."""

    id: int
    name: str
    status: {cls}Status
    created_at: datetime


class {cls}Create(CustomModel):
    """Payload accepted by the create endpoint."""

    name: str

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        """Normalize then apply the same rule the use case enforces again."""
        normalized = {cls}TextUtils.normalize_name(value)
        if not {cls}Rules.is_valid_name(normalized):
            raise ValueError("name length out of range")
        return normalized


class {cls}Update(CustomModel):
    """Payload accepted by the update endpoint."""

    name: str | None = None
    status: {cls}Status | None = None

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str | None) -> str | None:
        """Normalize then apply the same rule the use case enforces again, skipping when absent."""
        if value is None:
            return None
        normalized = {cls}TextUtils.normalize_name(value)
        if not {cls}Rules.is_valid_name(normalized):
            raise ValueError("name length out of range")
        return normalized
'''


def models(name: str) -> str:
    """Render the ORM models owned by this module."""
    cls = _cls(name)
    return f'''
"""ORM models owned by the {name} module.

DO:
  - Define SQLAlchemy ORM models (tables) this module owns.
  - Use constants from this module's constants.py for column constraints.
  - One table = one owning module, no exceptions.

DO NOT:
  - Query or JOIN tables owned by another module — go through their public.py.
  - Return ORM model instances from endpoints — convert to Pydantic schemas.
  - Import from other domain modules.
  - Put business logic or validation here — those live in rules.py / schemas.py.
"""

from datetime import datetime

from sqlalchemy import DateTime, Enum, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.modules.{name}.constants import {cls}Limits, {cls}Status


class {cls}(Base):
    """Primary entity of the {name} module."""

    __tablename__ = "{name}"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String({cls}Limits.MAX_NAME_LENGTH), unique=True, index=True)
    status: Mapped[{cls}Status] = mapped_column(
        Enum({cls}Status, native_enum=False), default={cls}Status.DRAFT, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
'''


def rules(name: str) -> str:
    """Render the pure business rules of this module."""
    cls = _cls(name)
    return f'''
"""Business rules for the {name} module.

Everything here is a pure decision: no I/O, no framework, no database. That is
what keeps these testable without fixtures, and it is the difference between
this class and utils/, which holds non-business helpers.

DO:
  - Encode business decisions as pure functions (can_X, is_valid_X, should_X).
  - Group methods inside a single class, decorated with @rule.
  - Keep this file heavily unit-tested — no fixtures needed.

DO NOT:
  - Perform I/O (database, HTTP, cache) — those belong in repository/services.
  - Import framework code (FastAPI, SQLAlchemy).
  - Put formatting/normalization here — that belongs in utils/.
  - Define bare functions outside a class.
"""

from app.core.base.markers import rule
from app.modules.{name}.constants import {cls}Limits, {cls}Status


class {cls}Rules:
    """Every business decision about a {name}, grouped so call sites read as
    `{cls}Rules.is_valid_name(...)` instead of a bare import."""

    @staticmethod
    @rule
    def is_valid_name(name: str) -> bool:
        """Decide whether a normalized name satisfies the naming rule."""
        return {cls}Limits.MIN_NAME_LENGTH <= len(name) <= {cls}Limits.MAX_NAME_LENGTH

    @staticmethod
    @rule
    def can_transition(current: {cls}Status, target: {cls}Status) -> bool:
        """Decide whether a status change is allowed."""
        allowed = {{
            {cls}Status.DRAFT: ({cls}Status.ACTIVE, {cls}Status.ARCHIVED),
            {cls}Status.ACTIVE: ({cls}Status.ARCHIVED,),
            {cls}Status.ARCHIVED: (),
        }}
        return target in allowed[current]
'''


def utils_init(name: str) -> str:
    """Render utils/__init__.py: the package's curated re-exports.

    utils is a package, not a single file, because a growing module
    accumulates more than one kind of non business helper (text, dates,
    formatting...) — each concern gets its own file and its own class here,
    the same way services/ is one file per use case.
    """
    cls = _cls(name)
    return f'''
"""Non-business helpers for the {name} module, grouped by concern.

Formatting, normalization and data shaping live here, one class per concern.
Add utils/dates.py, utils/formatting.py the same way when the module needs
another kind of helper.

DO:
  - Put formatting, normalization, and data-shaping helpers here.
  - One file per concern (text.py, dates.py, formatting.py).
  - Group methods inside a class, decorated with @helper.
  - Re-export from __init__.py.

DO NOT:
  - Put business decisions here — those belong in rules.py.
  - Use bare top-level functions outside a class.
  - Create a flat utils.py — use the utils/ package instead.
  - Import from other domain modules.
"""

from app.modules.{name}.utils.text import {cls}TextUtils

__all__ = ["{cls}TextUtils"]
'''


def utils_text(name: str) -> str:
    """Render utils/text.py: text formatting and normalization."""
    cls = _cls(name)
    return f'''
"""Text formatting helpers owned by the {name} module.

DO:
  - Define text normalization, slugification, display formatting.
  - Group methods inside a class, decorated with @helper.

DO NOT:
  - Encode business decisions — those belong in rules.py.
  - Perform I/O or import framework code.
"""

import re

from app.core.base.markers import helper

_WHITESPACE = re.compile(r"\\s+")


class {cls}TextUtils:
    """Formatting and normalization for {name} display strings."""

    @staticmethod
    @helper
    def normalize_name(raw: str) -> str:
        """Collapse whitespace and trim a name for storage and comparison."""
        return _WHITESPACE.sub(" ", raw).strip()

    @staticmethod
    @helper
    def slugify(value: str) -> str:
        """Build a URL safe slug from a display name."""
        lowered = _WHITESPACE.sub("-", value.strip().lower())
        return re.sub(r"[^a-z0-9-]", "", lowered)
'''


def repository(name: str, with_cache: bool) -> str:
    """Render the repository, optionally cache aside."""
    cls = _cls(name)
    if with_cache:
        cache_import = "from app.integrations.cache.client import CacheClient"
        const_import = f"from app.modules.{name}.constants import {cls}CacheKeys, {cls}Status"
        init_sig = "session: AsyncSession, cache: CacheClient"
        init_body = "        self._session = session\n        self._cache = cache"
        get_body = f'''        return await self._cache.get_or_load(
            {cls}CacheKeys.ENTITY, entity_id, {cls}Read, lambda: self._load_by_id(entity_id)
        )'''
        loader = f'''
    @helper
    async def _load_by_id(self, entity_id: int) -> {cls}Read | None:
        """Fetch one row from the database. Supports get_by_id's cache-aside logic above."""
        row = await self._session.scalar(select({cls}).where({cls}.id == entity_id))
        return {cls}Read.model_validate(row) if row else None
'''
        marker_import = "from app.core.base.markers import database, helper"
    else:
        cache_import = ""
        const_import = f"from app.modules.{name}.constants import {cls}Status"
        init_sig = "session: AsyncSession"
        init_body = "        self._session = session"
        get_body = f'''        row = await self._session.scalar(select({cls}).where({cls}.id == entity_id))
        return {cls}Read.model_validate(row) if row else None'''
        loader = ""
        marker_import = "from app.core.base.markers import database"

    return f'''
"""Single access path to the {name} tables.

DO:
  - Define Abstract{cls}Repository (contract) and {cls}Repository (SQLAlchemy impl).
  - Every read/write to {name} tables goes through this file.
  - Use flush() inside methods, never commit() — the UoW owns the transaction.
  - Decorate methods with @database.

DO NOT:
  - Query or JOIN tables owned by another module.
  - Commit the transaction here — that's the UoW's job.
  - Put business logic here — only data access.
  - Return ORM model instances — convert to Pydantic schemas.
"""

from abc import abstractmethod

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

{cache_import}
{const_import}
{marker_import}
from app.core.base.repository import AbstractRepository
from app.modules.{name}.exceptions import {cls}NotFound
from app.modules.{name}.models import {cls}
from app.modules.{name}.schemas import {cls}Read


class Abstract{cls}Repository(AbstractRepository[{cls}Read]):
    """Contract a service depends on instead of the concrete SQLAlchemy class below.

    get_by_id and list_page come from AbstractRepository; this adds the
    writes and lookups specific to {name}.
    """

    @abstractmethod
    async def find_by_name(self, name: str) -> {cls}Read | None:
        """Look up by name without caching, since uniqueness needs fresh data."""
        raise NotImplementedError

    @abstractmethod
    async def create(self, name: str) -> {cls}Read:
        """Insert a new row inside the caller transaction."""
        raise NotImplementedError

    @abstractmethod
    async def set_status(self, entity_id: int, status: {cls}Status) -> {cls}Read:
        """Apply a status change inside the caller transaction."""
        raise NotImplementedError


class {cls}Repository(Abstract{cls}Repository):
    """SQLAlchemy implementation. Every read and write of the {name} tables goes through this class."""

    def __init__(self, {init_sig}) -> None:
{init_body}

    @database
    async def get_by_id(self, entity_id: int) -> {cls}Read | None:
        """Return one entity, or None when it does not exist."""
{get_body}

    @database
    async def find_by_name(self, name: str) -> {cls}Read | None:
        """Look up by name without caching, since uniqueness needs fresh data."""
        row = await self._session.scalar(select({cls}).where({cls}.name == name))
        return {cls}Read.model_validate(row) if row else None

    @database
    async def list_page(self, limit: int, offset: int) -> tuple[list[{cls}Read], int]:
        """Return one page of visible entities together with the total count."""
        condition = {cls}.status == {cls}Status.ACTIVE
        rows = await self._session.scalars(
            select({cls}).where(condition).order_by({cls}.id).limit(limit).offset(offset)
        )
        total = await self._session.scalar(select(func.count()).select_from({cls}).where(condition))
        return [{cls}Read.model_validate(row) for row in rows], total or 0

    @database
    async def create(self, name: str) -> {cls}Read:
        """Insert a new row inside the caller transaction."""
        row = {cls}(name=name)
        self._session.add(row)
        await self._session.flush()
        return {cls}Read.model_validate(row)

    @database
    async def set_status(self, entity_id: int, status: {cls}Status) -> {cls}Read:
        """Apply a status change inside the caller transaction."""
        row = await self._session.get({cls}, entity_id)
        if row is None:
            raise {cls}NotFound(entity_id=entity_id)
        row.status = status
        await self._session.flush()
        return {cls}Read.model_validate(row)
{loader}'''


def uow(name: str, with_cache: bool) -> str:
    """Render the transaction boundary of this module."""
    cls = _cls(name)
    if with_cache:
        cache_import = "from app.integrations.cache.client import CacheClient"
        init_sig = "session: AsyncSession, cache: CacheClient"
        init_body = (
            "        self._session = session\n"
            "        self._cache = cache\n"
            "        self._stale: list[tuple[str, int]] = []\n"
            f"        self.{name} = {cls}Repository(session, cache)"
        )
        mark = '''
    @helper
    def mark_stale(self, entity: str, entity_id: int) -> None:
        """Queue an entity for invalidation once the commit succeeds. Supports commit() below."""
        self._stale.append((entity, entity_id))
'''
        commit_body = (
            "        await self._session.commit()\n"
            "        for entity, entity_id in self._stale:\n"
            "            await self._cache.bump_version(entity, entity_id)\n"
            "        self._stale.clear()"
        )
        rollback_body = (
            "        await self._session.rollback()\n"
            "        self._stale.clear()\n"
            f'        logger.warning("{name} unit of work rolled back")'
        )
        marker_import = "from app.core.base.markers import database, helper"
    else:
        cache_import = ""
        init_sig = "session: AsyncSession"
        init_body = (
            "        self._session = session\n"
            f"        self.{name} = {cls}Repository(session)"
        )
        mark = ""
        commit_body = "        await self._session.commit()"
        rollback_body = (
            "        await self._session.rollback()\n"
            f'        logger.warning("{name} unit of work rolled back")'
        )
        marker_import = "from app.core.base.markers import database"

    return f'''
"""Transaction boundary for the {name} module.

DO:
  - Define Abstract{cls}UnitOfWork (contract) and {cls}UnitOfWork (concrete).
  - Own the session.commit() / session.rollback() lifecycle.
  - Invalidate cache entries AFTER commit, never before.
  - Expose repositories as attributes (self.{name}).

DO NOT:
  - Put business logic here — only transaction coordination.
  - Create the session — it's injected by dependencies.py.
  - Import from other domain modules.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

{cache_import}
{marker_import}
from app.core.base.uow import AbstractUnitOfWork
from app.modules.{name}.repository import Abstract{cls}Repository, {cls}Repository

logger = logging.getLogger(__name__)


class Abstract{cls}UnitOfWork(AbstractUnitOfWork):
    """Contract a service depends on instead of the concrete SQLAlchemy class below."""

    {name}: Abstract{cls}Repository


class {cls}UnitOfWork(Abstract{cls}UnitOfWork):
    """Owns the transaction and applies invalidation only after a successful commit."""

    def __init__(self, {init_sig}) -> None:
{init_body}
{mark}
    @database
    async def commit(self) -> None:
        """Commit the transaction, then flush every queued invalidation."""
{commit_body}

    @database
    async def rollback(self) -> None:
        """Roll back the transaction, leaving the cache untouched."""
{rollback_body}
'''


def events(name: str) -> str:
    """Render the events published by this module."""
    cls = _cls(name)
    return f'''
"""Events published by the {name} module.

DO:
  - Define DomainEvent subclasses this module publishes.
  - Use routing_key for message broker topic routing.
  - Reference event identity from this module's constants.py.

DO NOT:
  - Handle/subscribe to events here — consumers live in services/ or a worker.
  - Import from other domain modules.
"""

from app.core.events import DomainEvent
from app.modules.{name}.constants import {cls}Events, {cls}Status


class {cls}Created(DomainEvent):
    """Emitted after a new {name} has been committed."""

    entity_id: int
    name: str

    @property
    def routing_key(self) -> str:
        """Return the key used when publishing this event."""
        return f"{{{cls}Events.EXCHANGE}}.created"


class {cls}StatusChanged(DomainEvent):
    """Emitted after a {name} moved to a new status."""

    entity_id: int
    previous: {cls}Status
    current: {cls}Status

    @property
    def routing_key(self) -> str:
        """Return the key used when publishing this event."""
        return f"{{{cls}Events.EXCHANGE}}.status_changed"
'''


def service_read(name: str) -> str:
    """Render the read use case."""
    cls = _cls(name)
    return f'''
"""Read use case of the {name} module.

DO:
  - One file = one use case class with one execute() method.
  - Extend AbstractUseCase, decorate execute() with @use_case.
  - Depend on Abstract* contracts, never concrete classes.

DO NOT:
  - Put multiple use cases in one file — split into separate files.
  - Name the concrete repository/UoW — that's dependencies.py's job.
  - Hold HTTP/framework concerns — those live in the router.
"""

from app.core.base.markers import use_case
from app.core.pagination import Page, PaginationParams
from app.core.base.use_case import AbstractUseCase
from app.modules.{name}.exceptions import {cls}NotFound
from app.modules.{name}.repository import Abstract{cls}Repository
from app.modules.{name}.schemas import {cls}Read


class Get{cls}(AbstractUseCase):
    """Returns one entity, composing data from other modules when needed.

    Depends on Abstract{cls}Repository, not the concrete {cls}Repository —
    dependencies.py binds the concrete class at the composition root, and a
    unit test binds a Fake{cls}Repository instead. See references/layer-examples.md.
    """

    def __init__(self, repo: Abstract{cls}Repository) -> None:
        self._repo = repo

    @use_case
    async def execute(self, entity_id: int) -> {cls}Read:
        """Return one entity or raise when it is missing."""
        entity = await self._repo.get_by_id(entity_id)
        if entity is None:
            raise {cls}NotFound(entity_id=entity_id)
        return entity


class List{cls}s(AbstractUseCase):
    """Returns one page of entities."""

    def __init__(self, repo: Abstract{cls}Repository) -> None:
        self._repo = repo

    @use_case
    async def execute(self, params: PaginationParams) -> Page[{cls}Read]:
        """Return one page together with the total count."""
        items, total = await self._repo.list_page(params.limit, params.offset)
        return Page(items=items, total=total, limit=params.limit, offset=params.offset)
'''


def service_write(name: str, with_uow: bool) -> str:
    """Render the write use case."""
    cls = _cls(name)
    if with_uow:
        dep_import = f"from app.modules.{name}.uow import Abstract{cls}UnitOfWork"
        init_sig = f"uow: Abstract{cls}UnitOfWork, events: EventBus"
        init_body = "        self._uow = uow\n        self._events = events"
        lookup = f"        existing = await self._uow.{name}.find_by_name(name)"
        persist = f'''        async with self._uow:
            created = await self._uow.{name}.create(name)
            await self._uow.commit()
'''
    else:
        dep_import = f"from app.modules.{name}.repository import Abstract{cls}Repository"
        init_sig = f"repo: Abstract{cls}Repository, events: EventBus"
        init_body = "        self._repo = repo\n        self._events = events"
        lookup = "        existing = await self._repo.find_by_name(name)"
        persist = "        created = await self._repo.create(name)\n"

    return f'''
"""Write use case of the {name} module.

DO:
  - One file = one use case class with one execute() method.
  - Extend AbstractUseCase, decorate execute() with @use_case.
  - Depend on Abstract* contracts, never concrete classes.
  - Publish domain events after successful persistence.

DO NOT:
  - Put multiple use cases in one file — split into separate files.
  - Name the concrete repository/UoW — that's dependencies.py's job.
  - Hold HTTP/framework concerns — those live in the router.
"""

from app.core.events import EventBus
from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
{dep_import}
from app.modules.{name}.events import {cls}Created
from app.modules.{name}.exceptions import Invalid{cls}Name, {cls}NameTaken
from app.modules.{name}.rules import {cls}Rules
from app.modules.{name}.schemas import {cls}Read
from app.modules.{name}.utils import {cls}TextUtils


class Create{cls}(AbstractUseCase):
    """Validates, persists and announces the creation of one entity."""

    def __init__(self, {init_sig}) -> None:
{init_body}

    @use_case
    async def execute(self, raw_name: str) -> {cls}Read:
        """Create one entity and publish the resulting event."""
        name = {cls}TextUtils.normalize_name(raw_name)
        if not {cls}Rules.is_valid_name(name):
            raise Invalid{cls}Name(length=len(name))

{lookup}
        if existing is not None:
            raise {cls}NameTaken(name=name)

{persist}
        await self._events.publish({cls}Created(entity_id=created.id, name=created.name))
        return created
'''


def dependencies(name: str, minimal: bool, with_cache: bool) -> str:
    """Render the dependency wiring of this module."""
    cls = _cls(name)
    cache_import = "from app.integrations.cache.dependencies import get_cache" if with_cache else ""
    cache_type = "from app.integrations.cache.client import CacheClient" if with_cache else ""
    cache_param = "\n    cache: CacheClient = Depends(get_cache)," if with_cache else ""
    cache_arg = ", cache" if with_cache else ""

    if minimal:
        root = f'''
async def get_repo(
    session: AsyncSession = Depends(get_session),{cache_param}
) -> {cls}Repository:
    """Provide a request scoped repository. The one place the concrete class is named."""
    return {cls}Repository(session{cache_arg})
'''
        uow_import = ""
        write_dep = f'''
async def create_{name}_service(
    repo: Abstract{cls}Repository = Depends(get_repo),
    events: EventBus = Depends(get_event_bus),
) -> Create{cls}:
    """Provide the create use case."""
    return Create{cls}(repo, events)
'''
    else:
        root = f'''
async def get_uow(
    session: AsyncSession = Depends(get_session),{cache_param}
) -> {cls}UnitOfWork:
    """Provide a request scoped unit of work. The one place the concrete class is named."""
    return {cls}UnitOfWork(session{cache_arg})


async def get_repo(uow: Abstract{cls}UnitOfWork = Depends(get_uow)) -> Abstract{cls}Repository:
    """Expose the repository held by the unit of work."""
    return uow.{name}
'''
        uow_import = f"from app.modules.{name}.uow import Abstract{cls}UnitOfWork, {cls}UnitOfWork"
        write_dep = f'''
async def create_{name}_service(
    uow: Abstract{cls}UnitOfWork = Depends(get_uow),
    events: EventBus = Depends(get_event_bus),
) -> Create{cls}:
    """Provide the create use case."""
    return Create{cls}(uow, events)
'''

    return f'''
"""Dependency wiring for the {name} module — the composition root.

DO:
  - Wire concrete classes to their Abstract* contracts via Depends().
  - This is the ONLY place that names a concrete class ({cls}Repository, {cls}UnitOfWork).
  - Provide factory functions for services/use cases.

DO NOT:
  - Put business logic here — only wiring.
  - Import from other domain modules (except through their public.py if needed).
  - Define classes — only plain Depends() provider functions.
  - Let services or public.py name concrete classes — they use Abstract*.
"""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.events import EventBus, get_event_bus
{cache_type}
{cache_import}
from app.modules.{name}.repository import Abstract{cls}Repository, {cls}Repository
from app.modules.{name}.schemas import {cls}Read
from app.modules.{name}.services.create_{name} import Create{cls}
from app.modules.{name}.services.read_{name} import Get{cls}, List{cls}s
{uow_import}

{root}

async def get_{name}_service(repo: Abstract{cls}Repository = Depends(get_repo)) -> Get{cls}:
    """Provide the single entity read use case."""
    return Get{cls}(repo)


async def list_{name}_service(repo: Abstract{cls}Repository = Depends(get_repo)) -> List{cls}s:
    """Provide the listing use case."""
    return List{cls}s(repo)

{write_dep}

async def valid_{name}_id(
    entity_id: int, service: Get{cls} = Depends(get_{name}_service)
) -> {cls}Read:
    """Validate the path identifier once and reuse the loaded entity."""
    return await service.execute(entity_id)
'''


def router(name: str) -> str:
    """Render the HTTP surface of this module."""
    cls = _cls(name)
    return f'''
"""HTTP entry points of the {name} module.

DO:
  - Translate HTTP requests into use-case calls and return ApiResponse.
  - Keep route handlers thin — call a dependency/service, return the result.
  - Map domain exceptions to HTTP status codes via the central error handler.

DO NOT:
  - Put business logic here — that belongs in services/.
  - Build URLs, format values, or make decisions — move to utils/ or rules.py.
  - Define private helper functions in this file (e.g. _build_redirect_url).
  - Return bare schemas without the ApiResponse envelope.
  - Return ORM models — always use Pydantic schemas.
"""

from fastapi import APIRouter, Depends, status

from app.core.models import ApiResponse
from app.core.pagination import Page, PaginationParams, pagination_params
from app.modules.{name}.dependencies import create_{name}_service, list_{name}_service, valid_{name}_id
from app.modules.{name}.schemas import {cls}Create, {cls}Read
from app.modules.{name}.services.create_{name} import Create{cls}
from app.modules.{name}.services.read_{name} import List{cls}s

router = APIRouter(prefix="/{name}", tags=["{name}"])


@router.get("", response_model=ApiResponse[Page[{cls}Read]])
async def list_{name}(
    params: PaginationParams = Depends(pagination_params),
    service: List{cls}s = Depends(list_{name}_service),
) -> ApiResponse[Page[{cls}Read]]:
    """Return one page of active entities."""
    page = await service.execute(params)
    return ApiResponse(success=True, data=page)


@router.get("/{{entity_id}}", response_model=ApiResponse[{cls}Read])
async def get_{name}(entity: {cls}Read = Depends(valid_{name}_id)) -> ApiResponse[{cls}Read]:
    """Return one entity by identifier."""
    return ApiResponse(success=True, data=entity)


@router.post("", response_model=ApiResponse[{cls}Read], status_code=status.HTTP_201_CREATED)
async def create_{name}(
    payload: {cls}Create,
    service: Create{cls} = Depends(create_{name}_service),
) -> ApiResponse[{cls}Read]:
    """Create a new entity."""
    created = await service.execute(payload.name)
    return ApiResponse(success=True, data=created)
'''


def public(name: str) -> str:
    """Render the cross module contract."""
    cls = _cls(name)
    return f'''
"""Contract exposed to other modules — the ONLY import surface.

DO:
  - Expose a read-only facade class ({cls}Api) with @facade-decorated methods.
  - Depend on Abstract* contracts, never concrete classes.
  - Re-export schemas/types that other modules need.
  - Other modules MUST import from this file and nothing else from {name}.

DO NOT:
  - Expose write operations — those stay internal to the module.
  - Let other modules reach into repository.py, models.py, services/, etc.
  - Import from other domain modules — public.py is a leaf for outbound deps.
"""

from fastapi import Depends

from app.core.base.markers import facade
from app.modules.{name}.dependencies import get_repo
from app.modules.{name}.repository import Abstract{cls}Repository
from app.modules.{name}.schemas import {cls}Read


class {cls}Api:
    """Read only facade over the {name} module."""

    def __init__(self, repo: Abstract{cls}Repository) -> None:
        self._repo = repo

    @facade
    async def get(self, entity_id: int) -> {cls}Read | None:
        """Return one entity, or None when it does not exist."""
        return await self._repo.get_by_id(entity_id)


async def get_{name}_api(repo: Abstract{cls}Repository = Depends(get_repo)) -> {cls}Api:
    """Provide the facade to other modules."""
    return {cls}Api(repo)
'''
