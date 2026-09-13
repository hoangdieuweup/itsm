"""Unit tests for the rbac module's use cases. No database — every collaborator
is a fake implementing the module's own Abstract* contract."""

from uuid import UUID, uuid4

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

_PERM_1 = uuid4()
_PERM_2 = uuid4()
_PERM_3 = uuid4()
_PERM_4 = uuid4()
_PERM_5 = uuid4()
_PERM_6 = uuid4()
_PERM_7 = uuid4()
_PERM_8 = uuid4()

_CATALOG = [
    PermissionRead(id=_PERM_1, resource="role", action="create", description_key="permissions.role.create"),
    PermissionRead(id=_PERM_2, resource="role", action="read", description_key="permissions.role.read"),
    PermissionRead(id=_PERM_3, resource="role", action="update", description_key="permissions.role.update"),
    PermissionRead(id=_PERM_4, resource="role", action="delete", description_key="permissions.role.delete"),
    PermissionRead(
        id=_PERM_5, resource="permission", action="read", description_key="permissions.permission.read"
    ),
    PermissionRead(id=_PERM_6, resource="user", action="read", description_key="permissions.user.read"),
    PermissionRead(
        id=_PERM_7, resource="user", action="update_status", description_key="permissions.user.update_status"
    ),
    PermissionRead(
        id=_PERM_8, resource="user", action="assign_role", description_key="permissions.user.assign_role"
    ),
]


class FakeRoleRepository(AbstractRoleRepository):
    def __init__(self) -> None:
        self.roles: dict[UUID, RoleRead] = {}
        self.user_counts: dict[UUID, int] = {}

    def seed(self, role: RoleRead, user_count: int = 0) -> None:
        self.roles[role.id] = role
        self.user_counts[role.id] = user_count

    async def get_by_id(self, id: UUID) -> RoleRead | None:
        return self.roles.get(id)

    async def list_page(self, limit: int, offset: int) -> tuple[list[RoleRead], int]:
        all_roles = list(self.roles.values())
        return all_roles[offset : offset + limit], len(all_roles)

    async def find_by_name(self, name: str) -> RoleRead | None:
        for r in self.roles.values():
            if r.name == name:
                return r
        return None

    async def create(self, *, name: str, is_system: bool, permission_ids: list[UUID]) -> RoleRead:
        perms = [p for p in _CATALOG if p.id in permission_ids]
        created = RoleRead(id=uuid4(), name=name, is_system=is_system, permissions=perms)
        self.roles[created.id] = created
        self.user_counts[created.id] = 0
        return created

    async def update(
        self, id: UUID, *, name: str | None = None, permission_ids: list[UUID] | None = None
    ) -> RoleRead | None:
        current = self.roles.get(id)
        if current is None:
            return None
        new_name = current.name if name is None else name
        new_perms = (
            current.permissions if permission_ids is None else [p for p in _CATALOG if p.id in permission_ids]
        )
        updated = RoleRead(id=current.id, name=new_name, is_system=current.is_system, permissions=new_perms)
        self.roles[id] = updated
        return updated

    async def delete(self, id: UUID) -> None:
        self.roles.pop(id, None)

    async def count_users_with_role(self, role_id: UUID) -> int:
        return self.user_counts.get(role_id, 0)


class FakePermissionRepository(AbstractPermissionRepository):
    async def get_by_id(self, entity_id: UUID) -> PermissionRead | None:
        return next((p for p in _CATALOG if p.id == entity_id), None)

    async def list_page(self, limit: int, offset: int) -> tuple[list[PermissionRead], int]:
        return _CATALOG[offset : offset + limit], len(_CATALOG)

    async def list_all(self) -> list[PermissionRead]:
        return list(_CATALOG)

    async def find_by_ids(self, ids: list[UUID]) -> list[PermissionRead]:
        return [p for p in _CATALOG if p.id in ids]


