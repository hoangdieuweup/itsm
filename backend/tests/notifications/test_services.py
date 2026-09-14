"""Unit tests for the notifications services — Fakes throughout, mirroring
tests/observability/test_services.py's exact Fake shape."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.integrations.telegram.exceptions import TelegramApiUnavailable
from app.modules.notifications.constants import NotificationChannelType
from app.modules.notifications.exceptions import (
    InvalidChannelConfig,
    NotificationChannelNotFound,
    NotificationsProjectNotFound,
    UnsupportedChannelType,
)
from app.modules.notifications.repository import AbstractNotificationChannelRepository
from app.modules.notifications.schemas import NotificationChannelRead
from app.modules.notifications.services.create_channel import CreateNotificationChannel
from app.modules.notifications.services.delete_channel import DeleteNotificationChannel
from app.modules.notifications.services.get_channel import GetNotificationChannel
from app.modules.notifications.services.test_send_channel import TestSendNotificationChannel
from app.modules.notifications.services.update_channel import UpdateNotificationChannel
from app.modules.notifications.uow import AbstractNotificationsUnitOfWork
from app.modules.users.public import UserRead

ACTOR_ID = uuid4()
ACTOR_EMAIL = "actor@example.com"


def _actor() -> UserRead:
    return UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)


class FakeChannelRepo(AbstractNotificationChannelRepository):
    def __init__(self) -> None:
        self._rows: dict[UUID, NotificationChannelRead] = {}
        self._raw_config: dict[UUID, dict] = {}

    async def get_by_id(self, entity_id):
        return self._rows.get(entity_id)

    async def list_page(self, limit, offset):
        raise NotImplementedError

    async def list_for_project(self, project_id, *, environment_id):
        return [c for c in self._rows.values() if c.project_id == project_id]

    async def create(self, *, project_id, environment_id, type, name, config):
        channel_id = uuid4()
        self._raw_config[channel_id] = dict(config)
        masked = {k: v for k, v in config.items() if k not in ("bot_token", "webhook_url")}
        channel = NotificationChannelRead(
            id=channel_id,
            project_id=project_id,
            environment_id=environment_id,
            type=type,
            name=name,
            config=masked,
            is_active=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self._rows[channel_id] = channel
        return channel

    async def update(self, channel_id, *, name, config, is_active):
        existing = self._rows[channel_id]
        updates = {k: v for k, v in {"name": name, "is_active": is_active}.items() if v is not None}
        updated = existing.model_copy(update=updates)
        self._rows[channel_id] = updated
        return updated

    async def delete(self, channel_id):
        self._rows.pop(channel_id, None)
        self._raw_config.pop(channel_id, None)

    async def get_dispatch_config(self, channel_id):
        return self._raw_config.get(channel_id, {})


class FakeNotificationsUnitOfWork(AbstractNotificationsUnitOfWork):
    def __init__(self) -> None:
        self.channels = FakeChannelRepo()
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        pass


class FakeProjectsApi:
    def __init__(self, projects: dict | None = None, environments: dict | None = None) -> None:
        self._projects = projects or {}
        self._environments = environments or {}

    async def get_project_by_id(self, project_id):
        return self._projects.get(project_id)

    async def get_environment_by_id(self, environment_id):
        return self._environments.get(environment_id)


class FakeAuditApi:
    def __init__(self) -> None:
        self.events: list[dict] = []

    async def log_event(self, **kwargs) -> None:
        self.events.append(kwargs)


class FakeTelegramClient:
    def __init__(self, raises: Exception | None = None) -> None:
        self._raises = raises
        self.calls: list[dict] = []

    async def send_message(self, **kwargs) -> None:
        self.calls.append(kwargs)
        if self._raises is not None:
            raise self._raises


class TestCreateNotificationChannel:
    async def test_rejects_unknown_project(self) -> None:
        uow = FakeNotificationsUnitOfWork()
        use_case = CreateNotificationChannel(uow, FakeProjectsApi(), FakeAuditApi())
        with pytest.raises(NotificationsProjectNotFound):
            await use_case.execute(
                project_id=uuid4(),
                environment_id=None,
                type=NotificationChannelType.EMAIL,
                name="Team",
                config={"recipients": ["a@b.com"]},
                actor=_actor(),
            )

    async def test_rejects_invalid_config_for_type(self) -> None:
        project_id = uuid4()
        uow = FakeNotificationsUnitOfWork()
        use_case = CreateNotificationChannel(uow, FakeProjectsApi({project_id: object()}), FakeAuditApi())
        with pytest.raises(InvalidChannelConfig):
            await use_case.execute(
                project_id=project_id,
                environment_id=None,
                type=NotificationChannelType.TELEGRAM,
                name="Ops",
                config={},
                actor=_actor(),
            )

    async def test_creates_and_audits(self) -> None:
        project_id = uuid4()
        uow = FakeNotificationsUnitOfWork()
        audit_api = FakeAuditApi()
        use_case = CreateNotificationChannel(uow, FakeProjectsApi({project_id: object()}), audit_api)

        channel = await use_case.execute(
            project_id=project_id,
            environment_id=None,
            type=NotificationChannelType.EMAIL,
            name="Team",
            config={"recipients": ["a@b.com"]},
            actor=_actor(),
        )

        assert channel.name == "Team"
        assert uow.commits == 1
        assert len(audit_api.events) == 1


class TestUpdateNotificationChannel:
    async def test_raises_not_found(self) -> None:
        uow = FakeNotificationsUnitOfWork()
        use_case = UpdateNotificationChannel(uow, FakeAuditApi())
        with pytest.raises(NotificationChannelNotFound):
            await use_case.execute(uuid4(), actor=_actor())

    async def test_updates_name_and_validates_new_config(self) -> None:
        project_id = uuid4()
        uow = FakeNotificationsUnitOfWork()
        create_use_case = CreateNotificationChannel(
            uow, FakeProjectsApi({project_id: object()}), FakeAuditApi()
        )
        channel = await create_use_case.execute(
            project_id=project_id,
            environment_id=None,
            type=NotificationChannelType.EMAIL,
            name="Team",
            config={"recipients": ["a@b.com"]},
            actor=_actor(),
        )

        use_case = UpdateNotificationChannel(uow, FakeAuditApi())
        updated = await use_case.execute(channel.id, name="Renamed", actor=_actor())

        assert updated.name == "Renamed"

    async def test_rejects_invalid_config_on_update(self) -> None:
        project_id = uuid4()
        uow = FakeNotificationsUnitOfWork()
        create_use_case = CreateNotificationChannel(
            uow, FakeProjectsApi({project_id: object()}), FakeAuditApi()
        )
        channel = await create_use_case.execute(
            project_id=project_id,
            environment_id=None,
            type=NotificationChannelType.TELEGRAM,
            name="Ops",
            config={"bot_token": "tok", "chat_id": "1"},
            actor=_actor(),
        )

        use_case = UpdateNotificationChannel(uow, FakeAuditApi())
        with pytest.raises(InvalidChannelConfig):
            await use_case.execute(channel.id, config={}, actor=_actor())


class TestDeleteNotificationChannel:
    async def test_raises_not_found(self) -> None:
        uow = FakeNotificationsUnitOfWork()
        use_case = DeleteNotificationChannel(uow, FakeAuditApi())
        with pytest.raises(NotificationChannelNotFound):
            await use_case.execute(uuid4(), actor=_actor())

    async def test_deletes_and_audits(self) -> None:
        project_id = uuid4()
        uow = FakeNotificationsUnitOfWork()
        create_use_case = CreateNotificationChannel(
            uow, FakeProjectsApi({project_id: object()}), FakeAuditApi()
        )
        channel = await create_use_case.execute(
            project_id=project_id,
            environment_id=None,
            type=NotificationChannelType.EMAIL,
            name="Team",
            config={"recipients": ["a@b.com"]},
            actor=_actor(),
        )
        audit_api = FakeAuditApi()
        use_case = DeleteNotificationChannel(uow, audit_api)

        await use_case.execute(channel.id, actor=_actor())

        assert await uow.channels.get_by_id(channel.id) is None
        assert len(audit_api.events) == 1


class TestGetNotificationChannel:
    async def test_raises_not_found(self) -> None:
        uow = FakeNotificationsUnitOfWork()
        use_case = GetNotificationChannel(uow)
        with pytest.raises(NotificationChannelNotFound):
            await use_case.execute(uuid4())


class TestTestSendNotificationChannel:
    async def test_raises_not_found(self) -> None:
        uow = FakeNotificationsUnitOfWork()
        use_case = TestSendNotificationChannel(
            uow,
            telegram_client=FakeTelegramClient(),
            email_client=None,
            base_vn_client=None,
            audit_api=FakeAuditApi(),
        )
        with pytest.raises(NotificationChannelNotFound):
            await use_case.execute(uuid4(), message=None, actor=_actor())

    async def test_other_type_raises_unsupported(self) -> None:
        project_id = uuid4()
        uow = FakeNotificationsUnitOfWork()
        create_use_case = CreateNotificationChannel(
            uow, FakeProjectsApi({project_id: object()}), FakeAuditApi()
        )
        channel = await create_use_case.execute(
            project_id=project_id,
            environment_id=None,
            type=NotificationChannelType.OTHER,
            name="Future",
            config={"whatever": "x"},
            actor=_actor(),
        )
        use_case = TestSendNotificationChannel(
            uow,
            telegram_client=FakeTelegramClient(),
            email_client=None,
            base_vn_client=None,
            audit_api=FakeAuditApi(),
        )
        with pytest.raises(UnsupportedChannelType):
            await use_case.execute(channel.id, message=None, actor=_actor())

    async def test_telegram_dispatches_to_client_and_decrypts_token(self) -> None:
        project_id = uuid4()
        uow = FakeNotificationsUnitOfWork()
        create_use_case = CreateNotificationChannel(
            uow, FakeProjectsApi({project_id: object()}), FakeAuditApi()
        )
        channel = await create_use_case.execute(
            project_id=project_id,
            environment_id=None,
            type=NotificationChannelType.TELEGRAM,
            name="Ops",
            config={"bot_token": "real-token", "chat_id": "chat-1"},
            actor=_actor(),
        )
        telegram_client = FakeTelegramClient()
        audit_api = FakeAuditApi()
        use_case = TestSendNotificationChannel(
            uow, telegram_client=telegram_client, email_client=None, base_vn_client=None, audit_api=audit_api
        )

        await use_case.execute(channel.id, message="hello", actor=_actor())

        assert telegram_client.calls[0]["bot_token"] == "real-token"
        assert telegram_client.calls[0]["chat_id"] == "chat-1"
        assert telegram_client.calls[0]["text"] == "hello"
        assert any(e["action"] == "NOTIFICATION_CHANNEL_TEST_SENT" for e in audit_api.events)

    async def test_telegram_send_failure_still_audits(self) -> None:
        project_id = uuid4()
        uow = FakeNotificationsUnitOfWork()
        create_use_case = CreateNotificationChannel(
            uow, FakeProjectsApi({project_id: object()}), FakeAuditApi()
        )
        channel = await create_use_case.execute(
            project_id=project_id,
            environment_id=None,
            type=NotificationChannelType.TELEGRAM,
            name="Ops",
            config={"bot_token": "real-token", "chat_id": "chat-1"},
            actor=_actor(),
        )
        audit_api = FakeAuditApi()
        use_case = TestSendNotificationChannel(
            uow,
            telegram_client=FakeTelegramClient(raises=TelegramApiUnavailable()),
            email_client=None,
            base_vn_client=None,
            audit_api=audit_api,
        )

        with pytest.raises(TelegramApiUnavailable):
            await use_case.execute(channel.id, message="hello", actor=_actor())

        assert any(e["action"] == "NOTIFICATION_CHANNEL_TEST_SENT" for e in audit_api.events)
