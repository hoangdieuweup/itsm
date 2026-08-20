"""Templates for the tests/ tree.

Tests live outside app/, mirroring its module layout, instead of colocated
inside each module — the standard Python convention, and it keeps the
shipped package free of test code. Nothing under tests/ is scanned by
lint-imports (root_package = app), so a test may import anything it needs
to exercise, including a module's internals.
"""


def _cls(name: str) -> str:
    """Convert a module name into a class prefix."""
    return "".join(p.capitalize() for p in name.replace("-", "_").split("_"))


def conftest(with_cache: bool) -> str:
    """Render tests/conftest.py: the one place the test database and client live."""
    cache_import = (
        "\nfrom redis.asyncio import Redis\n\n"
        "from app.integrations.cache.client import CacheClient\n"
        "from app.integrations.cache.config import cache_settings\n"
        "from app.integrations.cache.dependencies import get_cache\n"
        if with_cache
        else ""
    )
    cache_override_setup = (
        '''

    async def override_get_cache() -> CacheClient:
        return CacheClient(Redis.from_url(str(cache_settings.URL)), cache_settings.DEFAULT_TTL)

    app.dependency_overrides[get_cache] = override_get_cache'''
        if with_cache
        else ""
    )

    return f'''
"""Shared fixtures: one Postgres container for the whole run, tables truncated
after each test for isolation, and an HTTP client wired to it."""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from testcontainers.postgres import PostgresContainer

from app.core.database import Base, get_session
from app.main import app
{cache_import}

@pytest.fixture(scope="session")
def postgres_url() -> AsyncIterator[str]:
    """Start one Postgres container for the whole test session."""
    with PostgresContainer("postgres:16-alpine") as container:
        yield container.get_connection_url(driver="asyncpg")


@pytest.fixture(scope="session")
async def engine(postgres_url: str):
    """Create the schema once against the container."""
    engine = create_async_engine(postgres_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def client(engine) -> AsyncIterator[AsyncClient]:
    """Provide an HTTP client backed by the test database.

    ASGITransport runs the app in its own anyio task so it can stream the
    response, so a connection opened here and handed to the app would be
    used from a different task than the one that created it — asyncpg
    rejects that. The override below creates a session fresh on every call
    instead, entirely inside whichever task is actually handling the
    request, then every table is truncated once the client is done so the
    next test starts from a clean slate. ASGITransport also skips the app's
    lifespan, so any other dependency that normally reads a pool off
    app.state (cache, when enabled) is overridden here too.
    """
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_session] = override_get_session
{cache_override_setup}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client

    app.dependency_overrides.clear()
    async with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())
'''


def test_rules(name: str) -> str:
    """Render tests/<name>/test_rules.py: plain unit tests, no fixtures."""
    cls = _cls(name)
    return f'''
"""Unit tests for app.{name}.rules — pure decisions, no I/O, no fixtures."""

import pytest

from app.modules.{name}.constants import {cls}Limits, {cls}Status
from app.modules.{name}.rules import {cls}Rules


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("ab", True),
        ("a" * ({cls}Limits.MIN_NAME_LENGTH - 1), False),
        ("a" * {cls}Limits.MAX_NAME_LENGTH, True),
        ("a" * ({cls}Limits.MAX_NAME_LENGTH + 1), False),
    ],
)
def test_is_valid_name(value: str, expected: bool) -> None:
    """A name is valid only within the configured length range."""
    assert {cls}Rules.is_valid_name(value) is expected


def test_can_transition_draft_to_active() -> None:
    """Draft is allowed to move forward to active."""
    assert {cls}Rules.can_transition({cls}Status.DRAFT, {cls}Status.ACTIVE) is True


def test_can_transition_archived_is_terminal() -> None:
    """Archived has no allowed outgoing transition."""
    assert {cls}Rules.can_transition({cls}Status.ARCHIVED, {cls}Status.ACTIVE) is False
'''


