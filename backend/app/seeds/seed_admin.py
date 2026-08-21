"""Idempotent seed: the break-glass admin account from USERS__ADMIN_EMAIL.

Run via `python -m app.seeds.seed_admin`. No-op (with a log line) if
USERS__ADMIN_EMAIL is unset — this is an optional bootstrap step, not a
requirement to run the app. Requires seed_rbac.py to have already run (the
admin role must exist). This account's protection (see
UsersRules.is_protected_admin_email) is by email, not by holding any
particular role — the admin role grant just gives it the same full access
every admin has, nothing more.

The seeded name is a placeholder, not configurable: when this account
later logs in for real via DX SSO, SyncExternalUser's update_profile
overwrites name (and email/external_user_id/employee_code/email_confirmed)
with the real DX profile's values, same as any other user's first login.
"""

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.modules.common.constants import UserStatus
from app.modules.rbac.constants import RbacDefaults
from app.modules.rbac.models import Role, UserRole
from app.modules.users.config import users_settings
from app.modules.users.models import User

logger = logging.getLogger(__name__)


async def run() -> None:
    """Upsert the break-glass admin user and grant it the admin role."""
    if not users_settings.ADMIN_EMAIL:
        logger.info("USERS__ADMIN_EMAIL not set — skipping admin seed")
        return

    engine = create_async_engine(str(settings.DATABASE_URL))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        user = await session.scalar(select(User).where(User.email == users_settings.ADMIN_EMAIL))
        if user is None:
            user = User(
                email=users_settings.ADMIN_EMAIL,
                name="Admin",  # placeholder — overwritten by the real DX profile on first login
                status=UserStatus.ACTIVE,
                external_user_id=None,
                employee_code=None,
                email_confirmed=True,
            )
            session.add(user)
            await session.flush()
            logger.info("seeded break-glass admin user %s", users_settings.ADMIN_EMAIL)

        admin_role = await session.scalar(select(Role).where(Role.name == RbacDefaults.ADMIN_ROLE_NAME))
        if admin_role is None:
            raise RuntimeError("admin role missing — run `python -m app.seeds.seed_rbac` first")

        grant = await session.get(UserRole, user.id)
        if grant is None:
            session.add(UserRole(user_id=user.id, role_id=admin_role.id))
            logger.info("granted admin role to %s", users_settings.ADMIN_EMAIL)
        elif grant.role_id != admin_role.id:
            grant.role_id = admin_role.id
            logger.info("reasserted admin role for %s", users_settings.ADMIN_EMAIL)

        await session.commit()

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
