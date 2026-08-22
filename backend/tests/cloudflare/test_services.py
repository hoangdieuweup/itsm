"""Unit tests for app.modules.cloudflare.services — Fake-based, no database,
no real Cloudflare API calls."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.core.crypto import FernetCodec
from app.modules.cloudflare.config import cloudflare_settings
from app.modules.cloudflare.constants import (
    AccessLevel,
    CloudflareAccountAuditActions,
    DnsRecordType,
    ManagedBy,
)
from app.modules.cloudflare.exceptions import (
    CloudflareAccountManagerNotFound,
    CloudflareAccountNotFound,
    CloudflareConfigAlreadyExists,
    CloudflareConfigNotFound,
    CloudflareEnvironmentNotFound,
    DnsRecordNotFound,
    DnsRecordsExistForConfig,
    DnsRecordSyncFailed,
    InsufficientAccountAccess,
    InvalidCloudflareToken,
    LastOwnerRemovalBlocked,
    MissingDnsRecordPriority,
    ZoneNotOwnedByAccount,
)
from app.modules.cloudflare.exceptions import CloudflareApiUnavailable as CfUnavailable
from app.modules.cloudflare.repository import (
    AbstractCloudflareAccountManagerRepository,
    AbstractCloudflareAccountRepository,
    CloudflareAccountManagerRow,
)
from app.modules.cloudflare.schemas import (
    AccountAccessGrant,
    CloudflareAccountRead,
    CloudflareConfigRead,
    DnsRecordRead,
    ZoneOption,
)
from app.modules.cloudflare.services.assign_manager import AssignCloudflareAccountManager
from app.modules.cloudflare.services.create_account import CreateCloudflareAccount
from app.modules.cloudflare.services.create_config import CreateCloudflareConfig
from app.modules.cloudflare.services.create_dns_record import CreateDnsRecord
from app.modules.cloudflare.services.delete_account import DeleteCloudflareAccount
from app.modules.cloudflare.services.delete_config import DeleteCloudflareConfig
from app.modules.cloudflare.services.delete_dns_record import DeleteDnsRecord
from app.modules.cloudflare.services.list_account_managers import ListCloudflareAccountManagers
from app.modules.cloudflare.services.list_dns_records import ListDnsRecords
from app.modules.cloudflare.services.list_visible_accounts import ListVisibleCloudflareAccounts
from app.modules.cloudflare.services.list_zones import ListZones
from app.modules.cloudflare.services.remove_manager import RemoveCloudflareAccountManager
from app.modules.cloudflare.services.reveal_token import RevealCloudflareAccountToken
from app.modules.cloudflare.services.test_connection import TestCloudflareAccountConnection
from app.modules.cloudflare.services.update_account import UpdateCloudflareAccount
from app.modules.cloudflare.services.update_config import UpdateCloudflareConfig
from app.modules.cloudflare.services.update_dns_record import UpdateDnsRecord
from app.modules.cloudflare.services.update_manager import UpdateCloudflareAccountManager
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork
from app.modules.users.public import UserRead


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


class FakeConfigsRepo:
    def __init__(self) -> None:
        self._rows: dict = {}

    async def get_by_environment_id(self, environment_id):
        return self._rows.get(environment_id)

    async def create(self, *, environment_id, cloudflare_account_id, zone_id, zone_name):
        row = CloudflareConfigRead(
            id=uuid4(),
            environment_id=environment_id,
            cloudflare_account_id=cloudflare_account_id,
            zone_id=zone_id,
            zone_name=zone_name,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self._rows[environment_id] = row
        return row

    async def update_by_environment_id(self, environment_id, *, cloudflare_account_id, zone_id, zone_name):
        existing = self._rows[environment_id]
        updated = existing.model_copy(
            update={
                "cloudflare_account_id": cloudflare_account_id,
                "zone_id": zone_id,
                "zone_name": zone_name,
            }
        )
        self._rows[environment_id] = updated
        return updated

    async def delete_by_environment_id(self, environment_id):
        self._rows.pop(environment_id, None)


class FakeDnsRecordsRepo:
    def __init__(self) -> None:
        self._rows: dict = {}

    async def list_for_environment(self, environment_id):
        return [r for r in self._rows.values() if r.environment_id == environment_id]

    async def get_by_id(self, record_id):
        return self._rows.get(record_id)

    async def create(
        self, *, environment_id, cf_record_id, record_type, name, content, priority, proxied, ttl, created_by
    ):
        row = DnsRecordRead(
            id=uuid4(),
            environment_id=environment_id,
            cf_record_id=cf_record_id,
            record_type=record_type,
            name=name,
            content=content,
            priority=priority,
            proxied=proxied,
            ttl=ttl,
            managed_by=ManagedBy.SYSTEM,
            created_by=created_by,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self._rows[row.id] = row
        return row

    async def update(self, record_id, *, content, priority, proxied, ttl):
        existing = self._rows[record_id]
        updated = existing.model_copy(
            update={"content": content, "priority": priority, "proxied": proxied, "ttl": ttl}
        )
        self._rows[record_id] = updated
        return updated

    async def delete(self, record_id):
        self._rows.pop(record_id, None)


class FakeCloudflareUnitOfWork(AbstractCloudflareUnitOfWork):
    """In-memory unit of work. commit/rollback are no-ops that just count calls."""

    def __init__(self) -> None:
        self.accounts = FakeCloudflareAccountRepository()
        self.account_managers = FakeCloudflareAccountManagerRepository()
        self.configs = FakeConfigsRepo()
        self.dns_records = FakeDnsRecordsRepo()
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


class FakeClientWithZones(FakeCloudflareClient):
    def __init__(self, zones: list, raises: Exception | None = None) -> None:
        super().__init__(raises=raises)
        self._zones = zones

    async def list_zones(self, *, cf_account_id, api_token):
        if self._raises is not None:
            raise self._raises
        return self._zones


class FakeProjectsApi:
    def __init__(self, environments: dict) -> None:
        self._environments = environments

    async def get_environment_by_id(self, environment_id):
        return self._environments.get(environment_id)


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


class TestUpdateCloudflareAccountManager:
    async def test_changes_access_level(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )
        target_id = uuid4()
        await uow.account_managers.upsert(account.id, target_id, AccessLevel.VIEWER)

        await UpdateCloudflareAccountManager(uow, FakeAuditApi()).execute(
            account.id, target_id, AccessLevel.EDITOR, actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
        )

        row = await uow.account_managers.get_for_user(account.id, target_id)
        assert row.access_level is AccessLevel.EDITOR

    async def test_blocks_downgrading_the_last_owner(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )
        await uow.account_managers.upsert(account.id, ACTOR_ID, AccessLevel.OWNER)

        with pytest.raises(LastOwnerRemovalBlocked):
            await UpdateCloudflareAccountManager(uow, FakeAuditApi()).execute(
                account.id, ACTOR_ID, AccessLevel.EDITOR, actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
            )

        row = await uow.account_managers.get_for_user(account.id, ACTOR_ID)
        assert row.access_level is AccessLevel.OWNER

    async def test_allows_downgrading_one_of_two_owners(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )
        second_owner = uuid4()
        await uow.account_managers.upsert(account.id, ACTOR_ID, AccessLevel.OWNER)
        await uow.account_managers.upsert(account.id, second_owner, AccessLevel.OWNER)

        await UpdateCloudflareAccountManager(uow, FakeAuditApi()).execute(
            account.id, ACTOR_ID, AccessLevel.EDITOR, actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
        )

        row = await uow.account_managers.get_for_user(account.id, ACTOR_ID)
        assert row.access_level is AccessLevel.EDITOR

    async def test_rejects_unknown_manager(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )

        with pytest.raises(CloudflareAccountManagerNotFound):
            await UpdateCloudflareAccountManager(uow, FakeAuditApi()).execute(
                account.id, uuid4(), AccessLevel.EDITOR, actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
            )


class TestRemoveCloudflareAccountManager:
    async def test_removes_manager(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )
        target_id = uuid4()
        await uow.account_managers.upsert(account.id, target_id, AccessLevel.VIEWER)

        await RemoveCloudflareAccountManager(uow, FakeAuditApi()).execute(
            account.id, target_id, actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
        )

        assert await uow.account_managers.get_for_user(account.id, target_id) is None

    async def test_blocks_removing_the_last_owner(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )
        await uow.account_managers.upsert(account.id, ACTOR_ID, AccessLevel.OWNER)

        with pytest.raises(LastOwnerRemovalBlocked):
            await RemoveCloudflareAccountManager(uow, FakeAuditApi()).execute(
                account.id, ACTOR_ID, actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
            )

        assert await uow.account_managers.get_for_user(account.id, ACTOR_ID) is not None

    async def test_allows_removing_a_non_owner(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )
        await uow.account_managers.upsert(account.id, ACTOR_ID, AccessLevel.OWNER)
        target_id = uuid4()
        await uow.account_managers.upsert(account.id, target_id, AccessLevel.EDITOR)

        await RemoveCloudflareAccountManager(uow, FakeAuditApi()).execute(
            account.id, target_id, actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
        )

        assert await uow.account_managers.get_for_user(account.id, target_id) is None

    async def test_rejects_unknown_manager(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )

        with pytest.raises(CloudflareAccountManagerNotFound):
            await RemoveCloudflareAccountManager(uow, FakeAuditApi()).execute(
                account.id, uuid4(), actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
            )


class FakeRbacApi:
    """Duck-typed stand-in for app.modules.rbac.public.RbacApi — only the one
    method this module's services actually call."""

    def __init__(self, *, manage_all: bool) -> None:
        self._manage_all = manage_all

    async def has_permission(self, user_id, resource, action) -> bool:
        return self._manage_all


