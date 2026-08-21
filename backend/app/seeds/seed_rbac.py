"""Idempotent seed: the permission catalog and the three default roles.

Run via `python -m app.seeds.seed_rbac`. Safe to run on every deploy — new
permissions added to RbacPermissionCatalog.CATALOG appear on the next run
without touching existing role/permission rows.
"""

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.modules.rbac.constants import RbacDefaults, RbacPermissionCatalog
from app.modules.rbac.models import Permission, Role, RolePermission

logger = logging.getLogger(__name__)


async def run() -> None:
    """Upsert the permission catalog, then the three default roles."""
    engine = create_async_engine(str(settings.DATABASE_URL))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        permission_ids: list[int] = []
        for resource, action, description in RbacPermissionCatalog.CATALOG:
            row = await session.scalar(
                select(Permission).where(Permission.resource == resource, Permission.action == action)
            )
            if row is None:
                row = Permission(resource=resource, action=action, description=description)
                session.add(row)
                await session.flush()
            permission_ids.append(row.id)
        await session.commit()

        for name, grants_everything in (
            (RbacDefaults.OWNER_ROLE_NAME, True),
            (RbacDefaults.ADMIN_ROLE_NAME, True),
            (RbacDefaults.MEMBER_ROLE_NAME, False),
        ):
            role = await session.scalar(select(Role).where(Role.name == name))
            if role is None:
                role = Role(name=name, is_system=True)
                session.add(role)
                await session.flush()
                if grants_everything:
                    for permission_id in permission_ids:
                        session.add(RolePermission(role_id=role.id, permission_id=permission_id))
                await session.flush()
                logger.info("seeded role %s", name)
        await session.commit()

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
