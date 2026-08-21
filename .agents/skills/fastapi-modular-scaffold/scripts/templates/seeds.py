"""Templates for the app/seeds/ package: idempotent, one-off data setup scripts.

A seed script reaching into one module's repository directly (not through
public.py) is a deliberate exception, not a violation of the facade rule —
seeds are operational tooling, the same category as migrations/env.py, which
already imports every module's models directly.
"""


def _cls(name: str) -> str:
    """Convert a module name into a class prefix."""
    return "".join(p.capitalize() for p in name.replace("-", "_").split("_"))


def seed_example(name: str, with_cache: bool) -> str:
    """Render app/seeds/seed_<name>.py — the idempotent pattern every other seed script copies."""
    cls = _cls(name)
    if with_cache:
        cache_import = (
            "\nfrom redis.asyncio import Redis\n\n"
            "from app.integrations.cache.client import CacheClient\n"
            "from app.integrations.cache.config import cache_settings\n"
        )
        repo_args = "session, cache"
        cache_setup = "\n        cache = CacheClient(Redis.from_url(str(cache_settings.URL)), cache_settings.DEFAULT_TTL)"
    else:
        cache_import = ""
        repo_args = "session"
        cache_setup = ""

    return f'''
"""Seed a starter {name} row. Idempotent — safe to run on every deploy, including prod.

Copy this pattern for real seed data (an owner account, reference data,
feature flags): check for existence by whatever makes the row unique, create
only if missing, log either outcome. Never assume this is the only time it
runs. Run with:
    uv run python -m app.seeds.seed_{name}
"""

import asyncio
import logging

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.modules.{name}.repository import {cls}Repository
{cache_import}
logger = logging.getLogger(__name__)

SEED_NAME = "Starter {cls}"


async def run() -> None:
    """Create the seed row if it doesn't already exist."""
    engine = create_async_engine(str(settings.DATABASE_URL))
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with session_factory() as session:{cache_setup}
        repo = {cls}Repository({repo_args})
        existing = await repo.find_by_name(SEED_NAME)
        if existing is not None:
            logger.info("seed_{name}: already present, skipping")
        else:
            await repo.create(SEED_NAME)
            await session.commit()
            logger.info("seed_{name}: created")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
'''
