"""Scheduler process entry point. Runs separately from the API and the
worker — see scripts/start-scheduler.sh.

Builds its own DB engine, Redis connection and Mongo client exactly once
at startup, mirroring lifespan.py's pool tuning (this is a long-running
periodic process, not a one-shot script like app/seeds/). Per tick, opens
one AsyncSession from the shared session_factory and constructs each
module's concrete unit-of-work/facade directly (no FastAPI Depends tree
exists outside a request) — the same "root names the concrete class"
composition pattern app/seeds/ and app/worker.py already use.

Currently one job: DNS/Tunnel drift reconciliation (the spec's "second
safety layer" — Cloudflare has no way to block a dashboard-side change,
so this periodically re-checks live state and files an incident whenever
something changed outside this app).
"""

import asyncio
import logging
import signal

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.core.logging_config import setup_logging
from app.integrations.cache.client import CacheClient, RedisConnectionFactory
from app.integrations.cache.config import cache_settings
from app.integrations.cloudflare.client import CloudflareClient
from app.integrations.mongo.client import MongoConnectionFactory
from app.modules.audit.public import AuditApi
from app.modules.audit.repository import MongoAuditLogRepository
from app.modules.cloudflare.public import CloudflareApi
from app.modules.cloudflare.uow import CloudflareUnitOfWork
from app.modules.observability.config import observability_settings
from app.modules.observability.services.run_drift_reconciliation import RunDriftReconciliation
from app.modules.observability.uow import ObservabilityUnitOfWork
from app.modules.projects.public import ProjectsApi
from app.modules.projects.uow import ProjectsUnitOfWork

setup_logging()
logger = logging.getLogger(__name__)


async def run_reconciliation_once(session_factory, cache: CacheClient, mongo_db) -> None:
    """One full pass: build this tick's collaborators from a fresh session,
    run the job, let the session close on exit."""
    async with session_factory() as session:
        cloudflare_uow = CloudflareUnitOfWork(session, cache)
        observability_uow = ObservabilityUnitOfWork(session)
        projects_uow = ProjectsUnitOfWork(session, cache)

        projects_api = ProjectsApi(projects_uow)
        cloudflare_api = CloudflareApi(cloudflare_uow, CloudflareClient(), projects_api=projects_api)
        use_case = RunDriftReconciliation(
            observability_uow,
            cloudflare_api=cloudflare_api,
            projects_api=projects_api,
            audit_api=AuditApi(MongoAuditLogRepository(mongo_db)),
        )
        await use_case.execute()


async def main() -> None:
    """Build shared resources once, then run the reconciliation pass on a
    fixed interval until stopped, closing everything cleanly on exit."""
    engine = create_async_engine(
        str(settings.DATABASE_URL),
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_pre_ping=True,
        connect_args={"server_settings": {"statement_timeout": str(settings.DB_STATEMENT_TIMEOUT_MS)}},
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    redis = RedisConnectionFactory.create()
    cache = CacheClient(redis, cache_settings.DEFAULT_TTL)
    mongo_client = MongoConnectionFactory.create()
    mongo_db = MongoConnectionFactory.database(mongo_client)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)

    interval = observability_settings.RECONCILIATION_INTERVAL_SECONDS
    logger.info("scheduler started reconciliation_interval_seconds=%s", interval)

    while not stop.is_set():
        try:
            await run_reconciliation_once(session_factory, cache, mongo_db)
        except Exception:
            logger.exception("drift reconciliation pass failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except TimeoutError:
            pass

    logger.info("scheduler stopping")
    await redis.aclose()
    mongo_client.close()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
