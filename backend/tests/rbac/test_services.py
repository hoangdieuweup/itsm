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
from app.modules.rbac.services.assign_roles import AssignRoles
from app.modules.rbac.services.create_role import CreateRole
from app.modules.rbac.services.delete_role import DeleteRole
from app.modules.rbac.services.update_role import UpdateRole
from app.modules.rbac.uow import AbstractRbacUnitOfWork

_CATALOG = [
    PermissionRead(id=1, resource="role", action="create", description_key="permissions.role.create"),
    PermissionRead(id=2, resource="role", action="read", description_key="permissions.role.read"),
    PermissionRead(id=3, resource="role", action="update", description_key="permissions.role.update"),
    PermissionRead(id=4, resource="role", action="delete", description_key="permissions.role.delete"),
    PermissionRead(
        id=5, resource="permission", action="read", description_key="permissions.permission.read"
    ),
    PermissionRead(id=6, resource="user", action="read", description_key="permissions.user.read"),
    PermissionRead(
        id=7, resource="user", action="update_status", description_key="permissions.user.update_status"
    ),
    PermissionRead(
        id=8, resource="user", action="assign_role", description_key="permissions.user.assign_role"
    ),
]


class FakeRoleRepository(AbstractRoleRepository):
    def __init__(self) -> None:
        self.roles: dict[int, RoleRead] = {}
        self.user_counts: dict[int, int] = {}
        self._next_id = 1

    def seed(self, role: RoleRead, user_count: int = 0) -> None:
        self.roles[role.id] = role
        self.user_counts[role.id] = user_count
        self._next_id = max(self._next_id, role.id + 1)

    async def get_by_id(self, id: int) -> RoleRead | None:
        return self.roles.get(id)

    async def list_page(self, limit: int, offset: int) -> tuple[list[RoleRead], int]:
        all_roles = list(self.roles.values())
        return all_roles[offset : offset + limit], len(all_roles)

    async def find_by_name(self, name: str) -> RoleRead | None:
        for r in self.roles.values():
            if r.name == name:
                return r
        return None

    async def create(self, *, name: str, is_system: bool, permission_ids: list[int]) -> RoleRead:
        perms = [p for p in _CATALOG if p.id in permission_ids]
        created = RoleRead(id=self._next_id, name=name, is_system=is_system, permissions=perms)
        self.roles[created.id] = created
        self.user_counts[created.id] = 0
        self._next_id += 1
        return created

    async def update(
        self, id: int, *, name: str | None = None, permission_ids: list[int] | None = None
    ) -> RoleRead | None:
        current = self.roles.get(id)
        if current is None:
            return None
        new_name = current.name if name is None else name
        new_perms = (
            current.permissions
            if permission_ids is None
            else [p for p in _CATALOG if p.id in permission_ids]
        )
        updated = RoleRead(
            id=current.id, name=new_name, is_system=current.is_system, permissions=new_perms
        )
        self.roles[id] = updated
        return updated

    async def delete(self, id: int) -> None:
        self.roles.pop(id, None)

    async def count_users_with_role(self, role_id: int) -> int:
        return self.user_counts.get(role_id, 0)


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
    grants[user_id] = {role_id} round-trips correctly through get_roles_for_user."""

    def __init__(self, roles: "FakeRoleRepository") -> None:
        self._roles = roles
        self.grants: dict[int, set[int]] = {}  # user_id -> set of role_ids

    async def get_roles_for_user(self, user_id: int) -> list[RoleRead]:
        role_ids = self.grants.get(user_id, set())
        roles = []
        for rid in role_ids:
            role = await self._roles.get_by_id(rid)
            if role is not None:
                roles.append(role)
        return roles

    async def get_role_for_user(self, user_id: int) -> RoleRead | None:
        roles = await self.get_roles_for_user(user_id)
        return roles[0] if roles else None

    async def get_roles_for_users(self, user_ids: list[int]) -> dict[int, list[str]]:
        result: dict[int, list[str]] = {uid: [] for uid in user_ids}
        for uid in user_ids:
            role_ids = self.grants.get(uid, set())
            for rid in role_ids:
                role = await self._roles.get_by_id(rid)
                if role:
                    result[uid].append(role.name)
        return result

    async def assign_roles(self, user_id: int, role_ids: set[int] | list[int]) -> None:
        self.grants[user_id] = set(role_ids)

    async def assign(self, user_id: int, role_id: int) -> None:
        self.grants[user_id] = {role_id}

    async def user_has_permission(self, user_id: int, resource: str, action: str) -> bool:
        roles = await self.get_roles_for_user(user_id)
        for role in roles:
            if any(p.resource == resource and p.action == action for p in role.permissions):
                return True
        return False


class FakeRbacUnitOfWork(AbstractRbacUnitOfWork):
    def __init__(self) -> None:
        self.roles: FakeRoleRepository = FakeRoleRepository()
        self.permissions: FakePermissionRepository = FakePermissionRepository()
        self.user_roles: FakeUserRoleRepository = FakeUserRoleRepository(self.roles)
        self.commits = 0
        self.stale: list[tuple[str, int]] = []

    def mark_stale(self, entity: str, entity_id: int) -> None:
        self.stale.append((entity, entity_id))

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        pass


def _admin_role(user_count: int = 1) -> RoleRead:
    return RoleRead(id=10, name=RbacDefaults.ADMIN_ROLE_NAME, is_system=True, permissions=[])


async def _not_protected(user_id: int) -> bool:
    return False


class TestCreateRole:
    async def test_creates_a_custom_role_with_permissions(self) -> None:
        uow = FakeRbacUnitOfWork()
        role = await CreateRole(uow).execute("support", [1, 2])

        assert role.name == "support"
        assert not role.is_system
        assert {p.id for p in role.permissions} == {1, 2}
        assert uow.commits == 1

    async def test_rejects_duplicate_role_name(self) -> None:
        uow = FakeRbacUnitOfWork()
        uow.roles.seed(RoleRead(id=1, name="support", is_system=False, permissions=[]))

        with pytest.raises(DuplicateRoleName):
            await CreateRole(uow).execute("support", [])

    async def test_rejects_unknown_permission_ids(self) -> None:
        uow = FakeRbacUnitOfWork()

        with pytest.raises(UnknownPermissionId):
            await CreateRole(uow).execute("support", [999])


class TestUpdateRole:
    async def test_renames_a_custom_role(self) -> None:
        uow = FakeRbacUnitOfWork()
        uow.roles.seed(RoleRead(id=1, name="support", is_system=False, permissions=[]))

        updated = await UpdateRole(uow).execute(1, name="support-tier-2", permission_ids=None)
        assert updated.name == "support-tier-2"

    async def test_updates_custom_role_permissions(self) -> None:
        uow = FakeRbacUnitOfWork()
        uow.roles.seed(RoleRead(id=1, name="support", is_system=False, permissions=[]))

        updated = await UpdateRole(uow).execute(1, name=None, permission_ids=[1, 2])
        assert {p.id for p in updated.permissions} == {1, 2}

    async def test_allows_updating_system_role_permissions(self) -> None:
        uow = FakeRbacUnitOfWork()
        member = RoleRead(id=3, name=RbacDefaults.MEMBER_ROLE_NAME, is_system=True, permissions=[])
        uow.roles.seed(member)

        updated = await UpdateRole(uow).execute(3, name=None, permission_ids=[1])
        assert {p.id for p in updated.permissions} == {1}

    async def test_rejects_updating_admin_role_permissions(self) -> None:
        uow = FakeRbacUnitOfWork()
        uow.roles.seed(_admin_role())

        with pytest.raises(SystemRoleImmutable):
            await UpdateRole(uow).execute(10, name=None, permission_ids=[1])

    async def test_rejects_renaming_a_system_role(self) -> None:
        uow = FakeRbacUnitOfWork()
        uow.roles.seed(_admin_role())

        with pytest.raises(SystemRoleImmutable):
            await UpdateRole(uow).execute(10, name="superadmin", permission_ids=None)

    async def test_rejects_renaming_to_an_existing_role_name(self) -> None:
        uow = FakeRbacUnitOfWork()
        uow.roles.seed(RoleRead(id=1, name="support", is_system=False, permissions=[]))
        uow.roles.seed(RoleRead(id=2, name="billing", is_system=False, permissions=[]))

        with pytest.raises(DuplicateRoleName):
            await UpdateRole(uow).execute(1, name="billing", permission_ids=None)


class TestDeleteRole:
    async def test_deletes_a_custom_role_with_no_users(self) -> None:
        uow = FakeRbacUnitOfWork()
        uow.roles.seed(RoleRead(id=1, name="support", is_system=False, permissions=[]), user_count=0)

        await DeleteRole(uow).execute(1)

        assert await uow.roles.get_by_id(1) is None

    async def test_rejects_deleting_a_system_role(self) -> None:
        uow = FakeRbacUnitOfWork()
        uow.roles.seed(_admin_role(user_count=1))

        with pytest.raises(SystemRoleImmutable):
            await DeleteRole(uow).execute(10)

    async def test_rejects_deleting_a_role_still_in_use(self) -> None:
        uow = FakeRbacUnitOfWork()
        uow.roles.seed(RoleRead(id=1, name="support", is_system=False, permissions=[]), user_count=2)

        with pytest.raises(RoleInUse):
            await DeleteRole(uow).execute(1)


class TestAssignRole:
    async def test_assigns_role_to_an_existing_user(self) -> None:
        uow = FakeRbacUnitOfWork()
        uow.roles.seed(RoleRead(id=1, name="support", is_system=False, permissions=[]))

        async def user_lookup(user_id: int):
            return object()

        await AssignRole(uow, user_lookup, _not_protected).execute(42, 1)

        assert uow.user_roles.grants[42] == {1}

    async def test_rejects_unknown_user(self) -> None:
        uow = FakeRbacUnitOfWork()
        uow.roles.seed(RoleRead(id=1, name="support", is_system=False, permissions=[]))

        async def user_lookup(user_id: int):
            return None

        with pytest.raises(TargetUserNotFound):
            await AssignRole(uow, user_lookup, _not_protected).execute(42, 1)

    async def test_rejects_reassigning_the_last_admin_away(self) -> None:
        uow = FakeRbacUnitOfWork()
        admin = _admin_role(user_count=1)
        uow.roles.seed(admin, user_count=1)
        uow.roles.seed(RoleRead(id=1, name="support", is_system=False, permissions=[]))
        uow.user_roles.grants[42] = {10}

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


class TestAssignRoles:
    async def test_assigns_multiple_roles_to_an_existing_user(self) -> None:
        uow = FakeRbacUnitOfWork()
        uow.roles.seed(RoleRead(id=1, name="support", is_system=False, permissions=[]))
        uow.roles.seed(RoleRead(id=2, name="developer", is_system=False, permissions=[]))

        async def user_lookup(user_id: int):
            return object()

        await AssignRoles(uow, user_lookup, _not_protected).execute(42, [1, 2])

        assert uow.user_roles.grants[42] == {1, 2}

    async def test_rejects_removing_last_admin(self) -> None:
        uow = FakeRbacUnitOfWork()
        admin = _admin_role(user_count=1)
        uow.roles.seed(admin, user_count=1)
        uow.roles.seed(RoleRead(id=1, name="support", is_system=False, permissions=[]))
        uow.user_roles.grants[42] = {10}

        async def user_lookup(user_id: int):
            return object()

        with pytest.raises(CannotRemoveLastAdmin):
            await AssignRoles(uow, user_lookup, _not_protected).execute(42, [1])

    async def test_allows_adding_role_to_last_admin(self) -> None:
        uow = FakeRbacUnitOfWork()
        admin = _admin_role(user_count=1)
        uow.roles.seed(admin, user_count=1)
        uow.roles.seed(RoleRead(id=1, name="support", is_system=False, permissions=[]))
        uow.user_roles.grants[42] = {10}

        async def user_lookup(user_id: int):
            return object()

        await AssignRoles(uow, user_lookup, _not_protected).execute(42, [10, 1])
        assert uow.user_roles.grants[42] == {10, 1}

    async def test_rejects_modifying_protected_admin_without_admin_role(self) -> None:
        uow = FakeRbacUnitOfWork()
        admin = _admin_role(user_count=1)
        uow.roles.seed(admin, user_count=1)
        uow.roles.seed(RoleRead(id=1, name="support", is_system=False, permissions=[]))
        uow.user_roles.grants[42] = {10}

        async def user_lookup(user_id: int):
            return object()

        async def is_protected(user_id: int) -> bool:
            return True

        with pytest.raises(CannotModifyProtectedAdmin):
            await AssignRoles(uow, user_lookup, is_protected).execute(42, [1])


class TestAssignDefaultRole:
    async def test_grants_the_seeded_member_role(self) -> None:
        uow = FakeRbacUnitOfWork()
        member = RoleRead(id=3, name=RbacDefaults.MEMBER_ROLE_NAME, is_system=True, permissions=[])
        uow.roles.seed(member)

        await AssignDefaultRole(uow).execute(99)

        assert uow.user_roles.grants[99] == {3}
