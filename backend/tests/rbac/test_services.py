"""Unit tests for the rbac module's use cases. No database — every collaborator
is a fake implementing the module's own Abstract* contract."""

import pytest

from app.modules.rbac.constants import RbacDefaults
from app.modules.rbac.exceptions import (
    CannotModifyProtectedAdmin,
    CannotRemoveLastAdmin,
    DuplicateRoleName,
    RoleInUse,
    RoleNotFound,
    SystemRoleImmutable,
    TargetUserNotFound,
    UnknownPermissionId,
)
from app.modules.rbac.repository import (
    AbstractPermissionRepository,
    AbstractRoleRepository,
    AbstractUserRoleRepository,
)
from app.modules.rbac.schemas import PermissionRead, RoleRead
from app.modules.rbac.services.assign_default_role import AssignDefaultRole
from app.modules.rbac.services.assign_role import AssignRole
from app.modules.rbac.services.create_role import CreateRole
from app.modules.rbac.services.delete_role import DeleteRole
from app.modules.rbac.services.update_role import UpdateRole
from app.modules.rbac.uow import AbstractRbacUnitOfWork

_CATALOG = [
    PermissionRead(id=1, resource="role", action="read", description_key="permissions.role.read"),
    PermissionRead(id=2, resource="role", action="create", description_key="permissions.role.create"),
]


class FakeRoleRepository(AbstractRoleRepository):
    def __init__(self) -> None:
        self._rows: dict[int, RoleRead] = {}
        self._next_id = 1
        self._grants: dict[int, int] = {}  # role_id -> count, set by tests via seed_grants

    async def get_by_id(self, entity_id: int) -> RoleRead | None:
        return self._rows.get(entity_id)

    async def list_page(self, limit: int, offset: int) -> tuple[list[RoleRead], int]:
        items = list(self._rows.values())[offset : offset + limit]
        return items, len(self._rows)

    async def find_by_name(self, name: str) -> RoleRead | None:
        return next((r for r in self._rows.values() if r.name == name), None)

    async def create(self, *, name: str, is_system: bool, permission_ids: list[int]) -> RoleRead:
        permissions = [p for p in _CATALOG if p.id in permission_ids]
        role = RoleRead(id=self._next_id, name=name, is_system=is_system, permissions=permissions)
        self._rows[role.id] = role
        self._next_id += 1
        return role

    async def update(self, role_id: int, *, name: str | None, permission_ids: list[int] | None) -> RoleRead:
        existing = self._rows[role_id]
        permissions = existing.permissions
        if permission_ids is not None:
            permissions = [p for p in _CATALOG if p.id in permission_ids]
        updated = existing.model_copy(update={"name": name or existing.name, "permissions": permissions})
        self._rows[role_id] = updated
        return updated

    async def delete(self, role_id: int) -> None:
        self._rows.pop(role_id, None)

    async def count_users_with_role(self, role_id: int) -> int:
        return self._grants.get(role_id, 0)

    def seed(self, role: RoleRead, *, grants: int = 0) -> None:
        self._rows[role.id] = role
        self._next_id = max(self._next_id, role.id + 1)
        self._grants[role.id] = grants


class FakePermissionRepository(AbstractPermissionRepository):
    async def get_by_id(self, entity_id: int) -> PermissionRead | None:
        return next((p for p in _CATALOG if p.id == entity_id), None)

    async def list_page(self, limit: int, offset: int) -> tuple[list[PermissionRead], int]:
        return _CATALOG[offset : offset + limit], len(_CATALOG)

    async def list_all(self) -> list[PermissionRead]:
        return list(_CATALOG)

    async def find_by_ids(self, ids: list[int]) -> list[PermissionRead]:
        return [p for p in _CATALOG if p.id in ids]


class FakeUserRoleRepository(AbstractUserRoleRepository):
    """Resolves grants through the same FakeRoleRepository the uow already
    holds, so a role seeded via uow.roles.seed() and then granted via
    grants[user_id] = role_id round-trips correctly through get_role_for_user
    — needed for AssignRole's bus-factor check, which reads the *current*
    role before allowing a reassignment."""

    def __init__(self, roles: "FakeRoleRepository") -> None:
        self._roles = roles
        self.grants: dict[int, int] = {}  # user_id -> role_id

    async def get_role_for_user(self, user_id: int) -> RoleRead | None:
        role_id = self.grants.get(user_id)
        if role_id is None:
            return None
        return await self._roles.get_by_id(role_id)

    async def assign(self, user_id: int, role_id: int) -> None:
        self.grants[user_id] = role_id

    async def user_has_permission(self, user_id: int, resource: str, action: str) -> bool:
        return False  # not exercised by the services under test here


class FakeRbacUnitOfWork(AbstractRbacUnitOfWork):
    def __init__(self) -> None:
        self.roles = FakeRoleRepository()
        self.permissions = FakePermissionRepository()
        self.user_roles = FakeUserRoleRepository(self.roles)
        self.commits = 0
        self.stale: list[tuple[str, int]] = []

    def mark_stale(self, entity: str, entity_id: int) -> None:
        self.stale.append((entity, entity_id))

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        pass


def _admin_role(*, grants: int) -> RoleRead:
    return RoleRead(id=10, name=RbacDefaults.ADMIN_ROLE_NAME, is_system=True, permissions=[])


async def _not_protected(user_id: int) -> bool:
    return False