class FakeUserRoleRepository(AbstractUserRoleRepository):
    """Resolves grants through the same FakeRoleRepository the uow already
    holds, so a role seeded via uow.roles.seed() and then granted via
    grants[user_id] = {role_id} round-trips correctly through get_roles_for_user."""

    def __init__(self, roles: "FakeRoleRepository") -> None:
        self._roles = roles
        self.grants: dict[UUID, set[UUID]] = {}  # user_id -> set of role_ids

    async def get_roles_for_user(self, user_id: UUID) -> list[RoleRead]:
        role_ids = self.grants.get(user_id, set())
        roles = []
        for rid in role_ids:
            role = await self._roles.get_by_id(rid)
            if role is not None:
                roles.append(role)
        return roles

    async def get_role_for_user(self, user_id: UUID) -> RoleRead | None:
        roles = await self.get_roles_for_user(user_id)
        return roles[0] if roles else None

    async def get_roles_for_users(self, user_ids: list[UUID]) -> dict[UUID, list[str]]:
        result: dict[UUID, list[str]] = {uid: [] for uid in user_ids}
        for uid in user_ids:
            role_ids = self.grants.get(uid, set())
            for rid in role_ids:
                role = await self._roles.get_by_id(rid)
                if role:
                    result[uid].append(role.name)
        return result

    async def assign_roles(self, user_id: UUID, role_ids: set[UUID] | list[UUID]) -> None:
        self.grants[user_id] = set(role_ids)

    async def assign(self, user_id: UUID, role_id: UUID) -> None:
        self.grants[user_id] = {role_id}

    async def user_has_permission(self, user_id: UUID, resource: str, action: str) -> bool:
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
        self.stale: list[tuple[str, UUID | int | str]] = []

    def mark_stale(self, entity: str, entity_id: UUID | int | str) -> None:
        self.stale.append((entity, entity_id))

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        pass


def _admin_role(user_count: int = 1) -> RoleRead:
    return RoleRead(id=uuid4(), name=RbacDefaults.ADMIN_ROLE_NAME, is_system=True, permissions=[])


async def _not_protected(user_id: UUID) -> bool:
    return False


class TestCreateRole:
    async def test_creates_a_custom_role_with_permissions(self) -> None:
        uow = FakeRbacUnitOfWork()
        role = await CreateRole(uow).execute("support", [_PERM_1, _PERM_2])

        assert role.name == "support"
        assert not role.is_system
        assert {p.id for p in role.permissions} == {_PERM_1, _PERM_2}
        assert uow.commits == 1

    async def test_rejects_duplicate_role_name(self) -> None:
        uow = FakeRbacUnitOfWork()
        uow.roles.seed(RoleRead(id=uuid4(), name="support", is_system=False, permissions=[]))

        with pytest.raises(DuplicateRoleName):
            await CreateRole(uow).execute("support", [])

    async def test_rejects_unknown_permission_ids(self) -> None:
        uow = FakeRbacUnitOfWork()

        with pytest.raises(UnknownPermissionId):
            await CreateRole(uow).execute("support", [uuid4()])


