"""Unit tests for app.modules.cloudflare.services — Fake-based, no database,
no real Cloudflare API calls."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.modules.cloudflare.constants import AccessLevel, CloudflareAccountAuditActions
from app.modules.cloudflare.exceptions import CloudflareApiUnavailable as CfUnavailable
from app.modules.cloudflare.exceptions import InvalidCloudflareToken
from app.modules.cloudflare.repository import (
    AbstractCloudflareAccountManagerRepository,
    AbstractCloudflareAccountRepository,
    CloudflareAccountManagerRow,
)
from app.modules.cloudflare.schemas import CloudflareAccountRead
from app.modules.cloudflare.services.create_account import CreateCloudflareAccount
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