class TestCreateRole:
    async def test_creates_role_with_given_permissions(self) -> None:
        uow = FakeRbacUnitOfWork()

        role = await CreateRole(uow).execute("support", [1, 2])

        assert role.name == "support"
        assert role.is_system is False
        assert {p.id for p in role.permissions} == {1, 2}
        assert uow.commits == 1

    async def test_rejects_duplicate_name(self) -> None:
        uow = FakeRbacUnitOfWork()
        uow.roles.seed(RoleRead(id=1, name="support", is_system=False, permissions=[]))

        with pytest.raises(DuplicateRoleName):
            await CreateRole(uow).execute("support", [])

    async def test_rejects_unknown_permission_id(self) -> None:
        uow = FakeRbacUnitOfWork()

        with pytest.raises(UnknownPermissionId):
            await CreateRole(uow).execute("support", [999])


class TestUpdateRole:
    async def test_renames_a_custom_role(self) -> None:
        uow = FakeRbacUnitOfWork()
        uow.roles.seed(RoleRead(id=1, name="support", is_system=False, permissions=[]))

        updated = await UpdateRole(uow).execute(1, name="support-l1", permission_ids=None)

        assert updated.name == "support-l1"

    async def test_rejects_renaming_a_system_role(self) -> None:
        uow = FakeRbacUnitOfWork()
        uow.roles.seed(_admin_role(grants=1))

        with pytest.raises(SystemRoleImmutable):
            await UpdateRole(uow).execute(10, name="root", permission_ids=None)

    async def test_allows_editing_a_system_roles_permissions(self) -> None:
        uow = FakeRbacUnitOfWork()
        uow.roles.seed(_admin_role(grants=1))

        updated = await UpdateRole(uow).execute(10, name=None, permission_ids=[1])

        assert {p.id for p in updated.permissions} == {1}

    async def test_missing_role_raises(self) -> None:
        uow = FakeRbacUnitOfWork()

        with pytest.raises(RoleNotFound):
            await UpdateRole(uow).execute(404, name="x", permission_ids=None)


class TestDeleteRole:
    async def test_deletes_a_custom_role_with_no_users(self) -> None:
        uow = FakeRbacUnitOfWork()
        uow.roles.seed(RoleRead(id=1, name="support", is_system=False, permissions=[]), grants=0)

        await DeleteRole(uow).execute(1)

        assert await uow.roles.get_by_id(1) is None

    async def test_rejects_deleting_a_system_role(self) -> None:
        uow = FakeRbacUnitOfWork()
        uow.roles.seed(_admin_role(grants=1))

        with pytest.raises(SystemRoleImmutable):
            await DeleteRole(uow).execute(10)

    async def test_rejects_deleting_a_role_still_in_use(self) -> None:
        uow = FakeRbacUnitOfWork()
        uow.roles.seed(RoleRead(id=1, name="support", is_system=False, permissions=[]), grants=2)

        with pytest.raises(RoleInUse):
            await DeleteRole(uow).execute(1)


class TestAssignRole:
    async def test_assigns_role_to_an_existing_user(self) -> None:
        uow = FakeRbacUnitOfWork()
        uow.roles.seed(RoleRead(id=1, name="support", is_system=False, permissions=[]))

        async def user_lookup(user_id: int):
            return object()  # any non-None sentinel — AssignRole only checks for None

        await AssignRole(uow, user_lookup, _not_protected).execute(42, 1)

        assert uow.user_roles.grants[42] == 1

    async def test_rejects_unknown_user(self) -> None:
        uow = FakeRbacUnitOfWork()
        uow.roles.seed(RoleRead(id=1, name="support", is_system=False, permissions=[]))

        async def user_lookup(user_id: int):
            return None

        with pytest.raises(TargetUserNotFound):
            await AssignRole(uow, user_lookup, _not_protected).execute(42, 1)

    async def test_rejects_reassigning_the_last_admin_away(self) -> None:
        uow = FakeRbacUnitOfWork()
        uow.roles.seed(_admin_role(grants=1))
        uow.roles.seed(RoleRead(id=1, name="support", is_system=False, permissions=[]))
        uow.user_roles.grants[42] = 10  # currently the admin

        async def user_lookup(user_id: int):
            return object()

        with pytest.raises(CannotRemoveLastAdmin):
            await AssignRole(uow, user_lookup, _not_protected).execute(42, 1)

    async def test_missing_target_role_raises(self) -> None:
        uow = FakeRbacUnitOfWork()

        async def user_lookup(user_id: int):
            return object()

        with pytest.raises(RoleNotFound):
            await AssignRole(uow, user_lookup, _not_protected).execute(42, 404)

    async def test_rejects_modifying_a_protected_admin(self) -> None:
        uow = FakeRbacUnitOfWork()
        uow.roles.seed(RoleRead(id=1, name="support", is_system=False, permissions=[]))

        async def user_lookup(user_id: int):
            return object()

        async def is_protected(user_id: int) -> bool:
            return True

        with pytest.raises(CannotModifyProtectedAdmin):
            await AssignRole(uow, user_lookup, is_protected).execute(42, 1)

        assert 42 not in uow.user_roles.grants


class TestAssignDefaultRole:
    async def test_grants_the_seeded_member_role(self) -> None:
        uow = FakeRbacUnitOfWork()
        member = RoleRead(id=3, name=RbacDefaults.MEMBER_ROLE_NAME, is_system=True, permissions=[])
        uow.roles.seed(member)

        await AssignDefaultRole(uow).execute(99)

        assert uow.user_roles.grants[99] == 3
