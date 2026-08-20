# Layer-by-layer example, with abstract classes

Every code block below is real output of `scripts/scaffold.py --modules catalog --integrations cache`,
copied after `ruff check --fix` and `ruff format` ran on it — not hand-typed prose. It has been
verified end to end: `ruff check`, `mypy`, `lint-imports`, importing `app.main`, and running the
actual `pytest` suite shown at the bottom all pass. If you regenerate the same command you get this
file, byte for byte modulo formatting.

## Why abstract classes here

Two ideas from Percival & Gregory's *Architecture Patterns with Python* (cosmicpython.com) — the
Repository pattern and the Unit of Work pattern — plus the same idea applied to the use-case layer.
The point is Dependency Inversion: a service depends on an `Abstract*` contract, never on the
concrete SQLAlchemy class. Two consequences fall out of that:

1. **A unit test can hand a service an in-memory Fake instead of a database.** No container, no
   fixture beyond the fake itself — see the `test_services.py` example at the bottom.
2. **A missing method is a `TypeError` at instantiation, not a code-review miss.** Confirmed by
   actually doing it:
   ```python
   >>> class BrokenRepo(AbstractCatalogRepository):
   ...     async def get_by_id(self, entity_id): return None
   ...     # missing list_page / find_by_name / create / set_status
   >>> BrokenRepo()
   TypeError: Can't instantiate abstract class BrokenRepo without an implementation
   for abstract methods 'create', 'find_by_name', 'list_page', 'set_status'
   ```
   No linter rule catches an incomplete `Abstract*` implementation — Python itself does, every time,
   for free.

This does **not** replace `dependency_overrides` — the two work at different levels. A unit test
using a Fake exercises a use case's *decisions* (validation, ordering, what gets published) at
memory speed. The integration test in `test_router.py` still exercises the real Postgres path
through the full HTTP stack, because that's the only place a wrong SQL query or a bad migration
shows up. Keep both.

## Two more conventions baked into every layer below

- **No bare constant or bare helper function at module level.** A limit, a cache key prefix, a
  formatting helper — every one of them lives as an attribute or a `@staticmethod` on a class, never
  as a loose `MAX_X = 5` or `def normalize(...)` floating above the file. The constant still lives in
  its own file (`constants.py`) and gets imported where it's used — that part doesn't change — but
  *within* that file nothing sits outside a class. `utils.py` becomes a `utils/` package for the same
  reason: once a module needs more than one kind of helper (text, dates, formatting), each concern
  gets its own file and its own class, the same way `services/` is already one file per use case.
  This does **not** apply to FastAPI wiring functions (`router.py`, `dependencies.py`,
  `lifespan.py`) — those are framework entry points `Depends()` must be able to call directly, not
  the scattered "hàm vặt" this rule targets.
