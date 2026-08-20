"""Ownership of every shared resource, bound to the application lifecycle."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.integrations.cache.client import RedisConnectionFactory
from app.integrations.queue.client import Broker
from app.integrations.storage.client import StorageClient

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create pools on startup and release them on shutdown."""
    engine = create_async_engine(
        str(settings.DATABASE_URL),
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_pre_ping=True,
        connect_args={"server_settings": {"statement_timeout": str(settings.DB_STATEMENT_TIMEOUT_MS)}},
    )
    app.state.engine = engine
    app.state.session_factory = async_sessionmaker(engine, expire_on_commit=False)
    app.state.redis = RedisConnectionFactory.create()
    app.state.broker = Broker()
    await app.state.broker.connect()
    app.state.storage = StorageClient()

    logger.info("application resources initialized")
    yield

    await app.state.redis.aclose()
    await app.state.broker.close()
    await app.state.storage.close()
    await engine.dispose()
    logger.info("application resources released")
