"""Unit tests for app.modules.rbac.rules — pure decisions, no I/O, no fixtures."""

import pytest

from app.modules.rbac.rules import RbacRules
from app.modules.rbac.schemas import RoleRead


def _role(*, is_system: bool) -> RoleRead:
    return RoleRead(id=1, name="admin" if is_system else "custom", is_system=is_system, permissions=[])


@pytest.mark.parametrize(("is_system", "expected"), [(True, False), (False, True)])
def test_can_delete_role(is_system: bool, expected: bool) -> None:
    assert RbacRules.can_delete_role(_role(is_system=is_system)) is expected


@pytest.mark.parametrize(("is_system", "expected"), [(True, False), (False, True)])
def test_can_rename_role(is_system: bool, expected: bool) -> None:
    assert RbacRules.can_rename_role(_role(is_system=is_system)) is expected


@pytest.mark.parametrize(
    ("role_name", "remaining_admin_grants", "expected"),
    [
        ("admin", 1, True),  # this is the only admin left — block
        ("admin", 2, False),  # another admin still exists — fine
        ("support", 1, False),  # not the admin role at all — never blocked
        ("member", 0, False),
    ],
)
def test_blocks_last_admin_removal(role_name: str, remaining_admin_grants: int, expected: bool) -> None:
    assert RbacRules.blocks_last_admin_removal(role_name, remaining_admin_grants) is expected
