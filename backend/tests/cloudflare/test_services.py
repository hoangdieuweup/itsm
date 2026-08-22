"""Unit tests for app.modules.cloudflare.services — Fake-based, no database,
no real Cloudflare API calls."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.core.crypto import FernetCodec
from app.modules.cloudflare.constants import AccessLevel, CloudflareAccountAuditActions
from app.modules.cloudflare.exceptions import CloudflareAccountNotFound, InsufficientAccountAccess
from app.modules.cloudflare.exceptions import CloudflareApiUnavailable as CfUnavailable
from app.modules.cloudflare.exceptions import InvalidCloudflareToken
from app.modules.cloudflare.repository import (
    AbstractCloudflareAccountManagerRepository,
    AbstractCloudflareAccountRepository,
    CloudflareAccountManagerRow,
)
from app.modules.cloudflare.schemas import AccountAccessGrant, CloudflareAccountRead
from app.modules.cloudflare.services.create_account import CreateCloudflareAccount
from app.modules.cloudflare.services.assign_manager import AssignCloudflareAccountManager
from app.modules.cloudflare.services.delete_account import DeleteCloudflareAccount
from app.modules.cloudflare.services.list_account_managers import ListCloudflareAccountManagers
from app.modules.cloudflare.services.reveal_token import RevealCloudflareAccountToken
from app.modules.cloudflare.services.test_connection import TestCloudflareAccountConnection
from app.modules.cloudflare.services.update_account import UpdateCloudflareAccount
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork


class FakeCloudflareAccountRepository(AbstractCloudflareAccountRepository):
    def __init__(self) -> None:
        self._rows: dict[UUID, CloudflareAccountRead] = {}
        self._ciphertexts: dict[UUID, str] = {}

    async def get_by_id(self, entity_id: UUID) -> CloudflareAccountRead | None:
        return self._rows.get(entity_id)

    async def list_page(self, limit: int, offset: int) -> tuple[list[CloudflareAccountRead], int]:
        items = list(self._rows.values())[offset : offset + limit]
        return items, len(self._rows)

    async def list_for_ids(self, account_ids: list[UUID]) -> list[CloudflareAccountRead]:
        return [self._rows[i] for i in account_ids if i in self._rows]

    async def create(
        self, *, label: str, cf_account_id: str, api_token: str, created_by: UUID | None
    ) -> CloudflareAccountRead:
        account = CloudflareAccountRead(
            id=uuid4(),
            label=label,
            cf_account_id=cf_account_id,
            created_by=created_by,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self._rows[account.id] = account
        self._ciphertexts[account.id] = api_token
        return account

    async def update(
        self, account_id: UUID, *, label: str | None, api_token: str | None
    ) -> CloudflareAccountRead:
        existing = self._rows[account_id]
        updated = existing.model_copy(update={"label": label if label is not None else existing.label})
        self._rows[account_id] = updated
        if api_token is not None:
            self._ciphertexts[account_id] = api_token
        return updated

    async def delete(self, account_id: UUID) -> None:
        self._rows.pop(account_id, None)
        self._ciphertexts.pop(account_id, None)

    async def get_token_ciphertext(self, account_id: UUID) -> str | None:
        return self._ciphertexts.get(account_id)


class FakeCloudflareAccountManagerRepository(AbstractCloudflareAccountManagerRepository):
    def __init__(self) -> None:
        self._rows: dict[tuple[UUID, UUID], CloudflareAccountManagerRow] = {}

    async def get_by_id(self, entity_id: tuple) -> CloudflareAccountManagerRow | None:
        return self._rows.get(entity_id)

    async def list_page(self, limit: int, offset: int) -> tuple[list[CloudflareAccountManagerRow], int]:
        items = list(self._rows.values())[offset : offset + limit]
        return items, len(self._rows)

    async def get_for_user(self, account_id: UUID, user_id: UUID) -> CloudflareAccountManagerRow | None:
        return self._rows.get((account_id, user_id))

    async def list_for_account(self, account_id: UUID) -> list[CloudflareAccountManagerRow]:
        return [r for (aid, _), r in self._rows.items() if aid == account_id]

    async def list_for_user(self, user_id: UUID) -> list[CloudflareAccountManagerRow]:
        return [r for (_, uid), r in self._rows.items() if uid == user_id]

    async def count_owners(self, account_id: UUID) -> int:
        return sum(
            1
            for (aid, _), r in self._rows.items()
            if aid == account_id and r.access_level == AccessLevel.OWNER
        )

    async def upsert(
        self, account_id: UUID, user_id: UUID, access_level: AccessLevel
    ) -> CloudflareAccountManagerRow:
        row = CloudflareAccountManagerRow(
            cloudflare_account_id=account_id,
            user_id=user_id,
            access_level=access_level,
            created_at=datetime.now(UTC),
        )
        self._rows[(account_id, user_id)] = row
        return row

    async def remove(self, account_id: UUID, user_id: UUID) -> None:
        self._rows.pop((account_id, user_id), None)


class FakeCloudflareUnitOfWork(AbstractCloudflareUnitOfWork):
    """In-memory unit of work. commit/rollback are no-ops that just count calls."""

    def __init__(self) -> None:
        self.accounts = FakeCloudflareAccountRepository()
        self.account_managers = FakeCloudflareAccountManagerRepository()
        self.commits = 0
        self.rollbacks = 0
        self.stale: list[tuple[str, UUID]] = []

    def mark_stale(self, entity: str, entity_id: UUID) -> None:
        self.stale.append((entity, entity_id))

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class FakeCloudflareClient:
    """Duck-typed stand-in for CloudflareClient — configurable to raise or succeed."""

    def __init__(self, raises: Exception | None = None) -> None:
        self._raises = raises
        self.calls: list[tuple[str, str]] = []

    async def test_connection(self, *, cf_account_id: str, api_token: str) -> None:
        self.calls.append((cf_account_id, api_token))
        if self._raises is not None:
            raise self._raises


class FakeAuditApi:
    """Duck-typed stand-in for app.modules.audit.public.AuditApi — records every
    call instead of writing to Mongo, so tests can assert an event was logged."""

    def __init__(self) -> None:
        self.events: list[dict] = []

    async def log_event(self, **kwargs) -> None:
        self.events.append(kwargs)

    async def list_logs(self, **kwargs) -> tuple[list, int]:
        return [], 0


ACTOR_ID = uuid4()
ACTOR_EMAIL = "actor@example.com"
TEST_FERNET_KEY = "kL8Zx3vQ9mN2pR7wT4yU6bC1dF5gH0jK3lM6nO9pQ2s="


@pytest.fixture(autouse=True)
def _cloudflare_fernet_key(monkeypatch) -> None:
    """Every test in this file that encrypts/decrypts a token needs a real
    32-byte Fernet key — the module's own default is "" (fail-fast, per
    CloudflareConfig's docstring convention), which Fernet() rejects outright."""
    from app.modules.cloudflare.config import cloudflare_settings

    monkeypatch.setattr(cloudflare_settings, "FERNET_KEY", TEST_FERNET_KEY)