class TestUpdateRole:
    async def test_renames_a_custom_role(self) -> None:
        uow = FakeRbacUnitOfWork()
        role_id = uuid4()
        uow.roles.seed(RoleRead(id=role_id, name="support", is_system=False, permissions=[]))

        updated = await UpdateRole(uow).execute(role_id, name="support-tier-2", permission_ids=None)
        assert updated.name == "support-tier-2"

    async def test_updates_custom_role_permissions(self) -> None:
        uow = FakeRbacUnitOfWork()
        role_id = uuid4()
        uow.roles.seed(RoleRead(id=role_id, name="support", is_system=False, permissions=[]))

        updated = await UpdateRole(uow).execute(role_id, name=None, permission_ids=[_PERM_1, _PERM_2])
        assert {p.id for p in updated.permissions} == {_PERM_1, _PERM_2}

    async def test_allows_updating_system_role_permissions(self) -> None:
        uow = FakeRbacUnitOfWork()
        member_id = uuid4()
        member = RoleRead(id=member_id, name=RbacDefaults.MEMBER_ROLE_NAME, is_system=True, permissions=[])
        uow.roles.seed(member)

        updated = await UpdateRole(uow).execute(member_id, name=None, permission_ids=[_PERM_1])
        assert {p.id for p in updated.permissions} == {_PERM_1}

    async def test_rejects_updating_admin_role_permissions(self) -> None:
        uow = FakeRbacUnitOfWork()
        admin = _admin_role()
        uow.roles.seed(admin)

        with pytest.raises(SystemRoleImmutable):
            await UpdateRole(uow).execute(admin.id, name=None, permission_ids=[_PERM_1])

    async def test_rejects_renaming_a_system_role(self) -> None:
        uow = FakeRbacUnitOfWork()
        admin = _admin_role()
        uow.roles.seed(admin)

        with pytest.raises(SystemRoleImmutable):
            await UpdateRole(uow).execute(admin.id, name="superadmin", permission_ids=None)

    async def test_rejects_renaming_to_an_existing_role_name(self) -> None:
        uow = FakeRbacUnitOfWork()
        role1_id = uuid4()
        role2_id = uuid4()
        uow.roles.seed(RoleRead(id=role1_id, name="support", is_system=False, permissions=[]))
        uow.roles.seed(RoleRead(id=role2_id, name="billing", is_system=False, permissions=[]))

        with pytest.raises(DuplicateRoleName):
            await UpdateRole(uow).execute(role1_id, name="billing", permission_ids=None)


class TestDeleteRole:
    async def test_deletes_a_custom_role_with_no_users(self) -> None:
        uow = FakeRbacUnitOfWork()
        role_id = uuid4()
        uow.roles.seed(RoleRead(id=role_id, name="support", is_system=False, permissions=[]), user_count=0)

        await DeleteRole(uow).execute(role_id)

        assert await uow.roles.get_by_id(role_id) is None

    async def test_rejects_deleting_a_system_role(self) -> None:
        uow = FakeRbacUnitOfWork()
        admin = _admin_role(user_count=1)
        uow.roles.seed(admin)

        with pytest.raises(SystemRoleImmutable):
            await DeleteRole(uow).execute(admin.id)

    async def test_rejects_deleting_a_role_still_in_use(self) -> None:
        uow = FakeRbacUnitOfWork()
        role_id = uuid4()
        uow.roles.seed(RoleRead(id=role_id, name="support", is_system=False, permissions=[]), user_count=2)

        with pytest.raises(RoleInUse):
            await DeleteRole(uow).execute(role_id)


class TestAssignRole:
    async def test_assigns_role_to_an_existing_user(self) -> None:
        uow = FakeRbacUnitOfWork()
        user_id = uuid4()
        role_id = uuid4()
        uow.roles.seed(RoleRead(id=role_id, name="support", is_system=False, permissions=[]))

        async def user_lookup(uid: UUID):
            return object()

        await AssignRole(uow, user_lookup, _not_protected).execute(user_id, role_id)

        assert uow.user_roles.grants[user_id] == {role_id}

    async def test_rejects_unknown_user(self) -> None:
        uow = FakeRbacUnitOfWork()
        user_id = uuid4()
        role_id = uuid4()
        uow.roles.seed(RoleRead(id=role_id, name="support", is_system=False, permissions=[]))

        async def user_lookup(uid: UUID):
            return None

        with pytest.raises(TargetUserNotFound):
            await AssignRole(uow, user_lookup, _not_protected).execute(user_id, role_id)

    async def test_rejects_reassigning_the_last_admin_away(self) -> None:
        uow = FakeRbacUnitOfWork()
        user_id = uuid4()
        admin = _admin_role(user_count=1)
        uow.roles.seed(admin, user_count=1)
        role_id = uuid4()
        uow.roles.seed(RoleRead(id=role_id, name="support", is_system=False, permissions=[]))
        uow.user_roles.grants[user_id] = {admin.id}

        async def user_lookup(uid: UUID):
            return object()

        with pytest.raises(CannotRemoveLastAdmin):
            await AssignRole(uow, user_lookup, _not_protected).execute(user_id, role_id)

    async def test_missing_target_role_raises(self) -> None:
        uow = FakeRbacUnitOfWork()
        user_id = uuid4()

        async def user_lookup(uid: UUID):
            return object()

        with pytest.raises(RoleNotFound):
            await AssignRole(uow, user_lookup, _not_protected).execute(user_id, uuid4())

    async def test_rejects_modifying_a_protected_admin(self) -> None:
        uow = FakeRbacUnitOfWork()
        user_id = uuid4()
        role_id = uuid4()
        uow.roles.seed(RoleRead(id=role_id, name="support", is_system=False, permissions=[]))

        async def user_lookup(uid: UUID):
            return object()

        async def is_protected(uid: UUID) -> bool:
            return True

        with pytest.raises(CannotModifyProtectedAdmin):
            await AssignRole(uow, user_lookup, is_protected).execute(user_id, role_id)

        assert user_id not in uow.user_roles.grants


