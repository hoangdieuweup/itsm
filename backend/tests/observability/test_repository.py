"""Integration tests for the observability repository — real Postgres via a
locally scoped session fixture, mirroring tests/cloudflare/test_repository.py's
`_session` pattern (session_factory from the shared `engine` fixture,
truncate-after-test for isolation)."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.notifications.constants import NotificationChannelType
from app.modules.notifications.models import NotificationChannel
from app.modules.observability.config import observability_settings
from app.modules.observability.constants import (
    AlertRuleSource,
    AlertSeverity,
    IncidentCategory,
    IncidentSource,
    IncidentStatus,
    LokiAuthType,
)
from app.modules.observability.exceptions import (
    AlertRuleNotFound,
    IncidentNotFound,
    LokiConfigNotFound,
    LokiCredentialUnreadable,
)
from app.modules.observability.models import AlertRule, AlertRuleChannel, Incident, LokiConfig
from app.modules.observability.repository import AlertRuleRepository, IncidentRepository, LokiConfigRepository
from app.modules.projects.models import Environment, Project


@pytest.fixture(autouse=True)
def _loki_fernet_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """LokiConfigRepository encrypts the stored credential itself."""
    monkeypatch.setattr(observability_settings, "FERNET_KEY", Fernet.generate_key().decode())


async def _stored_credential(session: AsyncSession, environment_id: UUID) -> str | None:
    """Read the raw credential column, bypassing the repository's decryption."""
    row = await session.scalar(select(LokiConfig).where(LokiConfig.environment_id == environment_id))
    return row.credential if row is not None else None


@pytest.fixture
async def _session(engine) -> AsyncIterator[AsyncSession]:
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()

    async with engine.begin() as conn:
        await conn.execute(delete(Incident))
        await conn.execute(delete(AlertRuleChannel))
        await conn.execute(delete(AlertRule))
        await conn.execute(delete(NotificationChannel))
        await conn.execute(delete(LokiConfig))
        await conn.execute(delete(Environment))
        await conn.execute(delete(Project))


async def _make_environment(session: AsyncSession) -> Environment:
    project = Project(name=f"P-{uuid4()}")
    session.add(project)
    await session.flush()
    env = Environment(project_id=project.id, type="dev", name="Dev", base_url=None)
    session.add(env)
    await session.flush()
    await session.refresh(env)
    await session.commit()
    return env


async def _make_project_and_environment(session: AsyncSession) -> tuple[UUID, UUID]:
    env = await _make_environment(session)
    return env.project_id, env.id


async def _make_notification_channel(session: AsyncSession, project_id: UUID) -> NotificationChannel:
    channel = NotificationChannel(
        project_id=project_id, type=NotificationChannelType.EMAIL, name=f"C-{uuid4()}", config={}
    )
    session.add(channel)
    await session.flush()
    await session.refresh(channel)
    await session.commit()
    return channel


