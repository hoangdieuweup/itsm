"""Unit tests for the observability services — Fakes throughout, mirroring
tests/cloudflare/test_services.py's exact Fake shape (FakeCloudflareUnitOfWork,
FakeProjectsApi, FakeAuditApi, FakeCloudflareClient)."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.core.crypto import FernetCodec
from app.integrations.loki.exceptions import LokiApiUnavailable
from app.integrations.loki.schemas import LokiLogEntry, LokiQueryResult
from app.modules.observability.config import observability_settings
from app.modules.observability.constants import LokiAuthType
from app.modules.observability.exceptions import (
    LokiConfigAlreadyExists,
    LokiConfigNotFound,
    ObservabilityEnvironmentNotFound,
)
from app.modules.observability.repository import AbstractLokiConfigRepository
from app.modules.observability.schemas import LokiConfigRead
from app.modules.observability.services.create_loki_config import CreateLokiConfig
from app.modules.observability.services.delete_loki_config import DeleteLokiConfig
from app.modules.observability.services.get_loki_config import GetLokiConfig
from app.modules.observability.services.run_log_query import RunLogQuery
from app.modules.observability.services.update_loki_config import UpdateLokiConfig
from app.modules.observability.uow import AbstractObservabilityUnitOfWork
from app.modules.users.public import UserRead

ACTOR_ID = uuid4()
ACTOR_EMAIL = "actor@example.com"
TEST_FERNET_KEY = "kL8Zx3vQ9mN2pR7wT4yU6bC1dF5gH0jK3lM6nO9pQ2s="


@pytest.fixture(autouse=True)
def _observability_fernet_key(monkeypatch) -> None:
    """Every test that encrypts/decrypts a credential needs a real 32-byte
    Fernet key — the module's own default is "" (fail-fast), which Fernet()
    rejects outright."""
    monkeypatch.setattr(observability_settings, "FERNET_KEY", TEST_FERNET_KEY)


class FakeLokiConfigRepo(AbstractLokiConfigRepository):
    def __init__(self) -> None:
        self._rows: dict[UUID, LokiConfigRead] = {}
        self._ciphertexts: dict[UUID, str | None] = {}

    async def get_by_id(self, entity_id):
        raise NotImplementedError

    async def list_page(self, limit, offset):
        raise NotImplementedError

    async def get_by_environment_id(self, environment_id):
        return self._rows.get(environment_id)

    async def get_credential_ciphertext(self, environment_id):
        return self._ciphertexts.get(environment_id)

    async def create(
        self, *, environment_id, endpoint_url, tenant_id, auth_type, credential, default_query, default_range_minutes
    ):
        row = LokiConfigRead(
            id=uuid4(),
            environment_id=environment_id,
            endpoint_url=endpoint_url,
            tenant_id=tenant_id,
            auth_type=auth_type,
            has_credential=credential is not None,
            default_query=default_query,
            default_range_minutes=default_range_minutes,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self._rows[environment_id] = row
        self._ciphertexts[environment_id] = credential
        return row

    async def update_by_environment_id(
        self, environment_id, *, endpoint_url, tenant_id, auth_type, credential, default_query, default_range_minutes
    ):
        existing = self._rows[environment_id]
        updated = existing.model_copy(
            update={
                "endpoint_url": endpoint_url,
                "tenant_id": tenant_id,
                "auth_type": auth_type,
                "has_credential": credential is not None,
                "default_query": default_query,
                "default_range_minutes": default_range_minutes,
            }
        )
        self._rows[environment_id] = updated
        self._ciphertexts[environment_id] = credential
        return updated

    async def delete_by_environment_id(self, environment_id):
        self._rows.pop(environment_id, None)
        self._ciphertexts.pop(environment_id, None)


class FakeObservabilityUnitOfWork(AbstractObservabilityUnitOfWork):
    def __init__(self) -> None:
        self.loki_configs = FakeLokiConfigRepo()
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class FakeProjectsApi:
    def __init__(self, environments: dict) -> None:
        self._environments = environments

    async def get_environment_by_id(self, environment_id):
        return self._environments.get(environment_id)


class FakeAuditApi:
    def __init__(self) -> None:
        self.events: list[dict] = []

    async def log_event(self, **kwargs) -> None:
        self.events.append(kwargs)


class FakeLokiClient:
    def __init__(self, result: LokiQueryResult | None = None, raises: Exception | None = None) -> None:
        self._result = result or LokiQueryResult(entries=[])
        self._raises = raises
        self.calls: list[dict] = []

    async def query_range(self, **kwargs) -> LokiQueryResult:
        self.calls.append(kwargs)
        if self._raises is not None:
            raise self._raises
        return self._result


def _actor() -> UserRead:
    return UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)


class TestCreateLokiConfig:
    async def test_rejects_unknown_environment(self) -> None:
        uow = FakeObservabilityUnitOfWork()
        use_case = CreateLokiConfig(uow, FakeProjectsApi({}), FakeAuditApi())
        with pytest.raises(ObservabilityEnvironmentNotFound):
            await use_case.execute(
                uuid4(),
                endpoint_url="http://loki:3100",
                tenant_id=None,
                auth_type=LokiAuthType.NONE,
                credential=None,
                default_query="",
                default_range_minutes=60,
                actor=_actor(),
            )

    async def test_rejects_duplicate_binding(self) -> None:
        uow = FakeObservabilityUnitOfWork()
        env_id = uuid4()
        projects_api = FakeProjectsApi({env_id: object()})
        audit_api = FakeAuditApi()
        use_case = CreateLokiConfig(uow, projects_api, audit_api)
        kwargs = dict(
            endpoint_url="http://loki:3100",
            tenant_id=None,
            auth_type=LokiAuthType.NONE,
            credential=None,
            default_query="",
            default_range_minutes=60,
            actor=_actor(),
        )
        await use_case.execute(env_id, **kwargs)
        with pytest.raises(LokiConfigAlreadyExists):
            await use_case.execute(env_id, **kwargs)

    async def test_encrypts_bearer_credential_and_audits(self) -> None:
        uow = FakeObservabilityUnitOfWork()
        env_id = uuid4()
        projects_api = FakeProjectsApi({env_id: object()})
        audit_api = FakeAuditApi()
        use_case = CreateLokiConfig(uow, projects_api, audit_api)

        config = await use_case.execute(
            env_id,
            endpoint_url="http://loki:3100",
            tenant_id=None,
            auth_type=LokiAuthType.BEARER,
            credential="raw-token",
            default_query="",
            default_range_minutes=60,
            actor=_actor(),
        )

        assert config.has_credential is True
        stored_ciphertext = uow.loki_configs._ciphertexts[env_id]
        assert stored_ciphertext != "raw-token"
        assert FernetCodec.decrypt(stored_ciphertext, key=TEST_FERNET_KEY) == "raw-token"
        assert uow.commits == 1
        assert len(audit_api.events) == 1
        assert audit_api.events[0]["actor"].email == ACTOR_EMAIL


class TestGetLokiConfig:
    async def test_returns_config(self) -> None:
        uow = FakeObservabilityUnitOfWork()
        env_id = uuid4()
        await uow.loki_configs.create(
            environment_id=env_id,
            endpoint_url="http://loki:3100",
            tenant_id=None,
            auth_type=LokiAuthType.NONE,
            credential=None,
            default_query="",
            default_range_minutes=60,
        )
        use_case = GetLokiConfig(uow)
        config = await use_case.execute(env_id)
        assert config.endpoint_url == "http://loki:3100"

    async def test_raises_not_found_when_absent(self) -> None:
        uow = FakeObservabilityUnitOfWork()
        use_case = GetLokiConfig(uow)
        with pytest.raises(LokiConfigNotFound):
            await use_case.execute(uuid4())


class TestUpdateLokiConfig:
    async def test_raises_not_found_when_absent(self) -> None:
        uow = FakeObservabilityUnitOfWork()
        use_case = UpdateLokiConfig(uow, FakeAuditApi())
        with pytest.raises(LokiConfigNotFound):
            await use_case.execute(uuid4(), actor=_actor())

    async def test_partial_update_keeps_unprovided_fields(self) -> None:
        uow = FakeObservabilityUnitOfWork()
        env_id = uuid4()
        await uow.loki_configs.create(
            environment_id=env_id,
            endpoint_url="http://loki:3100",
            tenant_id="tenant-a",
            auth_type=LokiAuthType.BEARER,
            credential=FernetCodec.encrypt("old-token", key=TEST_FERNET_KEY),
            default_query="{}",
            default_range_minutes=60,
        )
        use_case = UpdateLokiConfig(uow, FakeAuditApi())

        updated = await use_case.execute(env_id, default_range_minutes=120, actor=_actor())

        assert updated.default_range_minutes == 120
        assert updated.endpoint_url == "http://loki:3100"
        assert updated.tenant_id == "tenant-a"
        stored_ciphertext = uow.loki_configs._ciphertexts[env_id]
        assert FernetCodec.decrypt(stored_ciphertext, key=TEST_FERNET_KEY) == "old-token"

    async def test_switching_to_none_auth_clears_credential(self) -> None:
        uow = FakeObservabilityUnitOfWork()
        env_id = uuid4()
        await uow.loki_configs.create(
            environment_id=env_id,
            endpoint_url="http://loki:3100",
            tenant_id=None,
            auth_type=LokiAuthType.BEARER,
            credential=FernetCodec.encrypt("old-token", key=TEST_FERNET_KEY),
            default_query="",
            default_range_minutes=60,
        )
        use_case = UpdateLokiConfig(uow, FakeAuditApi())

        updated = await use_case.execute(env_id, auth_type=LokiAuthType.NONE, actor=_actor())

        assert updated.has_credential is False
        assert uow.loki_configs._ciphertexts[env_id] is None

    async def test_rotating_credential_re_encrypts(self) -> None:
        uow = FakeObservabilityUnitOfWork()
        env_id = uuid4()
        await uow.loki_configs.create(
            environment_id=env_id,
            endpoint_url="http://loki:3100",
            tenant_id=None,
            auth_type=LokiAuthType.BEARER,
            credential=FernetCodec.encrypt("old-token", key=TEST_FERNET_KEY),
            default_query="",
            default_range_minutes=60,
        )
        use_case = UpdateLokiConfig(uow, FakeAuditApi())

        await use_case.execute(env_id, credential="new-token", actor=_actor())

        stored_ciphertext = uow.loki_configs._ciphertexts[env_id]
        assert FernetCodec.decrypt(stored_ciphertext, key=TEST_FERNET_KEY) == "new-token"


class TestDeleteLokiConfig:
    async def test_raises_not_found_when_absent(self) -> None:
        uow = FakeObservabilityUnitOfWork()
        use_case = DeleteLokiConfig(uow, FakeAuditApi())
        with pytest.raises(LokiConfigNotFound):
            await use_case.execute(uuid4(), actor=_actor())

    async def test_deletes_and_audits(self) -> None:
        uow = FakeObservabilityUnitOfWork()
        env_id = uuid4()
        await uow.loki_configs.create(
            environment_id=env_id,
            endpoint_url="http://loki:3100",
            tenant_id=None,
            auth_type=LokiAuthType.NONE,
            credential=None,
            default_query="",
            default_range_minutes=60,
        )
        audit_api = FakeAuditApi()
        use_case = DeleteLokiConfig(uow, audit_api)

        await use_case.execute(env_id, actor=_actor())

        assert await uow.loki_configs.get_by_environment_id(env_id) is None
        assert len(audit_api.events) == 1


class TestRunLogQuery:
    async def test_raises_not_found_when_unconfigured(self) -> None:
        uow = FakeObservabilityUnitOfWork()
        use_case = RunLogQuery(uow, FakeLokiClient())
        with pytest.raises(LokiConfigNotFound):
            await use_case.execute(
                environment_id=uuid4(),
                query="{}",
                start=datetime(2026, 1, 1, tzinfo=UTC),
                end=datetime(2026, 1, 1, 1, tzinfo=UTC),
                limit=100,
            )

    async def test_builds_bearer_auth_header(self) -> None:
        uow = FakeObservabilityUnitOfWork()
        env_id = uuid4()
        await uow.loki_configs.create(
            environment_id=env_id,
            endpoint_url="http://loki:3100",
            tenant_id="tenant-a",
            auth_type=LokiAuthType.BEARER,
            credential=FernetCodec.encrypt("tok", key=TEST_FERNET_KEY),
            default_query="",
            default_range_minutes=60,
        )
        client = FakeLokiClient()
        use_case = RunLogQuery(uow, client)

        await use_case.execute(
            environment_id=env_id,
            query="{}",
            start=datetime(2026, 1, 1, tzinfo=UTC),
            end=datetime(2026, 1, 1, 1, tzinfo=UTC),
            limit=100,
        )

        assert client.calls[0]["auth_header"] == "Bearer tok"
        assert client.calls[0]["tenant_id"] == "tenant-a"

    async def test_builds_basic_auth_header(self) -> None:
        uow = FakeObservabilityUnitOfWork()
        env_id = uuid4()
        await uow.loki_configs.create(
            environment_id=env_id,
            endpoint_url="http://loki:3100",
            tenant_id=None,
            auth_type=LokiAuthType.BASIC,
            credential=FernetCodec.encrypt("user:pass", key=TEST_FERNET_KEY),
            default_query="",
            default_range_minutes=60,
        )
        client = FakeLokiClient()
        use_case = RunLogQuery(uow, client)

        await use_case.execute(
            environment_id=env_id,
            query="{}",
            start=datetime(2026, 1, 1, tzinfo=UTC),
            end=datetime(2026, 1, 1, 1, tzinfo=UTC),
            limit=100,
        )

        assert client.calls[0]["auth_header"].startswith("Basic ")

    async def test_no_auth_header_for_none_auth_type(self) -> None:
        uow = FakeObservabilityUnitOfWork()
        env_id = uuid4()
        await uow.loki_configs.create(
            environment_id=env_id,
            endpoint_url="http://loki:3100",
            tenant_id=None,
            auth_type=LokiAuthType.NONE,
            credential=None,
            default_query="",
            default_range_minutes=60,
        )
        client = FakeLokiClient()
        use_case = RunLogQuery(uow, client)

        await use_case.execute(
            environment_id=env_id,
            query="{}",
            start=datetime(2026, 1, 1, tzinfo=UTC),
            end=datetime(2026, 1, 1, 1, tzinfo=UTC),
            limit=100,
        )

        assert client.calls[0]["auth_header"] is None

    async def test_clamps_limit_to_max(self) -> None:
        uow = FakeObservabilityUnitOfWork()
        env_id = uuid4()
        await uow.loki_configs.create(
            environment_id=env_id,
            endpoint_url="http://loki:3100",
            tenant_id=None,
            auth_type=LokiAuthType.NONE,
            credential=None,
            default_query="",
            default_range_minutes=60,
        )
        client = FakeLokiClient()
        use_case = RunLogQuery(uow, client)

        await use_case.execute(
            environment_id=env_id,
            query="{}",
            start=datetime(2026, 1, 1, tzinfo=UTC),
            end=datetime(2026, 1, 1, 1, tzinfo=UTC),
            limit=999_999,
        )

        assert client.calls[0]["limit"] == 1000

    async def test_propagates_client_errors(self) -> None:
        uow = FakeObservabilityUnitOfWork()
        env_id = uuid4()
        await uow.loki_configs.create(
            environment_id=env_id,
            endpoint_url="http://loki:3100",
            tenant_id=None,
            auth_type=LokiAuthType.NONE,
            credential=None,
            default_query="",
            default_range_minutes=60,
        )
        client = FakeLokiClient(raises=LokiApiUnavailable())
        use_case = RunLogQuery(uow, client)

        with pytest.raises(LokiApiUnavailable):
            await use_case.execute(
                environment_id=env_id,
                query="{}",
                start=datetime(2026, 1, 1, tzinfo=UTC),
                end=datetime(2026, 1, 1, 1, tzinfo=UTC),
                limit=100,
            )

    async def test_returns_flattened_entries(self) -> None:
        uow = FakeObservabilityUnitOfWork()
        env_id = uuid4()
        await uow.loki_configs.create(
            environment_id=env_id,
            endpoint_url="http://loki:3100",
            tenant_id=None,
            auth_type=LokiAuthType.NONE,
            credential=None,
            default_query="",
            default_range_minutes=60,
        )
        entries = [LokiLogEntry(timestamp="1", line="hello", labels={})]
        client = FakeLokiClient(result=LokiQueryResult(entries=entries))
        use_case = RunLogQuery(uow, client)

        result = await use_case.execute(
            environment_id=env_id,
            query="{}",
            start=datetime(2026, 1, 1, tzinfo=UTC),
            end=datetime(2026, 1, 1, 1, tzinfo=UTC),
            limit=100,
        )

        assert result.entries == entries
