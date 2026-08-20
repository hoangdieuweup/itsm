"""Shared fixtures: one Postgres container for the whole run, tables truncated
after each test for isolation, and an HTTP client wired to it."""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from app.core.database import Base, get_session
from app.integrations.cache.client import CacheClient
from app.integrations.cache.config import cache_settings
from app.integrations.cache.dependencies import get_cache
from app.main import app


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

    async def override_get_cache() -> CacheClient:
        return CacheClient(Redis.from_url(str(cache_settings.URL)), cache_settings.DEFAULT_TTL)

    app.dependency_overrides[get_cache] = override_get_cache

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client

    app.dependency_overrides.clear()
    async with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())
