"""Pure business rules for the notifications module — no I/O."""

from app.core.base.markers import rule
from app.modules.notifications.constants import NotificationChannelType
from app.modules.notifications.exceptions import InvalidChannelConfig


class NotificationRules:
    @staticmethod
    @rule
    def validate_config(channel_type: NotificationChannelType, config: dict) -> None:
        """Raises InvalidChannelConfig if config is missing required fields
        for channel_type. OTHER has no defined required fields by design —
        reserved for a future channel."""
        if channel_type == NotificationChannelType.EMAIL:
            if not config.get("recipients"):
                raise InvalidChannelConfig(message="EMAIL config requires a non-empty recipients list")
        elif channel_type == NotificationChannelType.TELEGRAM:
            if not config.get("bot_token") or not config.get("chat_id"):
                raise InvalidChannelConfig(message="TELEGRAM config requires bot_token and chat_id")
        elif channel_type == NotificationChannelType.BASE_VN:
            if not config.get("webhook_url"):
                raise InvalidChannelConfig(message="BASE_VN config requires webhook_url")

    @staticmethod
    @rule
    def render_base_content(template: str, message: str) -> str:
        """Substitute {message} if present; static text gets the message
        appended; empty template falls back to the raw message."""
        if not template:
            return message
        if "{message}" in template:
            return template.replace("{message}", message)
        return f"{template} {message}"
