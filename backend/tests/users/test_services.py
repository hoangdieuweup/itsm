"""Unit tests for the users module's use cases. No database — every
collaborator is a fake implementing the module's own Abstract* contract.
Router-level behavior is covered separately in tests/users/test_router.py.
"""

from datetime import UTC, datetime

import pytest

from app.modules.users.config import users_settings
from app.modules.users.constants import UserStatus
from app.modules.users.exceptions import CannotBlockLastAdmin, CannotModifyProtectedAdmin
from app.modules.users.repository import AbstractUserRepository
from app.modules.users.schemas import UserRead
from app.modules.users.services.update_user_status import UpdateUserStatus
from app.modules.users.uow import AbstractUsersUnitOfWork


class FakeUserRepository(AbstractUserRepository):
    def __init__(self) -> None:
        self._rows: dict[int, UserRead] = {}
        self._next_id = 1

    async def get_by_id(self, entity_id: int) -> UserRead | None:
        return self._rows.get(entity_id)

    async def list_page(self, limit: int, offset: int) -> tuple[list[UserRead], int]:
        items = list(self._rows.values())[offset : offset + limit]
        return items, len(self._rows)

    async def find_by_email(self, email: str) -> UserRead | None:
        return next((u for u in self._rows.values() if u.email == email), None)

    async def find_by_external_id(self, external_user_id: str) -> UserRead | None:
        return next((u for u in self._rows.values() if u.external_user_id == external_user_id), None)

    async def create(
        self,
        *,
        email: str,
        name: str,
        external_user_id: str,
        employee_code: str | None,
        email_confirmed: bool,
    ) -> UserRead:
        user = UserRead(
            id=self._next_id,
            email=email,
            name=name,
            status=UserStatus.ACTIVE,
            external_user_id=external_user_id,
            employee_code=employee_code,
            email_confirmed=email_confirmed,
            last_login_at=None,
            created_at=datetime.now(UTC),
        )
        self._rows[user.id] = user
        self._next_id += 1
        return user

    async def update_profile(
        self,
        user_id: int,
        *,
        email: str,
        name: str,
        external_user_id: str,
        employee_code: str | None,
        email_confirmed: bool,
    ) -> UserRead:
        existing = self._rows[user_id]
        updated = existing.model_copy(
            update={
                "email": email,
                "name": name,
                "external_user_id": external_user_id,
                "employee_code": employee_code,
                "email_confirmed": email_confirmed,
            }
        )
        self._rows[user_id] = updated
        return updated

    async def set_last_login(self, user_id: int, at: datetime) -> None:
        existing = self._rows.get(user_id)
        if existing is not None:
            self._rows[user_id] = existing.model_copy(update={"last_login_at": at})

    async def set_status(self, user_id: int, status: UserStatus) -> UserRead:
        existing = self._rows[user_id]
        updated = existing.model_copy(update={"status": status})
        self._rows[user_id] = updated
        return updated


class FakeUsersUnitOfWork(AbstractUsersUnitOfWork):
    """In-memory unit of work. commit/rollback are no-ops that just count calls."""

    def __init__(self) -> None:
        self.users = FakeUserRepository()
        self.commits = 0
        self.rollbacks = 0
        self.stale: list[tuple[str, int]] = []

    def mark_stale(self, entity: str, entity_id: int) -> None:
        self.stale.append((entity, entity_id))

    async def invalidate_now(self, entity: str, entity_id: int) -> None:
        pass

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class FakeRbacApi:
    """Duck-typed stand-in for app.modules.rbac.public.RbacApi — UpdateUserStatus
    only calls is_last_admin, so that's the only method this fake needs."""

    def __init__(self, *, last_admin_ids: frozenset[int] = frozenset()) -> None:
        self._last_admin_ids = last_admin_ids

    async def is_last_admin(self, user_id: int) -> bool:
        return user_id in self._last_admin_ids


class TestUpdateUserStatus:
    """UpdateUserStatus: block/unblock a user, rejecting a block that would
    leave zero users holding the admin role."""

    async def test_blocks_an_active_user(self) -> None:
        uow = FakeUsersUnitOfWork()
        user = await uow.users.create(
            email="target@example.com",
            name="Target",
            external_user_id="dx-target",
            employee_code=None,
            email_confirmed=True,
        )
        rbac_api = FakeRbacApi()

        updated = await UpdateUserStatus(uow, rbac_api).execute(user.id, UserStatus.BLOCKED)

        assert updated.status is UserStatus.BLOCKED
        assert uow.commits == 1

    async def test_unblocking_never_consults_the_bus_factor_rule(self) -> None:
        uow = FakeUsersUnitOfWork()
        user = await uow.users.create(
            email="target@example.com",
            name="Target",
            external_user_id="dx-target",
            employee_code=None,
            email_confirmed=True,
        )
        rbac_api = FakeRbacApi(last_admin_ids=frozenset({user.id}))  # would block if this were a BLOCK

        updated = await UpdateUserStatus(uow, rbac_api).execute(user.id, UserStatus.ACTIVE)

        assert updated.status is UserStatus.ACTIVE

    async def test_rejects_blocking_the_last_admin(self) -> None:
        uow = FakeUsersUnitOfWork()
        user = await uow.users.create(
            email="admin@example.com",
            name="Admin",
            external_user_id="dx-admin",
            employee_code=None,
            email_confirmed=True,
        )
        rbac_api = FakeRbacApi(last_admin_ids=frozenset({user.id}))

        with pytest.raises(CannotBlockLastAdmin):
            await UpdateUserStatus(uow, rbac_api).execute(user.id, UserStatus.BLOCKED)

        assert uow.commits == 0

    async def test_rejects_blocking_the_protected_admin(self, monkeypatch) -> None:
        monkeypatch.setattr(users_settings, "ADMIN_EMAIL", "protected@example.com")
        uow = FakeUsersUnitOfWork()
        user = await uow.users.create(
            email="protected@example.com",
            name="Protected",
            external_user_id="dx-protected",
            employee_code=None,
            email_confirmed=True,
        )
        rbac_api = FakeRbacApi()  # is_last_admin would return False — protection must win regardless

        with pytest.raises(CannotModifyProtectedAdmin):
            await UpdateUserStatus(uow, rbac_api).execute(user.id, UserStatus.BLOCKED)

        assert uow.commits == 0
