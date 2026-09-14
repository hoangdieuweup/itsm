"""Unit tests for app.modules.notifications.public — the facade other
modules (observability, in Phase 9) reach notifications through."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.integrations.email.config import email_settings
from app.modules.notifications.constants import NotificationChannelType, NotificationKind
from app.modules.notifications.exceptions import NotificationChannelNotFound
from app.modules.notifications.public import NotificationsApi
from app.modules.notifications.schemas import NotificationChannelRead, NotificationEvent


class FakeChannelsRepo:
    def __init__(self, channel=None, raw_config=None) -> None:
        self._channel = channel
        self._raw_config = raw_config or {}

    async def get_by_id(self, channel_id):
        return self._channel

    async def get_dispatch_config(self, channel_id):
        return self._raw_config


class FakeUow:
    def __init__(self, channels) -> None:
        self.channels = channels


class FakeEmailClient:
    def __init__(self) -> None:
        self.sent = []

    async def send(self, *, recipients, subject, body, html=None):
        self.sent.append((recipients, subject, body, html))


def _event() -> NotificationEvent:
    return NotificationEvent(
        kind=NotificationKind.INCIDENT_DETECTED,
        title="DDoS trên example.com",
        severity="CRITICAL",
    )


def _email_channel(channel_id) -> NotificationChannelRead:
    return NotificationChannelRead(
        id=channel_id,
        project_id=uuid4(),
        environment_id=None,
        type=NotificationChannelType.EMAIL,
        name="Team",
        config={"recipients": ["a@b.com"]},
        is_active=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.fixture(autouse=True)
def _smtp_configured(monkeypatch) -> None:
    """dispatch() refuses an EMAIL channel when no relay is configured;
    these tests exercise the dispatch path itself, not that guard."""
    monkeypatch.setattr(email_settings, "SMTP_HOST", "smtp.test.local")


class TestDispatch:
    async def test_raises_not_found_for_missing_channel(self) -> None:
        api = NotificationsApi(
            FakeUow(FakeChannelsRepo(channel=None)),
            telegram_client=None,
            email_client=None,
            base_vn_client=None,
        )
        with pytest.raises(NotificationChannelNotFound):
            await api.dispatch(uuid4(), _event())

    async def test_dispatches_to_email(self) -> None:
        channel = _email_channel(uuid4())
        email_client = FakeEmailClient()
        api = NotificationsApi(
            FakeUow(FakeChannelsRepo(channel=channel, raw_config={"recipients": ["a@b.com"]})),
            telegram_client=None,
            email_client=email_client,
            base_vn_client=None,
        )
        await api.dispatch(channel.id, _event())

        recipients, subject, body, html = email_client.sent[0]
        assert recipients == ["a@b.com"]
        assert "DDoS trên example.com" in subject
        assert "DDoS trên example.com" in body
        assert "<" not in body
        assert "<table" in html