def test_services(name: str, with_uow: bool) -> str:
    """Render tests/<name>/test_services.py: fast unit tests against a Fake, no database.

    AbstractRepository/AbstractUnitOfWork (app/repository.py, app/uow.py)
    exist for exactly this: every branch of a use case runs against an
    in-memory double, with no container to start and no table to truncate.
    test_router.py still exercises the same use case through the real
    Postgres path over HTTP — this file is faster, not a replacement for it.
    See references/layer-examples.md for the full explanation.
    """
    cls = _cls(name)

    if with_uow:
        uow_import = f"from app.modules.{name}.uow import Abstract{cls}UnitOfWork\n"
        double = f'''
class Fake{cls}UnitOfWork(Abstract{cls}UnitOfWork):
    """In-memory unit of work: no session, no network, no fixtures."""

    def __init__(self) -> None:
        self.{name} = Fake{cls}Repository()
        self.committed = False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.committed = False


@pytest.fixture
def uow() -> Fake{cls}UnitOfWork:
    """Provide a fresh in-memory unit of work for each test."""
    return Fake{cls}UnitOfWork()


@pytest.fixture
def service(uow: Fake{cls}UnitOfWork, events: InMemoryEventBus) -> Create{cls}:
    """Provide the use case under test, wired to the fakes above."""
    return Create{cls}(uow, events)
'''
        committed_line = "\n    assert uow.committed is True"
        persisted_test_args = "service: Create{cls}, uow: Fake{cls}UnitOfWork, events: InMemoryEventBus".format(
            cls=cls
        )
    else:
        uow_import = ""
        double = f'''
@pytest.fixture
def repo() -> Fake{cls}Repository:
    """Provide a fresh in-memory repository for each test."""
    return Fake{cls}Repository()


@pytest.fixture
def service(repo: Fake{cls}Repository, events: InMemoryEventBus) -> Create{cls}:
    """Provide the use case under test, wired to the fakes above."""
    return Create{cls}(repo, events)
'''
        committed_line = ""
        persisted_test_args = "service: Create{cls}, events: InMemoryEventBus".format(cls=cls)

    return f'''
"""Unit tests for app.{name}.services.create_{name} — a Fake stands in for the
database, so every branch runs without a container or any fixture beyond the
fakes below. tests/{name}/test_router.py exercises the same use case again
through the real Postgres path; this file is faster, not a replacement.
"""

from datetime import UTC, datetime

import pytest

from app.core.events import DomainEvent, EventBus
from app.modules.{name}.constants import {cls}Status
from app.modules.{name}.exceptions import {cls}NameTaken
from app.modules.{name}.repository import Abstract{cls}Repository
{uow_import}from app.modules.{name}.schemas import {cls}Read
from app.modules.{name}.services.create_{name} import Create{cls}


class InMemoryEventBus(EventBus):
    """Records published events instead of dispatching them to handlers."""

    def __init__(self) -> None:
        super().__init__()
        self.published: list[DomainEvent] = []

    async def publish(self, event: DomainEvent) -> None:
        """Record the event instead of delivering it to a handler."""
        self.published.append(event)


class Fake{cls}Repository(Abstract{cls}Repository):
    """In-memory stand-in for {cls}Repository — a dict instead of a table.

    Implements every abstract method Abstract{cls}Repository declares. Miss
    one and Python refuses to instantiate this class with a TypeError, which
    is the actual enforcement behind typing the fixture against the abstract
    contract instead of the concrete SQLAlchemy class.
    """

    def __init__(self) -> None:
        self._rows: dict[int, {cls}Read] = {{}}
        self._next_id = 1

    async def get_by_id(self, entity_id: int) -> {cls}Read | None:
        """Return one entity, or None when it does not exist."""
        return self._rows.get(entity_id)

    async def list_page(self, limit: int, offset: int) -> tuple[list[{cls}Read], int]:
        """Return one page of entities together with the total count."""
        items = list(self._rows.values())[offset : offset + limit]
        return items, len(self._rows)

    async def find_by_name(self, name: str) -> {cls}Read | None:
        """Look up by name, scanning the dict instead of running a query."""
        return next((row for row in self._rows.values() if row.name == name), None)

    async def create(self, name: str) -> {cls}Read:
        """Insert a new row into the dict, assigning the next id."""
        row = {cls}Read(id=self._next_id, name=name, status={cls}Status.DRAFT, created_at=datetime.now(UTC))
        self._rows[row.id] = row
        self._next_id += 1
        return row

    async def set_status(self, entity_id: int, status: {cls}Status) -> {cls}Read:
        """Replace the stored row with one carrying the new status."""
        updated = self._rows[entity_id].model_copy(update={{"status": status}})
        self._rows[entity_id] = updated
        return updated

{double}

@pytest.fixture
def events() -> InMemoryEventBus:
    """Provide an event bus that records instead of dispatching."""
    return InMemoryEventBus()


async def test_create_{name}_persists_and_publishes({persisted_test_args}) -> None:
    """The use case persists through the fake and publishes exactly one event."""
    created = await service.execute("Example")

    assert created.name == "Example"
    assert len(events.published) == 1{committed_line}


async def test_create_{name}_rejects_duplicate_name(service: Create{cls}) -> None:
    """The uniqueness rule runs before a second row is ever created."""
    await service.execute("Example")

    with pytest.raises({cls}NameTaken):
        await service.execute("Example")
'''


def test_router(name: str) -> str:
    """Render tests/<name>/test_router.py: integration tests against a real Postgres.

    Every response is the {{success, data, error}} envelope (see app/models.py
    and references/api-contract.md), so assertions read through ["data"] /
    ["error"] rather than the bare payload.
    """
    return f'''
"""Integration tests for app.{name}.router, against the real database via the client fixture."""


async def test_create_and_get_{name}(client) -> None:
    """A created entity can be fetched back by id."""
    create_response = await client.post("/api/v1/{name}", json={{"name": "Example"}})
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["success"] is True
    entity_id = created["data"]["id"]

    get_response = await client.get(f"/api/v1/{name}/{{entity_id}}")
    assert get_response.status_code == 200
    body = get_response.json()
    assert body["success"] is True
    assert body["data"]["name"] == "Example"


async def test_get_{name}_not_found(client) -> None:
    """A missing id returns 404 with the error half of the envelope populated."""
    response = await client.get("/api/v1/{name}/999999")
    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False
    assert body["data"] is None
    assert body["error"]["code"] == "{name}_not_found"


async def test_create_{name}_rejects_duplicate_name(client) -> None:
    """The uniqueness rule is enforced at the API boundary, not just in the database."""
    payload = {{"name": "Duplicate"}}
    first = await client.post("/api/v1/{name}", json=payload)
    assert first.status_code == 201

    second = await client.post("/api/v1/{name}", json=payload)
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "{name}_name_taken"


async def test_create_{name}_rejects_invalid_name_through_the_envelope(client) -> None:
    """A schema level field_validator failure still returns the {{success, data, error}} envelope.

    Without app/main.py's RequestValidationError handler, this would come
    back as FastAPI's own default {{"detail": [...]}} shape instead — see
    references/api-contract.md and references/layer-examples.md.
    """
    response = await client.post("/api/v1/{name}", json={{"name": "a"}})
    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["data"] is None
    assert body["error"]["code"] == "validation_failed"
    assert "errors" in body["error"]["context"]
'''
