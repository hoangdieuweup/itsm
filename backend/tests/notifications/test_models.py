import uuid

from app.modules.notifications.constants import NotificationChannelType
from app.modules.notifications.models import NotificationChannel


def test_notification_channel_model_columns():
    channel = NotificationChannel(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        environment_id=None,
        type=NotificationChannelType.TELEGRAM,
        name="Ops Alerts",
        config={"chat_id": "1", "bot_token": "ciphertext"},
        is_active=True,
    )
    assert channel.type == NotificationChannelType.TELEGRAM
    assert channel.is_active is True