class TestLokiConfigRepository:
    async def test_create_and_get_by_environment_id(self, _session: AsyncSession) -> None:
        env = await _make_environment(_session)
        repo = LokiConfigRepository(_session)

        created = await repo.create(
            environment_id=env.id,
            endpoint_url="http://loki:3100",
            tenant_id=None,
            auth_type=LokiAuthType.NONE,
            credential=None,
            default_query="",
            default_range_minutes=60,
        )

        found = await repo.get_by_environment_id(env.id)
        assert found is not None
        assert found.id == created.id
        assert found.endpoint_url == "http://loki:3100"

    async def test_get_by_environment_id_returns_none_when_absent(self, _session: AsyncSession) -> None:
        repo = LokiConfigRepository(_session)
        assert await repo.get_by_environment_id(uuid4()) is None

    async def test_get_credential_decrypts_the_stored_value(self, _session: AsyncSession) -> None:
        env = await _make_environment(_session)
        repo = LokiConfigRepository(_session)
        await repo.create(
            environment_id=env.id,
            endpoint_url="http://loki:3100",
            tenant_id=None,
            auth_type=LokiAuthType.BEARER,
            credential="tok",
            default_query="",
            default_range_minutes=60,
        )

        assert await _stored_credential(_session, env.id) != "tok"
        assert await repo.get_credential(env.id) == "tok"

    async def test_get_credential_returns_none_when_absent(self, _session: AsyncSession) -> None:
        repo = LokiConfigRepository(_session)
        assert await repo.get_credential(uuid4()) is None

    async def test_get_credential_raises_unreadable_after_a_key_change(
        self, _session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        env = await _make_environment(_session)
        repo = LokiConfigRepository(_session)
        await repo.create(
            environment_id=env.id,
            endpoint_url="http://loki:3100",
            tenant_id=None,
            auth_type=LokiAuthType.BEARER,
            credential="tok",
            default_query="",
            default_range_minutes=60,
        )
        monkeypatch.setattr(observability_settings, "FERNET_KEY", Fernet.generate_key().decode())

        with pytest.raises(LokiCredentialUnreadable):
            await repo.get_credential(env.id)

    async def test_update_with_keep_credential_leaves_the_stored_value(self, _session: AsyncSession) -> None:
        env = await _make_environment(_session)
        repo = LokiConfigRepository(_session)
        await repo.create(
            environment_id=env.id,
            endpoint_url="http://loki:3100",
            tenant_id=None,
            auth_type=LokiAuthType.BEARER,
            credential="tok",
            default_query="",
            default_range_minutes=60,
        )
        before = await _stored_credential(_session, env.id)

        await repo.update_by_environment_id(
            env.id,
            endpoint_url="http://loki-2:3100",
            tenant_id=None,
            auth_type=LokiAuthType.BEARER,
            credential=None,
            keep_credential=True,
            default_query="",
            default_range_minutes=60,
        )

        assert await _stored_credential(_session, env.id) == before
        assert await repo.get_credential(env.id) == "tok"

    async def test_environment_id_is_unique(self, _session: AsyncSession) -> None:
        env = await _make_environment(_session)
        repo = LokiConfigRepository(_session)
        await repo.create(
            environment_id=env.id,
            endpoint_url="http://loki:3100",
            tenant_id=None,
            auth_type=LokiAuthType.NONE,
            credential=None,
            default_query="",
            default_range_minutes=60,
        )
        await _session.commit()

        with pytest.raises(IntegrityError):
            await repo.create(
                environment_id=env.id,
                endpoint_url="http://loki-2:3100",
                tenant_id=None,
                auth_type=LokiAuthType.NONE,
                credential=None,
                default_query="",
                default_range_minutes=60,
            )
            await _session.commit()

    async def test_update_by_environment_id(self, _session: AsyncSession) -> None:
        env = await _make_environment(_session)
        repo = LokiConfigRepository(_session)
        await repo.create(
            environment_id=env.id,
            endpoint_url="http://loki:3100",
            tenant_id=None,
            auth_type=LokiAuthType.NONE,
            credential=None,
            default_query="",
            default_range_minutes=60,
        )
        await _session.commit()

        updated = await repo.update_by_environment_id(
            env.id,
            endpoint_url="http://loki-2:3100",
            tenant_id="tenant-a",
            auth_type=LokiAuthType.BEARER,
            credential="token",
            default_query='{job="api"}',
            default_range_minutes=120,
        )
        assert updated.endpoint_url == "http://loki-2:3100"
        assert updated.auth_type == LokiAuthType.BEARER
        assert updated.default_range_minutes == 120

    async def test_delete_by_environment_id(self, _session: AsyncSession) -> None:
        env = await _make_environment(_session)
        repo = LokiConfigRepository(_session)
        await repo.create(
            environment_id=env.id,
            endpoint_url="http://loki:3100",
            tenant_id=None,
            auth_type=LokiAuthType.NONE,
            credential=None,
            default_query="",
            default_range_minutes=60,
        )
        await _session.commit()

        await repo.delete_by_environment_id(env.id)
        await _session.commit()

        assert await repo.get_by_environment_id(env.id) is None


class TestAlertRuleRepository:
    async def test_get_by_cf_policy_id_finds_exact_match(self, _session: AsyncSession) -> None:
        repo = AlertRuleRepository(_session)
        env = await _make_environment(_session)
        created = await repo.create(
            environment_id=env.id,
            name="DDoS rule",
            source=AlertRuleSource.CLOUDFLARE_NATIVE,
            cf_alert_type="advanced_ddos_attack_l4_alert",
            severity=AlertSeverity.HIGH,
        )
        await repo.set_cf_policy_id(created.id, cf_policy_id="policy-789")
        found = await repo.get_by_cf_policy_id("policy-789")
        assert found is not None and found.id == created.id

    async def test_get_by_cf_policy_id_returns_none_for_unknown(self, _session: AsyncSession) -> None:
        repo = AlertRuleRepository(_session)
        assert await repo.get_by_cf_policy_id("nonexistent") is None

    async def test_create_defaults_to_active_with_no_channels(self, _session: AsyncSession) -> None:
        repo = AlertRuleRepository(_session)
        env = await _make_environment(_session)
        created = await repo.create(
            environment_id=env.id,
            name="Loki rule",
            source=AlertRuleSource.LOKI_QUERY,
            condition={"query": '{job="api"}', "threshold": 5, "for": "5m"},
            severity=AlertSeverity.MEDIUM,
        )
        assert created.is_active is True
        assert created.channel_ids == []
        assert created.cf_policy_id is None

    async def test_list_for_environment_orders_by_created_at(self, _session: AsyncSession) -> None:
        repo = AlertRuleRepository(_session)
        env = await _make_environment(_session)
        first = await repo.create(
            environment_id=env.id,
            name="First",
            source=AlertRuleSource.LOKI_QUERY,
            severity=AlertSeverity.LOW,
        )
        second = await repo.create(
            environment_id=env.id,
            name="Second",
            source=AlertRuleSource.LOKI_QUERY,
            severity=AlertSeverity.LOW,
        )
        rules = await repo.list_for_environment(env.id)
        assert [r.id for r in rules] == [first.id, second.id]

    async def test_update_partial_fields(self, _session: AsyncSession) -> None:
        repo = AlertRuleRepository(_session)
        env = await _make_environment(_session)
        created = await repo.create(
            environment_id=env.id,
            name="Original",
            source=AlertRuleSource.LOKI_QUERY,
            severity=AlertSeverity.LOW,
        )
        updated = await repo.update(created.id, is_active=False)
        assert updated.is_active is False
        assert updated.name == "Original"
        assert updated.severity == AlertSeverity.LOW

    async def test_delete_removes_row(self, _session: AsyncSession) -> None:
        repo = AlertRuleRepository(_session)
        env = await _make_environment(_session)
        created = await repo.create(
            environment_id=env.id,
            name="Doomed",
            source=AlertRuleSource.LOKI_QUERY,
            severity=AlertSeverity.LOW,
        )
        await repo.delete(created.id)
        assert await repo.get_by_id(created.id) is None

    async def test_set_channels_replaces_existing_set(self, _session: AsyncSession) -> None:
        repo = AlertRuleRepository(_session)
        env = await _make_environment(_session)
        created = await repo.create(
            environment_id=env.id,
            name="Channeled",
            source=AlertRuleSource.LOKI_QUERY,
            severity=AlertSeverity.LOW,
        )
        first_channel = await _make_notification_channel(_session, env.project_id)
        second_channel = await _make_notification_channel(_session, env.project_id)
        await repo.set_channels(created.id, [first_channel.id])
        assert await repo.list_channel_ids(created.id) == [first_channel.id]

        await repo.set_channels(created.id, [second_channel.id])
        assert await repo.list_channel_ids(created.id) == [second_channel.id]


class TestIncidentRepository:
    async def test_get_open_by_correlation_id_excludes_resolved(self, _session: AsyncSession) -> None:
        repo = IncidentRepository(_session)
        project_id, env_id = await _make_project_and_environment(_session)
        resolved = await repo.create(
            project_id=project_id,
            environment_id=env_id,
            alert_rule_id=None,
            source=IncidentSource.CLOUDFLARE,
            category=IncidentCategory.DDOS,
            severity=AlertSeverity.HIGH,
            title="t",
            alert_correlation_id="corr-1",
        )
        await repo.update_status(
            resolved.id, status=IncidentStatus.RESOLVED, actor_id=None, at=datetime.now(UTC)
        )
        assert await repo.get_open_by_correlation_id("corr-1") is None

        open_incident = await repo.create(
            project_id=project_id,
            environment_id=env_id,
            alert_rule_id=None,
            source=IncidentSource.CLOUDFLARE,
            category=IncidentCategory.DDOS,
            severity=AlertSeverity.HIGH,
            title="t2",
            alert_correlation_id="corr-2",
        )
        found = await repo.get_open_by_correlation_id("corr-2")
        assert found is not None and found.id == open_incident.id

    async def test_create_defaults_to_open_status(self, _session: AsyncSession) -> None:
        repo = IncidentRepository(_session)
        project_id, env_id = await _make_project_and_environment(_session)
        created = await repo.create(
            project_id=project_id,
            environment_id=env_id,
            alert_rule_id=None,
            source=IncidentSource.MANUAL,
            category=IncidentCategory.MANUAL,
            severity=AlertSeverity.LOW,
            title="Manual incident",
        )
        assert created.status == IncidentStatus.OPEN
        assert created.acknowledged_at is None
        assert created.resolved_at is None

    async def test_acknowledge_sets_timestamp(self, _session: AsyncSession) -> None:
        repo = IncidentRepository(_session)
        project_id, env_id = await _make_project_and_environment(_session)
        created = await repo.create(
            project_id=project_id,
            environment_id=env_id,
            alert_rule_id=None,
            source=IncidentSource.MANUAL,
            category=IncidentCategory.MANUAL,
            severity=AlertSeverity.LOW,
            title="Manual incident",
        )
        now = datetime.now(UTC)
        updated = await repo.update_status(
            created.id, status=IncidentStatus.ACKNOWLEDGED, actor_id=None, at=now
        )
        assert updated.status == IncidentStatus.ACKNOWLEDGED
        assert updated.acknowledged_by is None
        assert updated.acknowledged_at is not None
        assert updated.resolved_at is None

    async def test_list_page_filtered_by_status(self, _session: AsyncSession) -> None:
        repo = IncidentRepository(_session)
        project_id, env_id = await _make_project_and_environment(_session)
        await repo.create(
            project_id=project_id,
            environment_id=env_id,
            alert_rule_id=None,
            source=IncidentSource.MANUAL,
            category=IncidentCategory.MANUAL,
            severity=AlertSeverity.LOW,
            title="Open one",
        )
        resolved = await repo.create(
            project_id=project_id,
            environment_id=env_id,
            alert_rule_id=None,
            source=IncidentSource.MANUAL,
            category=IncidentCategory.MANUAL,
            severity=AlertSeverity.LOW,
            title="Resolved one",
        )
        await repo.update_status(
            resolved.id, status=IncidentStatus.RESOLVED, actor_id=None, at=datetime.now(UTC)
        )

        items, total = await repo.list_page_filtered(status=IncidentStatus.OPEN, limit=10, offset=0)
        assert total == 1
        assert items[0].title == "Open one"

    async def test_list_page_filtered_by_project_and_environment(self, _session: AsyncSession) -> None:
        repo = IncidentRepository(_session)
        project_id, env_id = await _make_project_and_environment(_session)
        other_project_id, other_env_id = await _make_project_and_environment(_session)
        await repo.create(
            project_id=project_id,
            environment_id=env_id,
            alert_rule_id=None,
            source=IncidentSource.MANUAL,
            category=IncidentCategory.MANUAL,
            severity=AlertSeverity.LOW,
            title="In scope",
        )
        await repo.create(
            project_id=other_project_id,
            environment_id=other_env_id,
            alert_rule_id=None,
            source=IncidentSource.MANUAL,
            category=IncidentCategory.MANUAL,
            severity=AlertSeverity.LOW,
            title="Out of scope",
        )
        items, total = await repo.list_page_filtered(project_id=project_id, limit=10, offset=0)
        assert total == 1
        assert items[0].title == "In scope"


class TestUpdatesRaiseNotFoundForMissingRows:
    async def test_loki_config(self, _session: AsyncSession) -> None:
        with pytest.raises(LokiConfigNotFound):
            await LokiConfigRepository(_session).update_by_environment_id(
                uuid4(),
                endpoint_url="http://loki:3100",
                tenant_id=None,
                auth_type=LokiAuthType.NONE,
                credential=None,
                default_query='{job="app"}',
                default_range_minutes=15,
            )

    async def test_alert_rule_set_cf_policy_id(self, _session: AsyncSession) -> None:
        with pytest.raises(AlertRuleNotFound):
            await AlertRuleRepository(_session).set_cf_policy_id(uuid4(), cf_policy_id="p")

    async def test_alert_rule_update(self, _session: AsyncSession) -> None:
        with pytest.raises(AlertRuleNotFound):
            await AlertRuleRepository(_session).update(uuid4(), name="x")

    async def test_incident(self, _session: AsyncSession) -> None:
        with pytest.raises(IncidentNotFound):
            await IncidentRepository(_session).update_status(
                uuid4(), status=IncidentStatus.ACKNOWLEDGED, actor_id=None, at=datetime.now(UTC)
            )
