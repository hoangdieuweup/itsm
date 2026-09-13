"""Integration tests for the notifications repository — real Postgres via a
locally scoped session fixture, mirroring tests/observability/test_repository.py's
`_session` pattern. This is the one place secret encryption (on write) and
masking (on read) actually happens."""

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.crypto import FernetCodec
from app.modules.notifications.config import notifications_settings
from app.modules.notifications.constants import NotificationChannelType
from app.modules.notifications.exceptions import NotificationChannelNotFound
from app.modules.notifications.models import NotificationChannel
from app.modules.notifications.repository import NotificationChannelRepository
from app.modules.projects.models import Environment, Project

TEST_FERNET_KEY = "kL8Zx3vQ9mN2pR7wT4yU6bC1dF5gH0jK3lM6nO9pQ2s="


@pytest.fixture(autouse=True)
def _fernet_key(monkeypatch) -> None:
    monkeypatch.setattr(notifications_settings, "FERNET_KEY", TEST_FERNET_KEY)


@pytest.fixture
async def _session(engine) -> AsyncIterator[AsyncSession]:
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()

    async with engine.begin() as conn:
        await conn.execute(delete(NotificationChannel))
        await conn.execute(delete(Environment))
        await conn.execute(delete(Project))


async def _make_project(session: AsyncSession) -> Project:
    project = Project(name=f"P-{uuid4()}")
    session.add(project)
    await session.flush()
    return project


class TestNotificationChannelRepository:
    async def test_create_encrypts_telegram_bot_token(self, _session: AsyncSession) -> None:
        project = await _make_project(_session)
        repo = NotificationChannelRepository(_session)

        created = await repo.create(
            project_id=project.id,
            environment_id=None,
            type=NotificationChannelType.TELEGRAM,
            name="Ops",
            config={"bot_token": "raw-token", "chat_id": "1"},
        )

        assert created.config == {"chat_id": "1", "has_bot_token": True}

        raw_row = await _session.get(NotificationChannel, created.id)
        assert raw_row.config["bot_token"] != "raw-token"
        assert FernetCodec.decrypt(raw_row.config["bot_token"], key=TEST_FERNET_KEY) == "raw-token"

    async def test_create_encrypts_base_vn_webhook_url(self, _session: AsyncSession) -> None:
        project = await _make_project(_session)
        repo = NotificationChannelRepository(_session)

        created = await repo.create(
            project_id=project.id,
            environment_id=None,
            type=NotificationChannelType.BASE_VN,
            name="Base Alerts",
            config={"webhook_url": "http://base.vn/x", "bot_name": "Alerts", "message_template": ""},
        )

        assert created.config == {"bot_name": "Alerts", "message_template": "", "has_webhook_url": True}
        raw_row = await _session.get(NotificationChannel, created.id)
        assert raw_row.config["webhook_url"] != "http://base.vn/x"

    async def test_email_config_has_no_masking(self, _session: AsyncSession) -> None:
        project = await _make_project(_session)
        repo = NotificationChannelRepository(_session)

        created = await repo.create(
            project_id=project.id,
            environment_id=None,
            type=NotificationChannelType.EMAIL,
            name="Team",
            config={"recipients": ["a@b.com"]},
        )
        assert created.config == {"recipients": ["a@b.com"]}

    async def test_get_config_ciphertext_fields_returns_raw_secrets(self, _session: AsyncSession) -> None:
        project = await _make_project(_session)
        repo = NotificationChannelRepository(_session)
        created = await repo.create(
            project_id=project.id,
            environment_id=None,
            type=NotificationChannelType.TELEGRAM,
            name="Ops",
            config={"bot_token": "raw-token", "chat_id": "1"},
        )

        fields = await repo.get_config_ciphertext_fields(created.id)
        assert FernetCodec.decrypt(fields["bot_token"], key=TEST_FERNET_KEY) == "raw-token"
        assert fields["chat_id"] == "1"

    async def test_list_for_project_filters_by_environment(self, _session: AsyncSession) -> None:
        project = await _make_project(_session)
        dev = Environment(project_id=project.id, type="dev", name="Dev", base_url=None)
        staging = Environment(project_id=project.id, type="staging", name="Staging", base_url=None)
        _session.add_all([dev, staging])
        await _session.flush()
        repo = NotificationChannelRepository(_session)
        await repo.create(
            project_id=project.id,
            environment_id=None,
            type=NotificationChannelType.EMAIL,
            name="All-env",
            config={"recipients": ["a@b.com"]},
        )
        await repo.create(
            project_id=project.id,
            environment_id=dev.id,
            type=NotificationChannelType.EMAIL,
            name="Dev-only",
            config={"recipients": ["b@b.com"]},
        )
        await repo.create(
            project_id=project.id,
            environment_id=staging.id,
            type=NotificationChannelType.EMAIL,
            name="Staging-only",
            config={"recipients": ["c@b.com"]},
        )

        all_channels = await repo.list_for_project(project.id, environment_id=None)
        assert len(all_channels) == 3

        # Filtering by "dev" includes the project-wide (null environment_id)
        # channel too — null means "applies to every environment", so a
        # dev-scoped view must show it alongside dev's own channel, while
        # excluding the unrelated staging-only one.
        dev_channels = await repo.list_for_project(project.id, environment_id=dev.id)
        assert {c.name for c in dev_channels} == {"All-env", "Dev-only"}

    async def test_update_re_encrypts_new_secret(self, _session: AsyncSession) -> None:
        project = await _make_project(_session)
        repo = NotificationChannelRepository(_session)
        created = await repo.create(
            project_id=project.id,
            environment_id=None,
            type=NotificationChannelType.TELEGRAM,
            name="Ops",
            config={"bot_token": "old-token", "chat_id": "1"},
        )

        updated = await repo.update(
            created.id, name=None, config={"bot_token": "new-token", "chat_id": "1"}, is_active=None
        )

        assert updated.config == {"chat_id": "1", "has_bot_token": True}
        fields = await repo.get_config_ciphertext_fields(created.id)
        assert FernetCodec.decrypt(fields["bot_token"], key=TEST_FERNET_KEY) == "new-token"

    async def test_delete_removes_row(self, _session: AsyncSession) -> None:
        project = await _make_project(_session)
        repo = NotificationChannelRepository(_session)
        created = await repo.create(
            project_id=project.id,
            environment_id=None,
            type=NotificationChannelType.EMAIL,
            name="Team",
            config={"recipients": ["a@b.com"]},
        )

        await repo.delete(created.id)

        assert await repo.get_by_id(created.id) is None


class TestNotificationChannelRepositoryMissingRows:
    async def test_update_raises_channel_not_found(self, _session: AsyncSession) -> None:
        with pytest.raises(NotificationChannelNotFound):
            await NotificationChannelRepository(_session).update(
                uuid4(), name="x", config=None, is_active=None
            )
