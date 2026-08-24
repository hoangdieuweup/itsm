"""Unit tests for the observability services — Fakes throughout, mirroring
tests/cloudflare/test_services.py's exact Fake shape (FakeCloudflareUnitOfWork,
FakeProjectsApi, FakeAuditApi, FakeCloudflareClient)."""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.core.crypto import FernetCodec
from app.integrations.cloudflare.exceptions import CloudflareDnsOperationRejected
from app.integrations.loki.exceptions import LokiApiUnavailable
from app.integrations.loki.schemas import LokiLogEntry, LokiQueryResult
from app.modules.observability.config import observability_settings
from app.modules.observability.constants import AlertRuleSource, AlertSeverity, LokiAuthType
from app.modules.observability.exceptions import (
    AlertRuleNotFound,
    CloudflareNotBoundForAlerting,
    LokiConfigAlreadyExists,
    LokiConfigNotFound,
    ObservabilityEnvironmentNotFound,
)
from app.modules.observability.repository import (
    AbstractAlertRuleRepository,
    AbstractIncidentRepository,
    AbstractLokiConfigRepository,
)
from app.modules.observability.schemas import AlertRuleRead, LokiConfigRead
from app.modules.observability.services.create_alert_rule import CreateAlertRule
from app.modules.observability.services.create_loki_config import CreateLokiConfig
from app.modules.observability.services.delete_alert_rule import DeleteAlertRule
from app.modules.observability.services.delete_loki_config import DeleteLokiConfig
from app.modules.observability.services.get_loki_config import GetLokiConfig
from app.modules.observability.services.list_alert_rules import ListAlertRules
from app.modules.observability.services.list_available_alerts import ListAvailableAlerts
from app.modules.observability.services.run_log_query import RunLogQuery
from app.modules.observability.services.stream_log_tail import StreamLogTail
from app.modules.observability.services.update_alert_rule import UpdateAlertRule
from app.modules.observability.services.update_loki_config import UpdateLokiConfig
from app.modules.observability.uow import AbstractObservabilityUnitOfWork
from app.modules.observability.utils import LokiAuthHelper
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
        self,
        *,
        environment_id,
        endpoint_url,
        tenant_id,
        auth_type,
        credential,
        default_query,
        default_range_minutes,
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
        self,
        environment_id,
        *,
        endpoint_url,
        tenant_id,
        auth_type,
        credential,
        default_query,
        default_range_minutes,
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


