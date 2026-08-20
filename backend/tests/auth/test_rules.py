"""Unit tests for app.auth.rules — pure decisions, no I/O, no fixtures."""

import pytest

from app.auth.constants import UserRole, UserStatus
from app.auth.rules import AuthRules


@pytest.mark.parametrize(
    ("external_role_code", "expected"),
    [
        ("director", UserRole.OWNER),
        ("manager", UserRole.ADMIN),
        ("employee", UserRole.MEMBER),
        (None, UserRole.MEMBER),
        ("unknown-role", UserRole.MEMBER),
    ],
)
def test_resolve_role(external_role_code: str | None, expected: UserRole) -> None:
    """DX role codes map to app roles; anything unrecognized falls back to the least privileged role."""
    assert AuthRules.resolve_role(external_role_code) is expected


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (UserStatus.ACTIVE, True),
        (UserStatus.PENDING, True),
        (UserStatus.BLOCKED, False),
    ],
)
def test_can_login(status: UserStatus, expected: bool) -> None:
    """Only a blocked user is denied login; every other status is allowed through."""
    assert AuthRules.can_login(status) is expected