- **A decorator marks each method's role — main operation or auxiliary support, never the whole
  class.** A repository has methods that are its actual API (`get_by_id`, `create`) and methods that
  only exist to support one of those (`_load_by_id`, called by `get_by_id`'s cache-aside logic). One
  `@database` on the whole class would say nothing that the file name didn't already say; `@database`
  on the main operations and `@helper` on the auxiliary one says which is which. `app/markers.py`'s
  `database`/`helper`/`rule`/`use_case`/`facade` are decorator *classes* (`__get__`/`__call__`), not
  functions returning closures — verified to bind `self` correctly for sync and async methods and to
  stack correctly under `@staticmethod`. They change nothing at runtime otherwise — no `lint-imports`
  contract reads them (yet) — they're for the human skimming the file or a diff.

## `app/repository.py`, `app/uow.py`, `app/use_case.py` — the root contracts

Root mechanism only, per rule #4: no business concept, just the shape every module's repository,
unit of work and use case must satisfy.

```python
# app/repository.py
"""Abstract repository contract every module's concrete repository implements."""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

EntityT = TypeVar("EntityT")


class AbstractRepository(ABC, Generic[EntityT]):
    """The read contract every module's repository must satisfy.

    Each module extends this with its own write and lookup methods.
    """

    @abstractmethod
    async def get_by_id(self, entity_id: int) -> EntityT | None:
        """Return one entity, or None when it does not exist."""
        raise NotImplementedError

    @abstractmethod
    async def list_page(self, limit: int, offset: int) -> tuple[list[EntityT], int]:
        """Return one page of entities together with the total count."""
        raise NotImplementedError
```

```python
# app/uow.py
"""Abstract unit-of-work contract every module's concrete UoW implements."""

from abc import ABC, abstractmethod


class AbstractUnitOfWork(ABC):
    """Async context manager owning one transaction boundary.

    __aexit__ rolls back automatically on any exception, so a concrete
    subclass only ever has to implement commit() and rollback().
    """

    async def __aenter__(self) -> "AbstractUnitOfWork":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if exc_type is not None:
            await self.rollback()

    @abstractmethod
    async def commit(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def rollback(self) -> None:
        raise NotImplementedError
```

```python
# app/use_case.py
"""Abstract use-case contract every module's service class implements.

Makes rule #9 (one use case, one class, one execute()) structural. Input and
output are left to each concrete class to type: a Get, a List and a Create
use case take genuinely different arguments, so forcing one shared signature
here would fight the domain instead of describing it.
"""

from abc import ABC, abstractmethod
from typing import Any


class AbstractUseCase(ABC):
    """One orchestration step: validate, call the repository or uow, publish."""

    @abstractmethod
    async def execute(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError
```

`app/markers.py` (the decorators) is generated alongside these — see the "Markers" section below.

## `constants.py` — grouped into classes, no bare values

```python
# app/catalog/constants.py
"""Constants and enums owned by the catalog module."""

from enum import StrEnum


class CatalogLimits:
    """Numeric limits owned by the catalog module."""

    MAX_NAME_LENGTH = 255
    MIN_NAME_LENGTH = 2
    DEFAULT_PAGE_SIZE = 50


class CatalogCacheKeys:
    """Cache identity owned by the catalog module."""

    ENTITY = "catalog"
    TTL_SECONDS = 300


class CatalogEvents:
    """Messaging identity owned by the catalog module."""

    EXCHANGE = "catalog"


class CatalogStatus(StrEnum):
    """Lifecycle state of a catalog."""

    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"

    @property
    def is_visible(self) -> bool:
        return self is CatalogStatus.ACTIVE


class ErrorCode(StrEnum):
    """Stable error codes returned to clients by this module."""

    NOT_FOUND = "catalog_not_found"
    NAME_TAKEN = "catalog_name_taken"
    INVALID_NAME = "catalog_invalid_name"
    NOT_ACTIVE = "catalog_not_active"
```

Every value groups by concern (`Limits`, `CacheKeys`, `Events`), the same way `router/` groups by
endpoint once it outgrows one file — see `references/architecture.md#keeping-files-and-functions-small`.
Elsewhere in the codebase these are always imported and referenced through the class, never as a bare
name: `CatalogLimits.MAX_NAME_LENGTH`, not `MAX_NAME_LENGTH`.

## `rules.py` — pure decisions, grouped into one class

```python
# app/catalog/rules.py
"""Business rules for the catalog module."""

from app.catalog.constants import CatalogLimits, CatalogStatus
from app.markers import rule


class CatalogRules:
    """Every business decision about a catalog, grouped so call sites read as
    `CatalogRules.is_valid_name(...)` instead of a bare import."""

    @staticmethod
    @rule
    def is_valid_name(name: str) -> bool:
        return CatalogLimits.MIN_NAME_LENGTH <= len(name) <= CatalogLimits.MAX_NAME_LENGTH

    @staticmethod
    @rule
    def can_transition(current: CatalogStatus, target: CatalogStatus) -> bool:
        allowed = {
            CatalogStatus.DRAFT: (CatalogStatus.ACTIVE, CatalogStatus.ARCHIVED),
            CatalogStatus.ACTIVE: (CatalogStatus.ARCHIVED,),
            CatalogStatus.ARCHIVED: (),
        }
        return target in allowed[current]
```
`@staticmethod` sits outermost (applied last) — `@rule` wraps the plain function first, `@staticmethod`
wraps the result, and Python 3.10+'s `staticmethod` forwards calls straight through, so the ordering
is what makes `CatalogRules.is_valid_name("x")` work at all. Verified for exactly this stacking, sync
and async both, before it went into the template — see "Markers" below.

Still no I/O, still no framework import — that hasn't changed. What changed is the shape: a
namespace class instead of two loose functions, so a caller reads `CatalogRules.is_valid_name` and
immediately knows which module's rule it's invoking, the same benefit the cross-module import
convention (`from app.identity import constants as identity_constants`) already gives constants.

## `utils/` — a package, one class per concern

```python
# app/catalog/utils/__init__.py
"""Non business helpers for the catalog module, grouped by concern.

Add utils/dates.py, utils/formatting.py the same way when the module needs
another kind of helper.
"""

from app.catalog.utils.text import CatalogTextUtils

__all__ = ["CatalogTextUtils"]
```

```python
# app/catalog/utils/text.py
"""Text formatting helpers owned by the catalog module."""

import re

from app.markers import helper

_WHITESPACE = re.compile(r"\s+")


class CatalogTextUtils:
    """Formatting and normalization for catalog display strings."""

    @staticmethod
    @helper
    def normalize_name(raw: str) -> str:
        return _WHITESPACE.sub(" ", raw).strip()

    @staticmethod
    @helper
    def slugify(value: str) -> str:
        lowered = _WHITESPACE.sub("-", value.strip().lower())
        return re.sub(r"[^a-z0-9-]", "", lowered)
```

A module with only formatting helpers only needs `text.py`. The moment it also needs date helpers or
money formatting, that's `utils/dates.py` with a `CatalogDateUtils` class and `utils/money.py` with a
`CatalogMoneyUtils` class — siblings, not a growing `text.py`. `_WHITESPACE` stays a private
module-level compiled pattern (leading underscore) — that's implementation caching, not a business
constant, so it's exempt from the class-grouping rule the same way a local variable would be.

## `schemas.py` — validation and serialization live on the schema

Pydantic's own `field_validator`/`field_serializer` are the mechanism; the rule they enforce still
comes from `rules.py`/`utils/`, never reimplemented inline. One implementation of "what makes a name
valid", called from two boundaries — the schema at parse time, and the use case again below, since the
use case has to stay independently callable from a worker, a CLI script or a unit test that never goes
through a schema at all.

```python
# app/catalog/schemas.py
"""Schemas for the catalog module."""

from datetime import datetime

from pydantic import field_validator

from app.catalog.constants import CatalogStatus
from app.catalog.rules import CatalogRules
from app.catalog.utils import CatalogTextUtils
from app.models import CustomModel, FrozenModel


class CatalogRead(FrozenModel):
    """Representation safe to round trip through the cache."""

    id: int
    name: str
    status: CatalogStatus
    created_at: datetime


class CatalogCreate(CustomModel):
    """Payload accepted by the create endpoint."""

    name: str

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        """Normalize then apply the same rule the use case enforces again."""
        normalized = CatalogTextUtils.normalize_name(value)
        if not CatalogRules.is_valid_name(normalized):
            raise ValueError("name length out of range")
        return normalized


class CatalogUpdate(CustomModel):
    """Payload accepted by the update endpoint."""

    name: str | None = None
    status: CatalogStatus | None = None

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str | None) -> str | None:
        """Normalize then apply the same rule the use case enforces again, skipping when absent."""
        if value is None:
            return None
        normalized = CatalogTextUtils.normalize_name(value)
        if not CatalogRules.is_valid_name(normalized):
            raise ValueError("name length out of range")
        return normalized
```

`CustomModel`/`FrozenModel` in `app/models.py` already do this for every schema project-wide: the
`@field_serializer("*", when_used="json")` there is what makes every datetime cross the wire in one
consistent format, without each schema repeating the logic.

### The other half: a schema failure still returns the envelope

A `field_validator` raising `ValueError` becomes a Pydantic `ValidationError`, which FastAPI turns into
a `RequestValidationError` — a different exception class than the `AppError` hierarchy `main.py`
already handles. Left unhandled, FastAPI's own default handler returns `{"detail": [...]}`, breaking
the one envelope every other endpoint returns. `app/main.py` registers a second handler:

```python
@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    envelope = ApiResponse[None](
        success=False,
        error=ErrorPayload(
            code="validation_failed",
            message="Validation failed",
            context={"errors": jsonable_encoder(exc.errors())},
        ),
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content=envelope.model_dump(mode="json", by_alias=True),
    )
```

`jsonable_encoder` — the same helper FastAPI's own default handler uses internally — sanitizes
`exc.errors()` before it goes into `ErrorPayload.context`; passing the raw list through `model_dump`
directly risks a non-JSON-native value (Pydantic's error `ctx` can hold arbitrary objects) breaking
serialization. Verified with a real request: `POST /api/v1/catalog {"name": "a"}` (below the 2 character
minimum) comes back `422` with `body["error"]["code"] == "validation_failed"`, not FastAPI's default shape
— see `tests/catalog/test_router.py::test_create_catalog_rejects_invalid_name_through_the_envelope`.

### The other other half: who commits

Pushing validation onto the schema doesn't change who commits the transaction, but it's worth stating
next to it since both are about trusting the wire boundary to do its job once, correctly, instead of
re-deriving trust deeper in the stack. `app/database.py`'s `get_session` commits once the request
completes without raising, and rolls back if it does:

```python
async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    factory = request.app.state.session_factory
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

This is load-bearing for any `--minimal` module: its `repository.create()` only ever calls `flush()`,
correctly, per the "repository never commits" rule — so without this, nothing commits at all. Found by
actually running the generated `--minimal` project's router tests against a real Postgres container: the
create endpoint returned `201`, the row existed inside that request's transaction, and the very next
request's `GET` came back `404` because nothing had persisted past the connection being returned to the
pool. A module *with* `uow.py` already calls `uow.commit()` explicitly before the handler returns; this
second commit on an already-clean session is a harmless no-op, not a double write.

## `repository.py` — the abstract contract plus the SQLAlchemy implementation

```python
# app/catalog/repository.py
"""Single access path to the catalog tables."""

from abc import abstractmethod

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.constants import CatalogCacheKeys, CatalogStatus
from app.catalog.exceptions import CatalogNotFound
from app.catalog.models import Catalog
from app.catalog.schemas import CatalogRead
from app.integrations.cache.client import CacheClient
from app.markers import database, helper
from app.repository import AbstractRepository


class AbstractCatalogRepository(AbstractRepository[CatalogRead]):
    """Contract a service depends on instead of the concrete SQLAlchemy class below.

    get_by_id and list_page come from AbstractRepository; this adds the
    writes and lookups specific to catalog.
    """

    @abstractmethod
    async def find_by_name(self, name: str) -> CatalogRead | None:
        raise NotImplementedError

    @abstractmethod
    async def create(self, name: str) -> CatalogRead:
        raise NotImplementedError

    @abstractmethod
    async def set_status(self, entity_id: int, status: CatalogStatus) -> CatalogRead:
        raise NotImplementedError


class CatalogRepository(AbstractCatalogRepository):
    """SQLAlchemy implementation. Every read and write of the catalog tables goes through this class."""

    def __init__(self, session: AsyncSession, cache: CacheClient) -> None:
        self._session = session
        self._cache = cache

    @database
    async def get_by_id(self, entity_id: int) -> CatalogRead | None:
        return await self._cache.get_or_load(
            CatalogCacheKeys.ENTITY, entity_id, CatalogRead, lambda: self._load_by_id(entity_id)
        )

    @database
    async def find_by_name(self, name: str) -> CatalogRead | None:
        row = await self._session.scalar(select(Catalog).where(Catalog.name == name))
        return CatalogRead.model_validate(row) if row else None

    @database
    async def list_page(self, limit: int, offset: int) -> tuple[list[CatalogRead], int]:
        condition = Catalog.status == CatalogStatus.ACTIVE
        rows = await self._session.scalars(
            select(Catalog).where(condition).order_by(Catalog.id).limit(limit).offset(offset)
        )
        total = await self._session.scalar(select(func.count()).select_from(Catalog).where(condition))
        return [CatalogRead.model_validate(row) for row in rows], total or 0

    @database
    async def create(self, name: str) -> CatalogRead:
        row = Catalog(name=name)
        self._session.add(row)
        await self._session.flush()
        return CatalogRead.model_validate(row)

    @database
    async def set_status(self, entity_id: int, status: CatalogStatus) -> CatalogRead:
        row = await self._session.get(Catalog, entity_id)
        if row is None:
            raise CatalogNotFound(entity_id=entity_id)
        row.status = status
        await self._session.flush()
        return CatalogRead.model_validate(row)

    @helper
    async def _load_by_id(self, entity_id: int) -> CatalogRead | None:
        """Supports get_by_id's cache-aside logic above — not itself one of the repository's operations."""
        row = await self._session.scalar(select(Catalog).where(Catalog.id == entity_id))
        return CatalogRead.model_validate(row) if row else None
```
`get_by_id`/`find_by_name`/`list_page`/`create`/`set_status` are `@database` — the repository's actual
API, what a service calls. `_load_by_id` is `@helper` — it touches the database too, but it exists only
to support `get_by_id`'s cache-aside branch, and isn't itself something a caller reaches for. The
marker tracks *role in the class*, not *whether the method does I/O*.

Note the `set_status` None-check: `session.get()` can return `None`, and `mypy` catches assigning
through it if you don't guard — this was caught by actually running `mypy` against the generated
project, not written from memory.

## `uow.py` — the abstract contract plus the transaction boundary

```python
# app/catalog/uow.py
"""Transaction boundary for the catalog module."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.repository import AbstractCatalogRepository, CatalogRepository
from app.integrations.cache.client import CacheClient
from app.markers import database, helper
from app.uow import AbstractUnitOfWork

logger = logging.getLogger(__name__)


class AbstractCatalogUnitOfWork(AbstractUnitOfWork):
    """Contract a service depends on instead of the concrete SQLAlchemy class below."""

    catalog: AbstractCatalogRepository


class CatalogUnitOfWork(AbstractCatalogUnitOfWork):
    """Owns the transaction and applies invalidation only after a successful commit."""

    def __init__(self, session: AsyncSession, cache: CacheClient) -> None:
        self._session = session
        self._cache = cache
        self._stale: list[tuple[str, int]] = []
        self.catalog = CatalogRepository(session, cache)

    @helper
    def mark_stale(self, entity: str, entity_id: int) -> None:
        """Supports commit() below — bookkeeping, not itself a transaction operation."""
        self._stale.append((entity, entity_id))

    @database
    async def commit(self) -> None:
        await self._session.commit()
        for entity, entity_id in self._stale:
            await self._cache.bump_version(entity, entity_id)
        self._stale.clear()

    @database
    async def rollback(self) -> None:
        await self._session.rollback()
        self._stale.clear()
        logger.warning("catalog unit of work rolled back")
```

`AbstractCatalogUnitOfWork` declares `catalog: AbstractCatalogRepository` as a bare class-level
annotation — no value, just a type. `AbstractUnitOfWork.__aexit__` (inherited, not repeated) already
calls `self.rollback()` on any exception, so the concrete class only has to write `commit()` and
`rollback()`, never `__aenter__`/`__aexit__` again. `commit`/`rollback` are `@database` (the unit of
work's actual operations); `mark_stale` is `@helper` (queues bookkeeping `commit()` reads, not a
transaction operation itself).

## `services/*.py` — use cases depending on the abstraction

```python
# app/catalog/services/create_catalog.py
"""Write use case of the catalog module."""

from app.catalog.events import CatalogCreated
from app.catalog.exceptions import CatalogNameTaken, InvalidCatalogName
from app.catalog.rules import CatalogRules
from app.catalog.schemas import CatalogRead
from app.catalog.uow import AbstractCatalogUnitOfWork
from app.catalog.utils import CatalogTextUtils
from app.events import EventBus
from app.markers import use_case
from app.use_case import AbstractUseCase


class CreateCatalog(AbstractUseCase):
    """Validates, persists and announces the creation of one entity."""

    def __init__(self, uow: AbstractCatalogUnitOfWork, events: EventBus) -> None:
        self._uow = uow
        self._events = events

    @use_case
    async def execute(self, raw_name: str) -> CatalogRead:
        name = CatalogTextUtils.normalize_name(raw_name)
        if not CatalogRules.is_valid_name(name):
            raise InvalidCatalogName(length=len(name))

        existing = await self._uow.catalog.find_by_name(name)
        if existing is not None:
            raise CatalogNameTaken(name=name)

        async with self._uow:
            created = await self._uow.catalog.create(name)
            await self._uow.commit()

        await self._events.publish(CatalogCreated(entity_id=created.id, name=created.name))
        return created
```

`__init__` takes `AbstractCatalogUnitOfWork`, never the concrete `CatalogUnitOfWork` — this class
cannot construct or even name the SQLAlchemy implementation. That's the entire point: read this file
top to bottom and there is no way to tell whether it will run against Postgres or an in-memory Fake.
`@use_case` sits on `execute` itself, not the class — rule #9 is "one use case, one class, one
`execute()`"; marking the method that *is* the use case is more precise than marking a class that, in
this file, only ever has that one operation anyway.

## `dependencies.py` — the composition root

The **one** place a concrete class is named and constructed. Everything downstream — the use cases
above, the facade below — receives the abstraction.

```python
# app/catalog/dependencies.py
"""Dependency wiring for the catalog module.

The composition root: the only place that names a concrete class
(CatalogRepository / CatalogUnitOfWork) instead of its Abstract* contract.
"""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.repository import AbstractCatalogRepository
from app.catalog.schemas import CatalogRead
from app.catalog.services.create_catalog import CreateCatalog
from app.catalog.services.read_catalog import GetCatalog, ListCatalogs
from app.catalog.uow import AbstractCatalogUnitOfWork, CatalogUnitOfWork
from app.database import get_session
from app.events import EventBus, get_event_bus
from app.integrations.cache.client import CacheClient
from app.integrations.cache.dependencies import get_cache


async def get_uow(
    session: AsyncSession = Depends(get_session),
    cache: CacheClient = Depends(get_cache),
) -> CatalogUnitOfWork:
    """Provide a request scoped unit of work. The one place the concrete class is named."""
    return CatalogUnitOfWork(session, cache)


async def get_repo(uow: AbstractCatalogUnitOfWork = Depends(get_uow)) -> AbstractCatalogRepository:
    """Expose the repository held by the unit of work."""
    return uow.catalog


async def get_catalog_service(repo: AbstractCatalogRepository = Depends(get_repo)) -> GetCatalog:
    return GetCatalog(repo)


async def list_catalog_service(repo: AbstractCatalogRepository = Depends(get_repo)) -> ListCatalogs:
    return ListCatalogs(repo)


async def create_catalog_service(
    uow: AbstractCatalogUnitOfWork = Depends(get_uow),
    events: EventBus = Depends(get_event_bus),
) -> CreateCatalog:
    return CreateCatalog(uow, events)
```

`get_uow` returns the concrete `CatalogUnitOfWork` — accurate, since it's the function that literally
builds one. `get_repo` returns `AbstractCatalogRepository` — also accurate, since `uow.catalog` is
typed through the abstract annotation declared on `AbstractCatalogUnitOfWork`. Getting this backwards
(declaring `get_repo`'s return type as the concrete class while it's really handing back whatever type
the abstract attribute says) is exactly the kind of mismatch `mypy` catches — confirmed by initially
getting it wrong here, running `mypy`, and fixing it before writing this document.

## `public.py` — the facade, also typed against the abstraction

```python
# app/catalog/public.py
"""Contract exposed to other modules."""

from fastapi import Depends

from app.catalog.dependencies import get_repo
from app.catalog.repository import AbstractCatalogRepository
from app.catalog.schemas import CatalogRead
from app.markers import facade


class CatalogApi:
    """Read only facade over the catalog module."""

    def __init__(self, repo: AbstractCatalogRepository) -> None:
        self._repo = repo

    @facade
    async def get(self, entity_id: int) -> CatalogRead | None:
        return await self._repo.get_by_id(entity_id)


async def get_catalog_api(repo: AbstractCatalogRepository = Depends(get_repo)) -> CatalogApi:
    return CatalogApi(repo)
```

## Markers: `@database`, `@helper`, `@rule`, `@use_case`, `@facade`, `@integration`

Decorate the **method** with a role, never the class — a repository has main operations (`get_by_id`,
`create`) and auxiliary ones that only support them (`_load_by_id`, called by `get_by_id`'s cache-aside
branch); one blanket `@database` on the class says nothing the file name didn't already say, while
`@database` on the main operations and `@helper` on the auxiliary one says which is which.

```python
# app/markers.py
"""Layer markers: decorator classes that tag a method with its architectural role."""

import functools
from collections.abc import Callable
from typing import Any


class _MethodMarker:
    """Base for every marker below. Never used directly."""

    layer: str

    def __init__(self, func: Callable[..., Any]) -> None:
        functools.update_wrapper(self, func)
        self._func = func
        setattr(func, "__layer__", self.layer)  # noqa: B010 -- dynamic attribute, not a fixed attr of Callable

    def __get__(self, obj: Any, objtype: type | None = None) -> Any:
        """Delegate binding to the wrapped function — sync and async both bind correctly this way."""
        if obj is None:
            return self._func
        return self._func.__get__(obj, objtype)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Forward straight through for a bare function (no class involved)."""
        return self._func(*args, **kwargs)


class database(_MethodMarker):  # noqa: N801 -- lowercase by design, read as an annotation like @staticmethod
    """A method that reads or writes a module's own tables directly."""

    layer = "database"


class helper(_MethodMarker):  # noqa: N801 -- lowercase by design, read as an annotation like @staticmethod
    """A method with no business decision: formatting, normalization, or support for another method."""

    layer = "helper"


class rule(_MethodMarker):  # noqa: N801 -- lowercase by design, read as an annotation like @staticmethod
    """A method holding a pure business decision — no I/O."""

    layer = "rule"


class use_case(_MethodMarker):  # noqa: N801 -- lowercase by design, read as an annotation like @staticmethod
    """The execute() of a use case — one class, one operation."""

    layer = "use_case"


class facade(_MethodMarker):  # noqa: N801 -- lowercase by design, read as an annotation like @staticmethod
    """A method exposed to other modules through public.py."""

    layer = "facade"


class integration(_MethodMarker):  # noqa: N801 -- lowercase by design, read as an annotation like @staticmethod
    """A method that calls an external system directly (Redis, RabbitMQ, object storage)."""

    layer = "integration"
```

Implemented as classes, not functions returning closures, so lowercase names read as annotations the
same way `@property`/`@staticmethod` already do — deliberately not CapWords, with `# noqa: N801` saying
so. `__get__` delegates binding to the *wrapped function's own* descriptor protocol (`self._func.__get__`)
rather than reimplementing it, which is what makes this transparent for both sync and async methods —
verified directly, including stacked under `@staticmethod` (`@staticmethod` outermost, the marker
innermost — `@staticmethod` forwards to whatever it wraps either way) and stacked with a *behavioral*
decorator like `@retry` below (marker outermost that time, so the visible callable still carries the
role tag). Purely informational otherwise — no `lint-imports` contract or `ruff` rule reads `__layer__`
today. A method carrying more than one *role* marker is a sign it's doing more than one job — split it.

`Abstract*` classes are never decorated — the name prefix already announces the contract, and
`dependencies.py`/`router.py`/`lifespan.py` stay undecorated too, since a FastAPI dependency provider
has to remain a plain function `Depends()` calls directly.

### Two behavioral decorators, not just tags

`@database`/`@helper`/`@rule`/`@use_case`/`@facade`/`@integration` change nothing at runtime. Two more
decorators in this codebase *do* change behavior — real cross-cutting concerns, not role tags, so they
live in their own files rather than `app/markers.py`:

- **`app/retry.py`'s `retry(attempts=..., exceptions=...)`** — exponential backoff around a transient
  failure in an external call. Stack it *under* a role marker (`@integration` outermost, `@retry(...)`
  innermost) so the visible, callable attribute still carries the role tag:
  ```python
  # integrations/storage/client.py
  @integration
  @retry(attempts=3, exceptions=(UploadFailed,))
  async def upload(self, key: str, body: bytes, content_type: str) -> str:
      ...
  ```
  Verified end to end against a real MinIO container: `upload()`/`presigned_url()` round-trip an object
  correctly with both decorators applied, and a scripted transient failure (fails twice, then succeeds)
  confirms the retry loop actually retries instead of just looking like it would. Not a substitute for
  the queue's own retry-via-DLX (`references/messaging.md`) — that handles a message still failing
  after every attempt here is exhausted.

- **`integrations/queue/idempotency.py`'s `idempotent(store)`** — skips a queue consumer handler if the
  message's `event_id` was already processed, since AMQP only guarantees at-least-once delivery. Wired
  into `app/worker.py` automatically when `queue` and `cache` are both selected (`RedisIdempotencyStore`,
  a TTL'd key per `event_id`); the `IdempotencyStore` `Protocol` and the decorator itself don't require
  `cache` — bring your own store when it isn't selected. Verified against a real Redis container: three
  deliveries of the same `event_id` run the wrapped handler exactly once, a distinct `event_id` runs it
  again, and the TTL is actually set on the key, not just claimed. See
  `references/messaging.md#idempotent-consumers` for the full pattern and `app/worker.py`'s own wiring:
  ```python
  # app/worker.py, when cache is also selected
  redis = RedisConnectionFactory.create()
  handler = idempotent(RedisIdempotencyStore(redis))(handle_message)
  ```

## Tests: Fake doubles for a database-free unit test

```python
# tests/catalog/test_services.py
"""Unit tests for app.catalog.services.create_catalog — a Fake stands in for the
database, so every branch runs without a container or any fixture beyond the
fakes below. tests/catalog/test_router.py exercises the same use case again
through the real Postgres path; this file is faster, not a replacement.
"""

from datetime import UTC, datetime

import pytest

from app.catalog.constants import CatalogStatus
from app.catalog.exceptions import CatalogNameTaken
from app.catalog.repository import AbstractCatalogRepository
from app.catalog.schemas import CatalogRead
from app.catalog.services.create_catalog import CreateCatalog
from app.catalog.uow import AbstractCatalogUnitOfWork
from app.events import DomainEvent, EventBus


class InMemoryEventBus(EventBus):
    """Records published events instead of dispatching them to handlers."""

    def __init__(self) -> None:
        super().__init__()
        self.published: list[DomainEvent] = []

    async def publish(self, event: DomainEvent) -> None:
        self.published.append(event)


class FakeCatalogRepository(AbstractCatalogRepository):
    """In-memory stand-in for CatalogRepository — a dict instead of a table.

    Implements every abstract method AbstractCatalogRepository declares. Miss
    one and Python refuses to instantiate this class with a TypeError.
    """

    def __init__(self) -> None:
        self._rows: dict[int, CatalogRead] = {}
        self._next_id = 1

    async def get_by_id(self, entity_id: int) -> CatalogRead | None:
        return self._rows.get(entity_id)

    async def list_page(self, limit: int, offset: int) -> tuple[list[CatalogRead], int]:
        items = list(self._rows.values())[offset : offset + limit]
        return items, len(self._rows)

    async def find_by_name(self, name: str) -> CatalogRead | None:
        return next((row for row in self._rows.values() if row.name == name), None)

    async def create(self, name: str) -> CatalogRead:
        row = CatalogRead(
            id=self._next_id, name=name, status=CatalogStatus.DRAFT, created_at=datetime.now(UTC)
        )
        self._rows[row.id] = row
        self._next_id += 1
        return row

    async def set_status(self, entity_id: int, status: CatalogStatus) -> CatalogRead:
        updated = self._rows[entity_id].model_copy(update={"status": status})
        self._rows[entity_id] = updated
        return updated


class FakeCatalogUnitOfWork(AbstractCatalogUnitOfWork):
    """In-memory unit of work: no session, no network, no fixtures."""

    def __init__(self) -> None:
        self.catalog = FakeCatalogRepository()
        self.committed = False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.committed = False


@pytest.fixture
def uow() -> FakeCatalogUnitOfWork:
    return FakeCatalogUnitOfWork()


@pytest.fixture
def service(uow: FakeCatalogUnitOfWork, events: InMemoryEventBus) -> CreateCatalog:
    return CreateCatalog(uow, events)


@pytest.fixture
def events() -> InMemoryEventBus:
    return InMemoryEventBus()


async def test_create_catalog_persists_and_publishes(
    service: CreateCatalog, uow: FakeCatalogUnitOfWork, events: InMemoryEventBus
) -> None:
    created = await service.execute("Example")

    assert created.name == "Example"
    assert len(events.published) == 1
    assert uow.committed is True


async def test_create_catalog_rejects_duplicate_name(service: CreateCatalog) -> None:
    await service.execute("Example")

    with pytest.raises(CatalogNameTaken):
        await service.execute("Example")
```

Run against the generated project:

```
$ uv run pytest tests/catalog/test_services.py -v
tests/catalog/test_services.py::test_create_catalog_persists_and_publishes PASSED
tests/catalog/test_services.py::test_create_catalog_rejects_duplicate_name PASSED
========================= 2 passed in 0.01s =========================
```

0.01 seconds, no Postgres container. `tests/catalog/test_router.py` (unchanged, already documented in
`references/architecture.md`) covers the same use case again through the real HTTP + Postgres path —
neither file replaces the other; they answer different questions ("does the logic work?" versus "does
it work against a real database and a real transaction?").

## Applying this to a module by hand

`scripts/scaffold.py --add-module <name>` generates all of the above automatically. Writing it by
hand, the order that keeps the plumbing honest (same order as `references/architecture.md#adding-a-module`):

1. `constants.py` — grouped classes for limits, cache keys, event identity; enums for status and error codes.
2. `rules.py` / `utils/` — pure decisions and formatting, each a class, before there's any I/O to write against.
3. `schemas.py` — `field_validator`s calling straight into the classes from step 2, so the wire boundary rejects bad input before anything downstream runs.
4. `repository.py` — `Abstract{X}Repository(AbstractRepository[...])` first, then the SQLAlchemy class implementing it, decorated `@database`.
5. `uow.py` (if not `--minimal`) — same shape, `Abstract{X}UnitOfWork(AbstractUnitOfWork)` then the concrete class.
6. `services/*.py` — one file per use case, each class extending `AbstractUseCase`, decorated `@use_case`, constructor typed against the `Abstract*` repository/uow.
7. `dependencies.py` — the composition root: construct the concrete class here, type every other parameter against the abstraction.
8. `public.py` — the facade, decorated `@facade`, also typed against the abstraction.
9. `tests/<name>/test_services.py` — a `Fake{X}Repository`/`Fake{X}UnitOfWork` alongside the real `test_router.py` integration test.

Two pieces of root mechanism have to already be in place for step 3 to be safe, not something each
module re-derives: `app/main.py`'s `RequestValidationError` handler (envelopes a schema validator's
failure) and `app/database.py`'s `get_session` (commits once the request completes cleanly). Both are
generated automatically by `scripts/scaffold.py` and don't need touching per module.
