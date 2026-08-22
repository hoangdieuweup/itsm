"""Unit tests for app.modules.cloudflare.dependencies.require_account_access —
Fake-based, no database. Exercises the closure returned by the factory directly."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.modules.cloudflare.access import resolve_account_access_grant
from app.modules.cloudflare.constants import AccessLevel
from app.modules.cloudflare.dependencies import require_account_access, require_account_access_for_environment
from app.modules.cloudflare.exceptions import CloudflareConfigNotFound, InsufficientAccountAccess
from app.modules.cloudflare.repository import CloudflareAccountManagerRow
from app.modules.users.public import UserRead

# UserRead.model_construct bypasses field validation/required-field checks —
# these tests only ever read .id off the fake user, and model_construct is
# the standard pydantic way to build a test fixture without knowing every
# field UserRead happens to require.
_FAKE_USER = UserRead.model_construct(id=uuid4())


class FakeAuthApi:
    def __init__(self, user) -> None:
        self._user = user

    def current_user(self):
        return self._user


class FakeRbacApi:
    def __init__(self, *, manage_all: bool) -> None:
        self._manage_all = manage_all

    async def has_permission(self, user_id, resource, action) -> bool:
        assert (resource, action) == ("cloudflare_account", "manage_all")
        return self._manage_all


class FakeAccountManagers:
    def __init__(self, row: CloudflareAccountManagerRow | None) -> None:
        self._row = row

    async def get_for_user(self, account_id, user_id):
        return self._row


class FakeUow:
    def __init__(self, manager_row: CloudflareAccountManagerRow | None) -> None:
        self.account_managers = FakeAccountManagers(manager_row)


def _make_uow(manager_row: CloudflareAccountManagerRow | None) -> FakeUow:
    return FakeUow(manager_row)


async def test_manage_all_bypasses_with_held_level_none() -> None:
    check = require_account_access(AccessLevel.OWNER)
    grant = await check(
        account_id=uuid4(),
        auth_api=FakeAuthApi(_FAKE_USER),
        rbac_api=FakeRbacApi(manage_all=True),
        uow=_make_uow(None),
    )
    assert grant.held_level is None


async def test_sufficient_manager_row_passes() -> None:
    account_id = uuid4()
    row = CloudflareAccountManagerRow(
        cloudflare_account_id=account_id,
        user_id=_FAKE_USER.id,
        access_level=AccessLevel.OWNER,
        created_at=datetime.now(UTC),
    )
    check = require_account_access(AccessLevel.EDITOR)
    grant = await check(
        account_id=account_id,
        auth_api=FakeAuthApi(_FAKE_USER),
        rbac_api=FakeRbacApi(manage_all=False),
        uow=_make_uow(row),
    )
    assert grant.held_level is AccessLevel.OWNER


async def test_insufficient_manager_row_raises() -> None:
    account_id = uuid4()
    row = CloudflareAccountManagerRow(
        cloudflare_account_id=account_id,
        user_id=_FAKE_USER.id,
        access_level=AccessLevel.VIEWER,
        created_at=datetime.now(UTC),
    )
    check = require_account_access(AccessLevel.OWNER)
    with pytest.raises(InsufficientAccountAccess):
        await check(
            account_id=account_id,
            auth_api=FakeAuthApi(_FAKE_USER),
            rbac_api=FakeRbacApi(manage_all=False),
            uow=_make_uow(row),
        )


async def test_no_manager_row_and_no_manage_all_raises() -> None:
    check = require_account_access(AccessLevel.VIEWER)
    with pytest.raises(InsufficientAccountAccess):
        await check(
            account_id=uuid4(),
            auth_api=FakeAuthApi(_FAKE_USER),
            rbac_api=FakeRbacApi(manage_all=False),
            uow=_make_uow(None),
        )


class FakeConfigs:
    def __init__(self, cloudflare_account_id) -> None:
        self._account_id = cloudflare_account_id

    async def get_by_environment_id(self, environment_id):
        if self._account_id is None:
            return None

        class _Row:
            cloudflare_account_id = self._account_id

        return _Row()


class FakeUowWithConfigs:
    def __init__(self, manager_row, cloudflare_account_id) -> None:
        self.account_managers = FakeAccountManagers(manager_row)
        self.configs = FakeConfigs(cloudflare_account_id)


async def test_resolve_account_access_grant_is_the_shared_implementation() -> None:
    """Direct-call test for the extracted helper — the regression proof that
    require_account_access's existing behavior didn't change lives in the
    untouched tests above this one in the file (all still exercise
    require_account_access's public signature unchanged)."""
    account_id = uuid4()
    grant = await resolve_account_access_grant(
        account_id, _FAKE_USER, FakeRbacApi(manage_all=True), _make_uow(None), AccessLevel.OWNER
    )
    assert grant.held_level is None


async def test_require_account_access_for_environment_resolves_via_config() -> None:
    account_id = uuid4()
    row = CloudflareAccountManagerRow(
        cloudflare_account_id=account_id,
        user_id=_FAKE_USER.id,
        access_level=AccessLevel.EDITOR,
        created_at=datetime.now(UTC),
    )
    check = require_account_access_for_environment(AccessLevel.EDITOR)

    grant = await check(
        environment_id=uuid4(),
        auth_api=FakeAuthApi(_FAKE_USER),
        rbac_api=FakeRbacApi(manage_all=False),
        uow=FakeUowWithConfigs(row, account_id),
    )

    assert grant.held_level is AccessLevel.EDITOR


async def test_require_account_access_for_environment_raises_when_unbound() -> None:
    check = require_account_access_for_environment(AccessLevel.VIEWER)

    with pytest.raises(CloudflareConfigNotFound):
        await check(
            environment_id=uuid4(),
            auth_api=FakeAuthApi(_FAKE_USER),
            rbac_api=FakeRbacApi(manage_all=False),
            uow=FakeUowWithConfigs(None, None),
        )