class FakeAlertRuleRepo(AbstractAlertRuleRepository):
    def __init__(self) -> None:
        self._rows: dict[UUID, AlertRuleRead] = {}
        self._channels: dict[UUID, list[UUID]] = {}

    async def get_by_id(self, entity_id):
        return self._rows.get(entity_id)

    async def list_page(self, limit, offset):
        raise NotImplementedError

    async def get_by_cf_policy_id(self, cf_policy_id):
        for row in self._rows.values():
            if row.cf_policy_id == cf_policy_id:
                return row
        return None

    async def list_for_environment(self, environment_id):
        return [row for row in self._rows.values() if row.environment_id == environment_id]

    async def create(self, *, environment_id, name, source, cf_alert_type=None, condition=None, severity):
        row = AlertRuleRead(
            id=uuid4(),
            environment_id=environment_id,
            name=name,
            source=source,
            cf_alert_type=cf_alert_type,
            cf_policy_id=None,
            condition=condition,
            severity=severity,
            is_active=True,
            channel_ids=[],
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self._rows[row.id] = row
        self._channels[row.id] = []
        return row

    async def set_cf_policy_id(self, alert_rule_id, *, cf_policy_id):
        self._rows[alert_rule_id] = self._rows[alert_rule_id].model_copy(
            update={"cf_policy_id": cf_policy_id}
        )

    async def update(self, alert_rule_id, *, name=None, is_active=None, severity=None):
        existing = self._rows[alert_rule_id]
        updates = {}
        if name is not None:
            updates["name"] = name
        if is_active is not None:
            updates["is_active"] = is_active
        if severity is not None:
            updates["severity"] = severity
        self._rows[alert_rule_id] = existing.model_copy(update=updates)
        return self._rows[alert_rule_id]

    async def delete(self, alert_rule_id):
        self._rows.pop(alert_rule_id, None)
        self._channels.pop(alert_rule_id, None)

    async def list_channel_ids(self, alert_rule_id):
        return self._channels.get(alert_rule_id, [])

    async def set_channels(self, alert_rule_id, channel_ids):
        self._channels[alert_rule_id] = list(channel_ids)
        self._rows[alert_rule_id] = self._rows[alert_rule_id].model_copy(
            update={"channel_ids": list(channel_ids)}
        )


class FakeIncidentRepo(AbstractIncidentRepository):
    def __init__(self) -> None:
        self._rows: dict = {}

    async def get_by_id(self, entity_id):
        return self._rows.get(entity_id)

    async def list_page(self, limit, offset):
        raise NotImplementedError

    async def get_open_by_correlation_id(self, correlation_id):
        raise NotImplementedError

    async def list_page_filtered(self, *, project_id=None, environment_id=None, status=None, limit, offset):
        raise NotImplementedError

    async def create(self, **kwargs):
        raise NotImplementedError

    async def update_status(self, incident_id, *, status, actor_id, at):
        raise NotImplementedError


class FakeObservabilityUnitOfWork(AbstractObservabilityUnitOfWork):
    def __init__(self) -> None:
        self.loki_configs = FakeLokiConfigRepo()
        self.alert_rules = FakeAlertRuleRepo()
        self.incidents = FakeIncidentRepo()
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
    def __init__(
        self,
        result: LokiQueryResult | None = None,
        raises: Exception | None = None,
        tail_entries: list[LokiLogEntry] | None = None,
        tail_raises: Exception | None = None,
    ) -> None:
        self._result = result or LokiQueryResult(entries=[])
        self._raises = raises
        self._tail_entries = tail_entries or []
        self._tail_raises = tail_raises
        self.calls: list[dict] = []
        self.tail_calls: list[dict] = []

    async def query_range(self, **kwargs) -> LokiQueryResult:
        self.calls.append(kwargs)
        if self._raises is not None:
            raise self._raises
        return self._result

    async def tail(self, **kwargs):
        self.tail_calls.append(kwargs)
        if self._tail_raises is not None:
            raise self._tail_raises
        for entry in self._tail_entries:
            yield entry


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


class TestResolveLokiAuthHeader:
    def test_none_auth_type_returns_none(self) -> None:
        config = LokiConfigRead(
            id=uuid4(),
            environment_id=uuid4(),
            endpoint_url="http://loki:3100",
            tenant_id=None,
            auth_type=LokiAuthType.NONE,
            has_credential=False,
            default_query="",
            default_range_minutes=60,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        assert LokiAuthHelper.resolve_loki_auth_header(config, None) is None

    def test_bearer_builds_header(self) -> None:
        config = LokiConfigRead(
            id=uuid4(),
            environment_id=uuid4(),
            endpoint_url="http://loki:3100",
            tenant_id=None,
            auth_type=LokiAuthType.BEARER,
            has_credential=True,
            default_query="",
            default_range_minutes=60,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        ciphertext = FernetCodec.encrypt("tok", key=TEST_FERNET_KEY)
        assert LokiAuthHelper.resolve_loki_auth_header(config, ciphertext) == "Bearer tok"

    def test_basic_builds_base64_header(self) -> None:
        config = LokiConfigRead(
            id=uuid4(),
            environment_id=uuid4(),
            endpoint_url="http://loki:3100",
            tenant_id=None,
            auth_type=LokiAuthType.BASIC,
            has_credential=True,
            default_query="",
            default_range_minutes=60,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        ciphertext = FernetCodec.encrypt("user:pass", key=TEST_FERNET_KEY)
        header = LokiAuthHelper.resolve_loki_auth_header(config, ciphertext)
        assert header is not None and header.startswith("Basic ")

    def test_missing_ciphertext_returns_none_even_if_auth_type_set(self) -> None:
        config = LokiConfigRead(
            id=uuid4(),
            environment_id=uuid4(),
            endpoint_url="http://loki:3100",
            tenant_id=None,
            auth_type=LokiAuthType.BEARER,
            has_credential=False,
            default_query="",
            default_range_minutes=60,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        assert LokiAuthHelper.resolve_loki_auth_header(config, None) is None


class TestStreamLogTail:
    async def test_raises_not_found_when_unconfigured(self) -> None:
        uow = FakeObservabilityUnitOfWork()
        use_case = StreamLogTail(uow, FakeLokiClient())
        with pytest.raises(LokiConfigNotFound):
            async for _ in use_case.execute(environment_id=uuid4(), query="{}", limit=100):
                pass

    async def test_streams_entries_through(self) -> None:
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
        entries = [LokiLogEntry(timestamp="1", line="hello", labels={})]
        client = FakeLokiClient(tail_entries=entries)
        use_case = StreamLogTail(uow, client)

        received = [entry async for entry in use_case.execute(environment_id=env_id, query="{}", limit=100)]

        assert received == entries
        assert client.tail_calls[0]["auth_header"] == "Bearer tok"
        assert client.tail_calls[0]["tenant_id"] == "tenant-a"

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
        client = FakeLokiClient(tail_raises=LokiApiUnavailable())
        use_case = StreamLogTail(uow, client)

        with pytest.raises(LokiApiUnavailable):
            async for _ in use_case.execute(environment_id=env_id, query="{}", limit=100):
                pass


class FakeReadyCloudflareClient:
    def __init__(self, client, cf_account_id="cf-1", api_token="tok", cloudflare_account_id=None) -> None:
        self.client, self.cf_account_id, self.api_token, self.cloudflare_account_id = (
            client,
            cf_account_id,
            api_token,
            cloudflare_account_id or uuid4(),
        )


class FakeCloudflareApiForAlertRules:
    def __init__(self, ready=None, webhook_destination_id="wh-123") -> None:
        self._ready = ready
        self._webhook_destination_id = webhook_destination_id
        self.ensure_calls: list[tuple] = []

    async def get_ready_client_for_environment(self, environment_id):
        return self._ready

    async def ensure_webhook_destination(self, cloudflare_account_id, *, webhook_url):
        self.ensure_calls.append((cloudflare_account_id, webhook_url))
        return self._webhook_destination_id


class FakeCloudflareClientForPolicy:
    def __init__(self, policy_id="policy-789") -> None:
        self.policy_id = policy_id
        self.created: list[dict] = []
        self.updated: list[dict] = []
        self.deleted: list[dict] = []

    async def create_policy(self, **kwargs):
        self.created.append(kwargs)
        return self.policy_id

    async def update_policy(self, **kwargs):
        self.updated.append(kwargs)

    async def delete_policy(self, **kwargs):
        self.deleted.append(kwargs)

    async def list_available_alerts(self, **kwargs):
        return [{"type": "advanced_ddos_attack_l4_alert"}, {"type": "health_check_status_notification"}]


class FakeLokiClientForRuleGroup:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def upsert_rule_group(self, **kwargs):
        self.calls.append(kwargs)


class TestCreateAlertRuleCloudflareNative:
    async def test_full_flow_persists_cf_policy_id(self) -> None:
        env_id = uuid4()
        cf_client = FakeCloudflareClientForPolicy()
        cloudflare_api = FakeCloudflareApiForAlertRules(ready=FakeReadyCloudflareClient(cf_client))
        uow = FakeObservabilityUnitOfWork()
        use_case = CreateAlertRule(
            uow,
            cloudflare_api=cloudflare_api,
            loki_client=None,
            projects_api=FakeProjectsApi({env_id: SimpleNamespace(project_id=uuid4())}),
            audit_api=FakeAuditApi(),
        )

        result = await use_case.execute(
            environment_id=env_id,
            name="DDoS",
            source=AlertRuleSource.CLOUDFLARE_NATIVE,
            cf_alert_type="advanced_ddos_attack_l4_alert",
            condition=None,
            severity=AlertSeverity.HIGH,
            channel_ids=[],
            actor=_actor(),
        )
        assert result.cf_policy_id == "policy-789"
        assert cloudflare_api.ensure_calls
        assert cf_client.created[0]["alert_type"] == "advanced_ddos_attack_l4_alert"

    async def test_unbound_environment_raises(self) -> None:
        env_id = uuid4()
        cloudflare_api = FakeCloudflareApiForAlertRules(ready=None)
        uow = FakeObservabilityUnitOfWork()
        use_case = CreateAlertRule(
            uow,
            cloudflare_api=cloudflare_api,
            loki_client=None,
            projects_api=FakeProjectsApi({env_id: SimpleNamespace(project_id=uuid4())}),
            audit_api=FakeAuditApi(),
        )
        with pytest.raises(CloudflareNotBoundForAlerting):
            await use_case.execute(
                environment_id=env_id,
                name="X",
                source=AlertRuleSource.CLOUDFLARE_NATIVE,
                cf_alert_type="x",
                condition=None,
                severity=AlertSeverity.LOW,
                channel_ids=[],
                actor=_actor(),
            )
        assert uow.alert_rules._rows == {}

    async def test_cloudflare_failure_persists_nothing(self) -> None:
        env_id = uuid4()

        class FailingCfClient:
            async def create_policy(self, **kwargs):
                raise CloudflareDnsOperationRejected()

        cloudflare_api = FakeCloudflareApiForAlertRules(ready=FakeReadyCloudflareClient(FailingCfClient()))
        uow = FakeObservabilityUnitOfWork()
        use_case = CreateAlertRule(
            uow,
            cloudflare_api=cloudflare_api,
            loki_client=None,
            projects_api=FakeProjectsApi({env_id: SimpleNamespace(project_id=uuid4())}),
            audit_api=FakeAuditApi(),
        )
        with pytest.raises(CloudflareDnsOperationRejected):
            await use_case.execute(
                environment_id=env_id,
                name="X",
                source=AlertRuleSource.CLOUDFLARE_NATIVE,
                cf_alert_type="x",
                condition=None,
                severity=AlertSeverity.LOW,
                channel_ids=[],
                actor=_actor(),
            )
        assert uow.alert_rules._rows == {}

    async def test_rejects_unknown_environment(self) -> None:
        use_case = CreateAlertRule(
            FakeObservabilityUnitOfWork(),
            cloudflare_api=FakeCloudflareApiForAlertRules(),
            loki_client=None,
            projects_api=FakeProjectsApi({}),
            audit_api=FakeAuditApi(),
        )
        with pytest.raises(ObservabilityEnvironmentNotFound):
            await use_case.execute(
                environment_id=uuid4(),
                name="X",
                source=AlertRuleSource.CLOUDFLARE_NATIVE,
                cf_alert_type="x",
                condition=None,
                severity=AlertSeverity.LOW,
                channel_ids=[],
                actor=_actor(),
            )


class TestCreateAlertRuleLokiQuery:
    async def test_calls_upsert_rule_group_with_join_label(self) -> None:
        loki_client = FakeLokiClientForRuleGroup()
        env_id = uuid4()
        use_case = CreateAlertRule(
            FakeObservabilityUnitOfWork(),
            cloudflare_api=None,
            loki_client=loki_client,
            projects_api=FakeProjectsApi({env_id: SimpleNamespace(project_id=uuid4())}),
            audit_api=FakeAuditApi(),
        )
        result = await use_case.execute(
            environment_id=env_id,
            name="Error rate",
            source=AlertRuleSource.LOKI_QUERY,
            cf_alert_type=None,
            condition={"query": '{app="x"} |= "error"', "for": "5m", "endpoint_url": "http://loki:3100"},
            severity=AlertSeverity.MEDIUM,
            channel_ids=[],
            actor=_actor(),
        )
        assert loki_client.calls[0]["labels"] == {"app_alert_rule_id": str(result.id)}
        assert loki_client.calls[0]["namespace"] == "itsm"


class TestListAvailableAlerts:
    async def test_shapes_raw_dicts_into_options(self) -> None:
        env_id = uuid4()
        cf_client = FakeCloudflareClientForPolicy()
        cloudflare_api = FakeCloudflareApiForAlertRules(ready=FakeReadyCloudflareClient(cf_client))
        use_case = ListAvailableAlerts(cloudflare_api)

        options = await use_case.execute(env_id)

        assert options[0].alert_type == "advanced_ddos_attack_l4_alert"
        assert options[0].display_name

    async def test_unbound_environment_raises(self) -> None:
        cloudflare_api = FakeCloudflareApiForAlertRules(ready=None)
        use_case = ListAvailableAlerts(cloudflare_api)
        with pytest.raises(CloudflareNotBoundForAlerting):
            await use_case.execute(uuid4())


class TestUpdateAlertRule:
    async def test_raises_not_found_when_absent(self) -> None:
        use_case = UpdateAlertRule(FakeObservabilityUnitOfWork(), FakeAuditApi())
        with pytest.raises(AlertRuleNotFound):
            await use_case.execute(uuid4(), actor=_actor())

    async def test_partial_update_keeps_unprovided_fields(self) -> None:
        uow = FakeObservabilityUnitOfWork()
        env_id = uuid4()
        rule = await uow.alert_rules.create(
            environment_id=env_id,
            name="Original",
            source=AlertRuleSource.LOKI_QUERY,
            severity=AlertSeverity.LOW,
        )
        use_case = UpdateAlertRule(uow, FakeAuditApi())

        updated = await use_case.execute(rule.id, is_active=False, actor=_actor())

        assert updated.is_active is False
        assert updated.name == "Original"


class TestDeleteAlertRule:
    async def test_deletes_loki_rule_without_cloudflare_call(self) -> None:
        uow = FakeObservabilityUnitOfWork()
        env_id = uuid4()
        rule = await uow.alert_rules.create(
            environment_id=env_id,
            name="Loki rule",
            source=AlertRuleSource.LOKI_QUERY,
            severity=AlertSeverity.LOW,
        )
        cloudflare_api = FakeCloudflareApiForAlertRules()
        use_case = DeleteAlertRule(uow, cloudflare_api, FakeAuditApi())

        await use_case.execute(rule.id, actor=_actor())

        assert await uow.alert_rules.get_by_id(rule.id) is None

    async def test_deletes_cloudflare_native_rule_calls_delete_policy_first(self) -> None:
        uow = FakeObservabilityUnitOfWork()
        env_id = uuid4()
        rule = await uow.alert_rules.create(
            environment_id=env_id,
            name="CF rule",
            source=AlertRuleSource.CLOUDFLARE_NATIVE,
            cf_alert_type="advanced_ddos_attack_l4_alert",
            severity=AlertSeverity.HIGH,
        )
        await uow.alert_rules.set_cf_policy_id(rule.id, cf_policy_id="policy-789")
        cf_client = FakeCloudflareClientForPolicy()
        cloudflare_api = FakeCloudflareApiForAlertRules(ready=FakeReadyCloudflareClient(cf_client))
        use_case = DeleteAlertRule(uow, cloudflare_api, FakeAuditApi())

        await use_case.execute(rule.id, actor=_actor())

        assert cf_client.deleted[0]["policy_id"] == "policy-789"
        assert await uow.alert_rules.get_by_id(rule.id) is None

    async def test_raises_not_found_when_absent(self) -> None:
        use_case = DeleteAlertRule(
            FakeObservabilityUnitOfWork(), FakeCloudflareApiForAlertRules(), FakeAuditApi()
        )
        with pytest.raises(AlertRuleNotFound):
            await use_case.execute(uuid4(), actor=_actor())


class TestListAlertRules:
    async def test_returns_rules_for_environment(self) -> None:
        uow = FakeObservabilityUnitOfWork()
        env_id = uuid4()
        await uow.alert_rules.create(
            environment_id=env_id, name="A", source=AlertRuleSource.LOKI_QUERY, severity=AlertSeverity.LOW
        )
        await uow.alert_rules.create(
            environment_id=uuid4(), name="B", source=AlertRuleSource.LOKI_QUERY, severity=AlertSeverity.LOW
        )
        use_case = ListAlertRules(uow)

        rules = await use_case.execute(env_id)

        assert len(rules) == 1
        assert rules[0].name == "A"