class TestAssignRoles:
    async def test_assigns_multiple_roles_to_an_existing_user(self) -> None:
        uow = FakeRbacUnitOfWork()
        user_id = uuid4()
        role1_id = uuid4()
        role2_id = uuid4()
        uow.roles.seed(RoleRead(id=role1_id, name="support", is_system=False, permissions=[]))
        uow.roles.seed(RoleRead(id=role2_id, name="developer", is_system=False, permissions=[]))

        async def user_lookup(uid: UUID):
            return object()

        await AssignRoles(uow, user_lookup, _not_protected).execute(user_id, [role1_id, role2_id])

        assert uow.user_roles.grants[user_id] == {role1_id, role2_id}

    async def test_rejects_removing_last_admin(self) -> None:
        uow = FakeRbacUnitOfWork()
        user_id = uuid4()
        admin = _admin_role(user_count=1)
        uow.roles.seed(admin, user_count=1)
        role_id = uuid4()
        uow.roles.seed(RoleRead(id=role_id, name="support", is_system=False, permissions=[]))
        uow.user_roles.grants[user_id] = {admin.id}

        async def user_lookup(uid: UUID):
            return object()

        with pytest.raises(CannotRemoveLastAdmin):
            await AssignRoles(uow, user_lookup, _not_protected).execute(user_id, [role_id])

    async def test_allows_adding_role_to_last_admin(self) -> None:
        uow = FakeRbacUnitOfWork()
        user_id = uuid4()
        admin = _admin_role(user_count=1)
        uow.roles.seed(admin, user_count=1)
        role_id = uuid4()
        uow.roles.seed(RoleRead(id=role_id, name="support", is_system=False, permissions=[]))
        uow.user_roles.grants[user_id] = {admin.id}

        async def user_lookup(uid: UUID):
            return object()

        await AssignRoles(uow, user_lookup, _not_protected).execute(user_id, [admin.id, role_id])
        assert uow.user_roles.grants[user_id] == {admin.id, role_id}

    async def test_rejects_modifying_protected_admin_without_admin_role(self) -> None:
        uow = FakeRbacUnitOfWork()
        user_id = uuid4()
        admin = _admin_role(user_count=1)
        uow.roles.seed(admin, user_count=1)
        role_id = uuid4()
        uow.roles.seed(RoleRead(id=role_id, name="support", is_system=False, permissions=[]))
        uow.user_roles.grants[user_id] = {admin.id}

        async def user_lookup(uid: UUID):
            return object()

        async def is_protected(uid: UUID) -> bool:
            return True

        with pytest.raises(CannotModifyProtectedAdmin):
            await AssignRoles(uow, user_lookup, is_protected).execute(user_id, [role_id])


class TestAssignDefaultRole:
    async def test_grants_the_seeded_member_role(self) -> None:
        uow = FakeRbacUnitOfWork()
        user_id = uuid4()
        member_id = uuid4()
        member = RoleRead(id=member_id, name=RbacDefaults.MEMBER_ROLE_NAME, is_system=True, permissions=[])
        uow.roles.seed(member)

        await AssignDefaultRole(uow).execute(user_id)

        assert uow.user_roles.grants[user_id] == {member_id}