class TestListVisibleCloudflareAccounts:
    async def test_manage_all_sees_every_account(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        await uow.accounts.create(label="A", cf_account_id="cf-1", api_token="x", created_by=ACTOR_ID)
        await uow.accounts.create(label="B", cf_account_id="cf-2", api_token="x", created_by=ACTOR_ID)

        accounts = await ListVisibleCloudflareAccounts(uow, FakeRbacApi(manage_all=True)).execute(uuid4())

        assert {a.label for a in accounts} == {"A", "B"}

    async def test_regular_user_sees_only_managed_accounts(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        visible = await uow.accounts.create(
            label="Visible", cf_account_id="cf-1", api_token="x", created_by=ACTOR_ID
        )
        await uow.accounts.create(label="Hidden", cf_account_id="cf-2", api_token="x", created_by=ACTOR_ID)
        await uow.account_managers.upsert(visible.id, ACTOR_ID, AccessLevel.VIEWER)

        accounts = await ListVisibleCloudflareAccounts(uow, FakeRbacApi(manage_all=False)).execute(ACTOR_ID)

        assert [a.label for a in accounts] == ["Visible"]

    async def test_user_with_no_relationship_sees_nothing(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        await uow.accounts.create(label="A", cf_account_id="cf-1", api_token="x", created_by=ACTOR_ID)

        accounts = await ListVisibleCloudflareAccounts(uow, FakeRbacApi(manage_all=False)).execute(uuid4())

        assert accounts == []


class TestCreateCloudflareConfig:
    async def test_binds_environment_to_verified_zone(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A",
            cf_account_id="cf-1",
            api_token=FernetCodec.encrypt("plain", key=TEST_FERNET_KEY),
            created_by=ACTOR_ID,
        )
        await uow.account_managers.upsert(account.id, ACTOR_ID, AccessLevel.OWNER)
        env_id = uuid4()
        projects_api = FakeProjectsApi({env_id: object()})
        client = FakeClientWithZones([ZoneOption(id="z1", name="verified-name.com")])
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        config = await CreateCloudflareConfig(
            uow, client, FakeRbacApi(manage_all=False), projects_api, FakeAuditApi()
        ).execute(env_id, account.id, "z1", actor=actor)

        assert config.zone_name == "verified-name.com"
        assert config.zone_id == "z1"

    async def test_rejects_zone_not_owned_by_account(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A",
            cf_account_id="cf-1",
            api_token=FernetCodec.encrypt("plain", key=TEST_FERNET_KEY),
            created_by=ACTOR_ID,
        )
        await uow.account_managers.upsert(account.id, ACTOR_ID, AccessLevel.OWNER)
        env_id = uuid4()
        projects_api = FakeProjectsApi({env_id: object()})
        client = FakeClientWithZones([ZoneOption(id="other-zone", name="not-this.com")])
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        with pytest.raises(ZoneNotOwnedByAccount):
            await CreateCloudflareConfig(
                uow, client, FakeRbacApi(manage_all=False), projects_api, FakeAuditApi()
            ).execute(env_id, account.id, "spoofed-zone-id", actor=actor)

        assert uow.commits == 0

    async def test_rejects_unknown_environment(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )
        await uow.account_managers.upsert(account.id, ACTOR_ID, AccessLevel.OWNER)
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        with pytest.raises(CloudflareEnvironmentNotFound):
            await CreateCloudflareConfig(
                uow,
                FakeClientWithZones([]),
                FakeRbacApi(manage_all=False),
                FakeProjectsApi({}),
                FakeAuditApi(),
            ).execute(uuid4(), account.id, "z1", actor=actor)

    async def test_rejects_double_binding(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A",
            cf_account_id="cf-1",
            api_token=FernetCodec.encrypt("plain", key=TEST_FERNET_KEY),
            created_by=ACTOR_ID,
        )
        await uow.account_managers.upsert(account.id, ACTOR_ID, AccessLevel.OWNER)
        env_id = uuid4()
        projects_api = FakeProjectsApi({env_id: object()})
        client = FakeClientWithZones([ZoneOption(id="z1", name="a.com")])
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)
        await CreateCloudflareConfig(
            uow, client, FakeRbacApi(manage_all=False), projects_api, FakeAuditApi()
        ).execute(env_id, account.id, "z1", actor=actor)

        with pytest.raises(CloudflareConfigAlreadyExists):
            await CreateCloudflareConfig(
                uow, client, FakeRbacApi(manage_all=False), projects_api, FakeAuditApi()
            ).execute(env_id, account.id, "z1", actor=actor)

    async def test_rejects_insufficient_access(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )
        # No manager row for ACTOR_ID on this account, and no manage_all.
        env_id = uuid4()
        projects_api = FakeProjectsApi({env_id: object()})
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        with pytest.raises(InsufficientAccountAccess):
            await CreateCloudflareConfig(
                uow, FakeClientWithZones([]), FakeRbacApi(manage_all=False), projects_api, FakeAuditApi()
            ).execute(env_id, account.id, "z1", actor=actor)


class TestUpdateCloudflareConfig:
    async def test_rebinds_to_a_different_zone(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A",
            cf_account_id="cf-1",
            api_token=FernetCodec.encrypt("plain", key=TEST_FERNET_KEY),
            created_by=ACTOR_ID,
        )
        env_id = uuid4()
        await uow.configs.create(
            environment_id=env_id, cloudflare_account_id=account.id, zone_id="old-zone", zone_name="old.com"
        )
        client = FakeClientWithZones([ZoneOption(id="new-zone", name="new.com")])

        updated = await UpdateCloudflareConfig(uow, client, FakeAuditApi()).execute(
            env_id, "new-zone", actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
        )

        assert updated.zone_id == "new-zone"
        assert updated.zone_name == "new.com"

    async def test_rejects_zone_not_owned_by_account(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A",
            cf_account_id="cf-1",
            api_token=FernetCodec.encrypt("plain", key=TEST_FERNET_KEY),
            created_by=ACTOR_ID,
        )
        env_id = uuid4()
        await uow.configs.create(
            environment_id=env_id, cloudflare_account_id=account.id, zone_id="old-zone", zone_name="old.com"
        )
        client = FakeClientWithZones([ZoneOption(id="other-zone", name="other.com")])

        with pytest.raises(ZoneNotOwnedByAccount):
            await UpdateCloudflareConfig(uow, client, FakeAuditApi()).execute(
                env_id, "spoofed", actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
            )

    async def test_rejects_unbound_environment(self) -> None:
        uow = FakeCloudflareUnitOfWork()

        with pytest.raises(CloudflareConfigNotFound):
            await UpdateCloudflareConfig(uow, FakeClientWithZones([]), FakeAuditApi()).execute(
                uuid4(), "z1", actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
            )


class FakeDnsRecordsRepoEmpty:
    async def list_for_environment(self, environment_id):
        return []


class FakeDnsRecordsRepoNonEmpty:
    async def list_for_environment(self, environment_id):
        return [object()]


class TestDeleteCloudflareConfig:
    async def test_deletes_when_no_dns_records_exist(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        uow.dns_records = FakeDnsRecordsRepoEmpty()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )
        env_id = uuid4()
        await uow.configs.create(
            environment_id=env_id, cloudflare_account_id=account.id, zone_id="z1", zone_name="a.com"
        )

        await DeleteCloudflareConfig(uow, FakeAuditApi()).execute(
            env_id, actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
        )

        assert await uow.configs.get_by_environment_id(env_id) is None

    async def test_blocks_delete_when_dns_records_exist(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        uow.dns_records = FakeDnsRecordsRepoNonEmpty()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )
        env_id = uuid4()
        await uow.configs.create(
            environment_id=env_id, cloudflare_account_id=account.id, zone_id="z1", zone_name="a.com"
        )

        with pytest.raises(DnsRecordsExistForConfig):
            await DeleteCloudflareConfig(uow, FakeAuditApi()).execute(
                env_id, actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
            )

        assert await uow.configs.get_by_environment_id(env_id) is not None


class TestListZones:
    async def test_returns_zones_for_account(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        ciphertext = FernetCodec.encrypt("plain-token", key=TEST_FERNET_KEY)
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token=ciphertext, created_by=ACTOR_ID
        )
        client = FakeClientWithZones([ZoneOption(id="z1", name="a.com")])

        zones = await ListZones(uow, client).execute(account.id)

        assert zones == [ZoneOption(id="z1", name="a.com")]

    async def test_rejects_unknown_account(self) -> None:
        uow = FakeCloudflareUnitOfWork()

        with pytest.raises(CloudflareAccountNotFound):
            await ListZones(uow, FakeClientWithZones([])).execute(uuid4())


class TestListDnsRecords:
    async def test_returns_records_for_bound_environment(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )
        env_id = uuid4()
        await uow.configs.create(
            environment_id=env_id, cloudflare_account_id=account.id, zone_id="z1", zone_name="a.com"
        )
        await uow.dns_records.create(
            environment_id=env_id,
            cf_record_id="rec1",
            record_type=DnsRecordType.A,
            name="app",
            content="1.2.3.4",
            priority=None,
            proxied=True,
            ttl=1,
            created_by=ACTOR_ID,
        )

        records = await ListDnsRecords(uow).execute(env_id)

        assert len(records) == 1
        assert records[0].cf_record_id == "rec1"

    async def test_rejects_unbound_environment(self) -> None:
        uow = FakeCloudflareUnitOfWork()

        with pytest.raises(CloudflareConfigNotFound):
            await ListDnsRecords(uow).execute(uuid4())


class FakeDnsClient(FakeCloudflareClient):
    """Extends FakeCloudflareClient with the 3 DNS write methods, each
    independently configurable to raise."""

    def __init__(
        self,
        create_returns: str = "rec-new",
        create_raises: Exception | None = None,
        delete_raises: Exception | None = None,
    ) -> None:
        super().__init__()
        self._create_returns = create_returns
        self._create_raises = create_raises
        self._delete_raises = delete_raises
        self.deleted: list[str] = []

    async def create_dns_record(self, **kwargs) -> str:
        if self._create_raises is not None:
            raise self._create_raises
        return self._create_returns

    async def delete_dns_record(self, *, zone_id, cf_record_id, api_token) -> None:
        if self._delete_raises is not None:
            raise self._delete_raises
        self.deleted.append(cf_record_id)


class FailingDnsRecordsRepo(FakeDnsRecordsRepo):
    """Every create() call raises, simulating a local DB failure AFTER
    Cloudflare already accepted the write."""

    async def create(self, **kwargs):
        raise RuntimeError("simulated DB failure")


class TestCreateDnsRecord:
    async def test_creates_record_with_real_cf_record_id(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A",
            cf_account_id="cf-1",
            api_token=FernetCodec.encrypt("plain", key=TEST_FERNET_KEY),
            created_by=ACTOR_ID,
        )
        env_id = uuid4()
        await uow.configs.create(
            environment_id=env_id, cloudflare_account_id=account.id, zone_id="z1", zone_name="a.com"
        )
        client = FakeDnsClient(create_returns="rec-new")
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        record = await CreateDnsRecord(uow, client, FakeAuditApi()).execute(
            env_id, DnsRecordType.A, "app", "1.2.3.4", None, True, 1, actor=actor
        )

        assert record.cf_record_id == "rec-new"
        assert record.managed_by == ManagedBy.SYSTEM

    async def test_mx_without_priority_raises_before_calling_cloudflare(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A",
            cf_account_id="cf-1",
            api_token=FernetCodec.encrypt("plain", key=TEST_FERNET_KEY),
            created_by=ACTOR_ID,
        )
        env_id = uuid4()
        await uow.configs.create(
            environment_id=env_id, cloudflare_account_id=account.id, zone_id="z1", zone_name="a.com"
        )
        client = FakeDnsClient()
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        with pytest.raises(MissingDnsRecordPriority):
            await CreateDnsRecord(uow, client, FakeAuditApi()).execute(
                env_id, DnsRecordType.MX, "app", "mail.example.com", None, False, 1, actor=actor
            )

    async def test_local_failure_after_cf_success_attempts_compensating_delete(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        uow.dns_records = FailingDnsRecordsRepo()
        account = await uow.accounts.create(
            label="A",
            cf_account_id="cf-1",
            api_token=FernetCodec.encrypt("plain", key=TEST_FERNET_KEY),
            created_by=ACTOR_ID,
        )
        env_id = uuid4()
        await uow.configs.create(
            environment_id=env_id, cloudflare_account_id=account.id, zone_id="z1", zone_name="a.com"
        )
        client = FakeDnsClient(create_returns="rec-orphan-risk")
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        with pytest.raises(DnsRecordSyncFailed):
            await CreateDnsRecord(uow, client, FakeAuditApi()).execute(
                env_id, DnsRecordType.A, "app", "1.2.3.4", None, False, 1, actor=actor
            )

        assert client.deleted == ["rec-orphan-risk"]

    async def test_rejects_unbound_environment(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        with pytest.raises(CloudflareConfigNotFound):
            await CreateDnsRecord(uow, FakeDnsClient(), FakeAuditApi()).execute(
                uuid4(), DnsRecordType.A, "app", "1.2.3.4", None, False, 1, actor=actor
            )


class FakeDnsClientForUpdate(FakeCloudflareClient):
    def __init__(self, update_raises: Exception | None = None) -> None:
        super().__init__()
        self._update_raises = update_raises
        self.update_calls: list[dict] = []

    async def update_dns_record(self, **kwargs) -> None:
        if self._update_raises is not None:
            raise self._update_raises
        self.update_calls.append(kwargs)


class FailingUpdateDnsRecordsRepo(FakeDnsRecordsRepo):
    async def update(self, record_id, **kwargs):
        raise RuntimeError("simulated DB failure")


class TestUpdateDnsRecord:
    async def test_updates_content_and_ttl(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A",
            cf_account_id="cf-1",
            api_token=FernetCodec.encrypt("plain", key=TEST_FERNET_KEY),
            created_by=ACTOR_ID,
        )
        env_id = uuid4()
        await uow.configs.create(
            environment_id=env_id, cloudflare_account_id=account.id, zone_id="z1", zone_name="a.com"
        )
        existing = await uow.dns_records.create(
            environment_id=env_id,
            cf_record_id="rec1",
            record_type=DnsRecordType.A,
            name="app",
            content="1.2.3.4",
            priority=None,
            proxied=False,
            ttl=1,
            created_by=ACTOR_ID,
        )
        client = FakeDnsClientForUpdate()
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        updated = await UpdateDnsRecord(uow, client, FakeAuditApi()).execute(
            env_id, existing.id, "5.6.7.8", None, True, 300, actor=actor
        )

        assert updated.content == "5.6.7.8"
        assert updated.ttl == 300

    async def test_local_failure_after_cf_success_attempts_compensating_revert(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A",
            cf_account_id="cf-1",
            api_token=FernetCodec.encrypt("plain", key=TEST_FERNET_KEY),
            created_by=ACTOR_ID,
        )
        env_id = uuid4()
        await uow.configs.create(
            environment_id=env_id, cloudflare_account_id=account.id, zone_id="z1", zone_name="a.com"
        )
        existing = await uow.dns_records.create(
            environment_id=env_id,
            cf_record_id="rec1",
            record_type=DnsRecordType.A,
            name="app",
            content="1.2.3.4",
            priority=None,
            proxied=False,
            ttl=1,
            created_by=ACTOR_ID,
        )
        failing_repo = FailingUpdateDnsRecordsRepo()
        failing_repo._rows[existing.id] = existing
        uow.dns_records = failing_repo
        client = FakeDnsClientForUpdate()
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        with pytest.raises(DnsRecordSyncFailed):
            await UpdateDnsRecord(uow, client, FakeAuditApi()).execute(
                env_id, existing.id, "9.9.9.9", None, True, 600, actor=actor
            )

        # First call = the real update; second call = the compensating
        # revert back to the original content/ttl.
        assert len(client.update_calls) == 2
        assert client.update_calls[1]["content"] == "1.2.3.4"
        assert client.update_calls[1]["ttl"] == 1

    async def test_rejects_unknown_record(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A",
            cf_account_id="cf-1",
            api_token=FernetCodec.encrypt("plain", key=TEST_FERNET_KEY),
            created_by=ACTOR_ID,
        )
        env_id = uuid4()
        await uow.configs.create(
            environment_id=env_id, cloudflare_account_id=account.id, zone_id="z1", zone_name="a.com"
        )
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        with pytest.raises(DnsRecordNotFound):
            await UpdateDnsRecord(uow, FakeDnsClientForUpdate(), FakeAuditApi()).execute(
                env_id, uuid4(), "x", None, False, 1, actor=actor
            )


class FakeDnsClientForDelete(FakeCloudflareClient):
    def __init__(self) -> None:
        super().__init__()
        self.deleted: list[str] = []

    async def delete_dns_record(self, *, zone_id, cf_record_id, api_token) -> None:
        self.deleted.append(cf_record_id)


class FailingDeleteDnsRecordsRepo(FakeDnsRecordsRepo):
    async def delete(self, record_id):
        raise RuntimeError("simulated DB failure")


class TestDeleteDnsRecord:
    async def test_deletes_record(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A",
            cf_account_id="cf-1",
            api_token=FernetCodec.encrypt("plain", key=TEST_FERNET_KEY),
            created_by=ACTOR_ID,
        )
        env_id = uuid4()
        await uow.configs.create(
            environment_id=env_id, cloudflare_account_id=account.id, zone_id="z1", zone_name="a.com"
        )
        existing = await uow.dns_records.create(
            environment_id=env_id,
            cf_record_id="rec1",
            record_type=DnsRecordType.A,
            name="app",
            content="1.2.3.4",
            priority=None,
            proxied=False,
            ttl=1,
            created_by=ACTOR_ID,
        )
        client = FakeDnsClientForDelete()
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        await DeleteDnsRecord(uow, client, FakeAuditApi()).execute(env_id, existing.id, actor=actor)

        assert client.deleted == ["rec1"]
        assert await uow.dns_records.get_by_id(existing.id) is None

    async def test_local_failure_after_cf_delete_succeeds_raises_sync_failed(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A",
            cf_account_id="cf-1",
            api_token=FernetCodec.encrypt("plain", key=TEST_FERNET_KEY),
            created_by=ACTOR_ID,
        )
        env_id = uuid4()
        await uow.configs.create(
            environment_id=env_id, cloudflare_account_id=account.id, zone_id="z1", zone_name="a.com"
        )
        existing = await uow.dns_records.create(
            environment_id=env_id,
            cf_record_id="rec1",
            record_type=DnsRecordType.A,
            name="app",
            content="1.2.3.4",
            priority=None,
            proxied=False,
            ttl=1,
            created_by=ACTOR_ID,
        )
        failing_repo = FailingDeleteDnsRecordsRepo()
        failing_repo._rows[existing.id] = existing
        uow.dns_records = failing_repo
        client = FakeDnsClientForDelete()
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        with pytest.raises(DnsRecordSyncFailed):
            await DeleteDnsRecord(uow, client, FakeAuditApi()).execute(env_id, existing.id, actor=actor)

        # Cloudflare's side really is deleted — no compensating action exists.
        assert client.deleted == ["rec1"]

    async def test_rejects_unknown_record(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A",
            cf_account_id="cf-1",
            api_token=FernetCodec.encrypt("plain", key=TEST_FERNET_KEY),
            created_by=ACTOR_ID,
        )
        env_id = uuid4()
        await uow.configs.create(
            environment_id=env_id, cloudflare_account_id=account.id, zone_id="z1", zone_name="a.com"
        )
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        with pytest.raises(DnsRecordNotFound):
            await DeleteDnsRecord(uow, FakeDnsClientForDelete(), FakeAuditApi()).execute(
                env_id, uuid4(), actor=actor
            )
