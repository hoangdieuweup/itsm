"""Idempotent seed: the permission catalog and the two default roles.

Run via `python -m app.seeds.seed_rbac`. Safe to run on every deploy — new
permissions added to RbacPermissionCatalog.CATALOG appear on the next run
without touching existing role/permission rows. There is no "owner" role —
admin is the highest role this seeds. A break-glass admin *account* (not a
role) can optionally be seeded separately by seed_admin.py, when
AUTH__ADMIN_EMAIL is configured, not unconditionally on every deploy. If a
project needs additional roles beyond admin/member, create them through the
admin UI (POST /rbac/roles) once an admin account exists to do so.
"""

import asyncio
import logging
import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.modules.rbac.constants import RbacDefaults, RbacPermissionCatalog
from app.modules.rbac.models import Permission, Role, RolePermission

logger = logging.getLogger(__name__)


async def _remove_stale_permissions(session, catalog_keys: set[tuple[str, str]]) -> None:
    """Delete any Permission not in CATALOG, unless a role (global or
    project) still grants it — deleting a still-granted row cascades
    role_permissions/project_role_permissions and silently strips real
    capability. Refuse and log instead; a migration should move the
    grants first."""
    all_db_perms = list(await session.scalars(select(Permission)))
    stale_perms = [p for p in all_db_perms if (p.resource, p.action) not in catalog_keys]
    if not stale_perms:
        return

    stale_ids = [p.id for p in stale_perms]
    stale_links = list(
        await session.scalars(select(RolePermission).where(RolePermission.permission_id.in_(stale_ids)))
    )
    granted_ids = {link.permission_id for link in stale_links}
    # project_role_permissions is owned by projects — a raw-SQL read here
    # is the smallest exception to seed_rbac.py never importing it.
    project_grants_query = text(
        "SELECT permission_id FROM project_role_permissions WHERE permission_id = ANY(:ids)"
    ).bindparams(ids=stale_ids)
    granted_project_ids = set(await session.scalars(project_grants_query))
    blocked = granted_ids | granted_project_ids

    for perm in stale_perms:
        if perm.id in blocked:
            logger.error(
                "REFUSING to remove permission %s.%s — roles still grant it. Write an Alembic "
                "data migration that moves those grants first, then re-run this seed. Nothing "
                "was deleted for this permission.",
                perm.resource,
                perm.action,
            )
    for link in stale_links:
        if link.permission_id not in blocked:
            await session.delete(link)
    for perm in stale_perms:
        if perm.id in blocked:
            continue
        logger.info("removing stale permission %s.%s", perm.resource, perm.action)
        await session.delete(perm)
    await session.flush()


async def run() -> None:
    """Upsert the permission catalog, then the admin/member default roles.

    Cleanup: any DB permissions NOT in the current CATALOG are deleted,
    along with their role_permission links. This keeps the DB in sync
    with the code — the CATALOG is the single source of truth.
    """
    engine = create_async_engine(str(settings.DATABASE_URL))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        # ── 1. Upsert every CATALOG permission ─────────────────────
        catalog_keys: set[tuple[str, str]] = set()
        permission_ids: list[uuid.UUID] = []
        for resource, action, description_key in RbacPermissionCatalog.CATALOG:
            catalog_keys.add((resource, action))
            row = await session.scalar(
                select(Permission).where(Permission.resource == resource, Permission.action == action)
            )
            if row is None:
                row = Permission(resource=resource, action=action, description_key=description_key)
                session.add(row)
                await session.flush()
                logger.info("seeded permission %s.%s", resource, action)
            elif row.description_key != description_key:
                row.description_key = description_key
                await session.flush()
                logger.info("updated description_key for %s.%s", resource, action)
            permission_ids.append(row.id)

        # ── 2. Clean up stale permissions no longer in CATALOG ──────
        await _remove_stale_permissions(session, catalog_keys)
        await session.commit()

        # ── 3. Upsert default roles ─────────────────────────────────
        for name, grants_everything in (
            (RbacDefaults.ADMIN_ROLE_NAME, True),
            (RbacDefaults.MEMBER_ROLE_NAME, False),
        ):
            role = await session.scalar(select(Role).where(Role.name == name))
            if role is None:
                role = Role(name=name, is_system=True)
                session.add(role)
                await session.flush()
                logger.info("seeded role %s", name)

            if grants_everything:
                existing_perms = set(
                    await session.scalars(
                        select(RolePermission.permission_id).where(RolePermission.role_id == role.id)
                    )
                )
                for permission_id in permission_ids:
                    if permission_id not in existing_perms:
                        session.add(RolePermission(role_id=role.id, permission_id=permission_id))
                await session.flush()
        await session.commit()

    await engine.dispose()

    # ── 4. Flush RBAC Redis cache so require_permission sees the new set ─
    try:
        from redis.asyncio import ConnectionPool, Redis as AsyncRedis

        from app.integrations.cache.config import cache_settings

        pool = ConnectionPool.from_url(
            str(cache_settings.URL),
            decode_responses=True,
            max_connections=2,
        )
        redis = AsyncRedis(connection_pool=pool)
        # Delete all version counters for roles and user_roles so the next
        # read triggers a fresh DB load rather than serving stale cached data.
        deleted = 0
        for pattern in ("ver:role:*", "role:*", "ver:user_role:*", "user_role:*"):
            async for key in redis.scan_iter(match=pattern, count=200):
                await redis.delete(key)
                deleted += 1
        await redis.aclose()
        await pool.disconnect()
        logger.info("flushed %d RBAC redis cache keys", deleted)
    except Exception as exc:
        # Cache flush is best-effort — if Redis is down, entries expire via TTL
        logger.warning("could not flush RBAC redis cache: %s", exc)


if __name__ == "__main__":
    asyncio.run(run())
