"""Unit tests for app.modules.cloudflare.public — the facade other modules
(observability, in Phase 9) reach cloudflare through."""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.crypto import FernetCodec
from app.modules.cloudflare.config import cloudflare_settings
from app.modules.cloudflare.public import CloudflareApi

TEST_KEY = "kL8Zx3vQ9mN2pR7wT4yU6bC1dF5gH0jK3lM6nO9pQ2s="


@pytest.fixture(autouse=True)
def _fernet_key(monkeypatch) -> None:
    monkeypatch.setattr(cloudflare_settings, "FERNET_KEY", TEST_KEY)


class FakeAccountsRepo:
    def __init__(self, accounts=None, token_ciphertexts=None) -> None:
        self._accounts = accounts or {}
        self._tokens = token_ciphertexts or {}
        self._webhook_destinations: dict = {}
        self.set_webhook_destination_calls = []

    async def get_by_id(self, account_id):
        return self._accounts.get(account_id)

    async def get_token_ciphertext(self, account_id):
        return self._tokens.get(account_id)

    async def get_webhook_destination_ciphertext(self, account_id):
        return self._webhook_destinations.get(account_id, (None, None))

    async def set_webhook_destination(self, account_id, *, cf_webhook_destination_id, secret_ciphertext):
        self._webhook_destinations[account_id] = (cf_webhook_destination_id, secret_ciphertext)
        self.set_webhook_destination_calls.append(account_id)


class FakeConfigsRepo:
    def __init__(self, configs=None) -> None:
        self._configs = configs or {}

    async def get_by_environment_id(self, environment_id):
        return self._configs.get(environment_id)


class FakeUow:
    def __init__(self, accounts: FakeAccountsRepo, configs: FakeConfigsRepo | None = None) -> None:
        self.accounts = accounts
        self.configs = configs or FakeConfigsRepo()
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


class FakeCloudflareClient:
    def __init__(self, destination_id: str = "wh-123") -> None:
        self.destination_id = destination_id
        self.create_calls: list[dict] = []

    async def create_webhook_destination(self, **kwargs):
        self.create_calls.append(kwargs)
        return self.destination_id


class TestGetReadyClientForEnvironment:
    async def test_returns_none_when_unbound(self) -> None:
        api = CloudflareApi(FakeUow(FakeAccountsRepo()), client=FakeCloudflareClient())
        assert await api.get_ready_client_for_environment(uuid4()) is None

    async def test_returns_ready_client_when_bound(self) -> None:
        env_id, account_id = uuid4(), uuid4()
        account = SimpleNamespace(id=account_id, cf_account_id="cf-123")
        config = SimpleNamespace(cloudflare_account_id=account_id)
        ciphertext = FernetCodec.encrypt("real-token", key=TEST_KEY)
        client = FakeCloudflareClient()
        api = CloudflareApi(
            FakeUow(
                FakeAccountsRepo({account_id: account}, {account_id: ciphertext}),
                FakeConfigsRepo({env_id: config}),
            ),
            client=client,
        )
        ready = await api.get_ready_client_for_environment(env_id)
        assert ready is not None
        assert ready.cf_account_id == "cf-123"
        assert ready.api_token == "real-token"
        assert ready.client is client
        assert ready.cloudflare_account_id == account_id


class TestEnsureWebhookDestination:
    async def test_registers_new_destination_and_returns_id(self) -> None:
        account_id = uuid4()
        account = SimpleNamespace(id=account_id, cf_account_id="cf-123")
        ciphertext = FernetCodec.encrypt("real-token", key=TEST_KEY)
        accounts_repo = FakeAccountsRepo({account_id: account}, {account_id: ciphertext})
        client = FakeCloudflareClient(destination_id="wh-new")
        api = CloudflareApi(FakeUow(accounts_repo), client=client)

        destination_id = await api.ensure_webhook_destination(
            account_id, webhook_url="https://x/webhooks/cloudflare-alert/" + str(account_id)
        )

        assert destination_id == "wh-new"
        assert accounts_repo.set_webhook_destination_calls == [account_id]
        assert client.create_calls[0]["cf_account_id"] == "cf-123"

    async def test_idempotent_returns_existing_id_without_calling_client(self) -> None:
        account_id = uuid4()
        account = SimpleNamespace(id=account_id, cf_account_id="cf-123")
        accounts_repo = FakeAccountsRepo({account_id: account})
        accounts_repo._webhook_destinations[account_id] = ("wh-existing", "ciphertext")
        client = FakeCloudflareClient()
        api = CloudflareApi(FakeUow(accounts_repo), client=client)

        destination_id = await api.ensure_webhook_destination(account_id, webhook_url="https://x")

        assert destination_id == "wh-existing"
        assert client.create_calls == []


class TestGetWebhookSecret:
    async def test_returns_none_when_never_registered(self) -> None:
        account_id = uuid4()
        api = CloudflareApi(FakeUow(FakeAccountsRepo()), client=FakeCloudflareClient())
        assert await api.get_webhook_secret(account_id) is None

    async def test_returns_decrypted_secret_when_registered(self) -> None:
        account_id = uuid4()
        secret_ciphertext = FernetCodec.encrypt("real-secret", key=TEST_KEY)
        accounts_repo = FakeAccountsRepo()
        accounts_repo._webhook_destinations[account_id] = ("wh-1", secret_ciphertext)
        api = CloudflareApi(FakeUow(accounts_repo), client=FakeCloudflareClient())

        assert await api.get_webhook_secret(account_id) == "real-secret"