class TestCreateCloudflareAccount:
    async def test_creates_account_and_assigns_creator_as_owner(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        client = FakeCloudflareClient()
        audit_api = FakeAuditApi()

        account = await CreateCloudflareAccount(uow, client, audit_api).execute(
            "CF - Customer A", "cf-acc-1", "real-token", actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
        )

        assert account.label == "CF - Customer A"
        manager = await uow.account_managers.get_for_user(account.id, ACTOR_ID)
        assert manager is not None
        assert manager.access_level is AccessLevel.OWNER
        assert client.calls == [("cf-acc-1", "real-token")]
        assert uow.commits == 1
        assert audit_api.events[0]["action"] == CloudflareAccountAuditActions.ACCOUNT_CREATED

    async def test_stores_token_as_ciphertext_not_plaintext(self) -> None:
        uow = FakeCloudflareUnitOfWork()

        account = await CreateCloudflareAccount(uow, FakeCloudflareClient(), FakeAuditApi()).execute(
            "CF - Customer A", "cf-acc-1", "super-secret-token", actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
        )

        stored = await uow.accounts.get_token_ciphertext(account.id)
        assert stored != "super-secret-token"

    async def test_rejects_bad_token_before_persisting_anything(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        client = FakeCloudflareClient(raises=InvalidCloudflareToken())

        with pytest.raises(InvalidCloudflareToken):
            await CreateCloudflareAccount(uow, client, FakeAuditApi()).execute(
                "CF - Bad", "cf-acc-2", "bad-token", actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
            )

        assert uow.commits == 0
        items, total = await uow.accounts.list_page(50, 0)
        assert total == 0

    async def test_rejects_unreachable_cloudflare_before_persisting_anything(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        client = FakeCloudflareClient(raises=CfUnavailable())

        with pytest.raises(CfUnavailable):
            await CreateCloudflareAccount(uow, client, FakeAuditApi()).execute(
                "CF - Down", "cf-acc-3", "x", actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
            )

        assert uow.commits == 0


def _grant(held_level: AccessLevel | None) -> AccountAccessGrant:
    from app.modules.users.public import UserRead

    return AccountAccessGrant(user=UserRead.model_construct(id=ACTOR_ID), held_level=held_level)


class TestUpdateCloudflareAccount:
    async def test_editor_can_rename_label(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="Old", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )

        updated = await UpdateCloudflareAccount(uow, FakeCloudflareClient(), FakeAuditApi()).execute(
            account.id,
            label="New",
            api_token=None,
            grant=_grant(AccessLevel.EDITOR),
            actor_email=ACTOR_EMAIL,
        )

        assert updated.label == "New"
        assert uow.commits == 1

    async def test_editor_cannot_rotate_token(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="Old", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )

        with pytest.raises(InsufficientAccountAccess):
            await UpdateCloudflareAccount(uow, FakeCloudflareClient(), FakeAuditApi()).execute(
                account.id,
                label=None,
                api_token="new-token",
                grant=_grant(AccessLevel.EDITOR),
                actor_email=ACTOR_EMAIL,
            )

        assert uow.commits == 0

    async def test_owner_can_rotate_token(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="Old", cf_account_id="cf-1", api_token="old-ciphertext", created_by=ACTOR_ID
        )
        client = FakeCloudflareClient()

        await UpdateCloudflareAccount(uow, client, FakeAuditApi()).execute(
            account.id,
            label=None,
            api_token="new-plaintext-token",
            grant=_grant(AccessLevel.OWNER),
            actor_email=ACTOR_EMAIL,
        )

        assert client.calls == [("cf-1", "new-plaintext-token")]
        stored = await uow.accounts.get_token_ciphertext(account.id)
        assert stored != "new-plaintext-token"
        assert stored != "old-ciphertext"

    async def test_manage_all_bypass_can_rotate_token(self) -> None:
        """held_level=None (manage_all bypass) satisfies OWNER too."""
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="Old", cf_account_id="cf-1", api_token="old-ciphertext", created_by=ACTOR_ID
        )

        await UpdateCloudflareAccount(uow, FakeCloudflareClient(), FakeAuditApi()).execute(
            account.id,
            label=None,
            api_token="rotated",
            grant=_grant(None),
            actor_email=ACTOR_EMAIL,
        )

        assert uow.commits == 1

    async def test_rejects_bad_rotated_token_before_persisting(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="Old", cf_account_id="cf-1", api_token="old-ciphertext", created_by=ACTOR_ID
        )
        client = FakeCloudflareClient(raises=InvalidCloudflareToken())

        with pytest.raises(InvalidCloudflareToken):
            await UpdateCloudflareAccount(uow, client, FakeAuditApi()).execute(
                account.id,
                label=None,
                api_token="bad-token",
                grant=_grant(AccessLevel.OWNER),
                actor_email=ACTOR_EMAIL,
            )

        assert uow.commits == 0
        stored = await uow.accounts.get_token_ciphertext(account.id)
        assert stored == "old-ciphertext"

    async def test_rejects_unknown_account(self) -> None:
        uow = FakeCloudflareUnitOfWork()

        with pytest.raises(CloudflareAccountNotFound):
            await UpdateCloudflareAccount(uow, FakeCloudflareClient(), FakeAuditApi()).execute(
                uuid4(), label="X", api_token=None, grant=_grant(AccessLevel.OWNER), actor_email=ACTOR_EMAIL
            )


class TestDeleteCloudflareAccount:
    async def test_deletes_account(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="Gone", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )

        await DeleteCloudflareAccount(uow, FakeAuditApi()).execute(
            account.id, actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
        )

        assert await uow.accounts.get_by_id(account.id) is None
        assert uow.commits == 1

    async def test_rejects_unknown_account(self) -> None:
        uow = FakeCloudflareUnitOfWork()

        with pytest.raises(CloudflareAccountNotFound):
            await DeleteCloudflareAccount(uow, FakeAuditApi()).execute(
                uuid4(), actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
            )

        assert uow.commits == 0


class TestTestCloudflareAccountConnection:
    async def test_calls_client_with_decrypted_token(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        ciphertext = FernetCodec.encrypt("plain-token", key=TEST_FERNET_KEY)
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token=ciphertext, created_by=ACTOR_ID
        )
        client = FakeCloudflareClient()

        await TestCloudflareAccountConnection(uow, client).execute(account.id)

        assert client.calls == [("cf-1", "plain-token")]

    async def test_rejects_unknown_account(self) -> None:
        uow = FakeCloudflareUnitOfWork()

        with pytest.raises(CloudflareAccountNotFound):
            await TestCloudflareAccountConnection(uow, FakeCloudflareClient()).execute(uuid4())


class TestRevealCloudflareAccountToken:
    async def test_returns_decrypted_token_and_audits_without_leaking_it(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        ciphertext = FernetCodec.encrypt("super-secret", key=TEST_FERNET_KEY)
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token=ciphertext, created_by=ACTOR_ID
        )
        audit_api = FakeAuditApi()

        revealed = await RevealCloudflareAccountToken(uow, audit_api).execute(
            account.id, actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
        )

        assert revealed == "super-secret"
        event = audit_api.events[0]
        assert event["action"] == CloudflareAccountAuditActions.TOKEN_REVEALED
        assert "super-secret" not in str(event)

    async def test_rejects_unknown_account(self) -> None:
        uow = FakeCloudflareUnitOfWork()

        with pytest.raises(CloudflareAccountNotFound):
            await RevealCloudflareAccountToken(uow, FakeAuditApi()).execute(
                uuid4(), actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
            )


class FakeUsersApi:
    """Duck-typed stand-in for app.modules.users.public.UsersApi."""

    def __init__(self, users: dict[UUID, object]) -> None:
        self._users = users

    async def get_user_by_id(self, user_id: UUID):
        return self._users.get(user_id)


class TestListCloudflareAccountManagers:
    async def test_lists_managers_enriched_with_user_info(self) -> None:
        from app.modules.users.public import UserRead

        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )
        await uow.account_managers.upsert(account.id, ACTOR_ID, AccessLevel.OWNER)
        user = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL, name="Actor")
        users_api = FakeUsersApi({ACTOR_ID: user})

        managers = await ListCloudflareAccountManagers(uow, users_api).execute(account.id)

        assert len(managers) == 1
        assert managers[0].email == ACTOR_EMAIL
        assert managers[0].access_level is AccessLevel.OWNER

    async def test_skips_a_manager_row_whose_user_was_deleted(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )
        await uow.account_managers.upsert(account.id, ACTOR_ID, AccessLevel.OWNER)
        users_api = FakeUsersApi({})  # ACTOR_ID resolves to None

        managers = await ListCloudflareAccountManagers(uow, users_api).execute(account.id)

        assert managers == []

    async def test_rejects_unknown_account(self) -> None:
        uow = FakeCloudflareUnitOfWork()

        with pytest.raises(CloudflareAccountNotFound):
            await ListCloudflareAccountManagers(uow, FakeUsersApi({})).execute(uuid4())


class TestAssignCloudflareAccountManager:
    async def test_assigns_manager(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )
        target_id = uuid4()

        await AssignCloudflareAccountManager(uow, FakeAuditApi()).execute(
            account.id, target_id, AccessLevel.VIEWER, actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
        )

        row = await uow.account_managers.get_for_user(account.id, target_id)
        assert row is not None
        assert row.access_level is AccessLevel.VIEWER
        assert uow.commits == 1

    async def test_rejects_unknown_account(self) -> None:
        uow = FakeCloudflareUnitOfWork()

        with pytest.raises(CloudflareAccountNotFound):
            await AssignCloudflareAccountManager(uow, FakeAuditApi()).execute(
                uuid4(), uuid4(), AccessLevel.VIEWER, actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
            )
