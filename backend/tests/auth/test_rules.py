"""Unit tests for app.auth.rules — pure decisions, no I/O, no fixtures."""

import pytest

from app.modules.auth.constants import UserStatus
from app.modules.auth.rules import AuthRules


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
