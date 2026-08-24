import pytest

from app.modules.notifications.constants import NotificationChannelType
from app.modules.notifications.exceptions import InvalidChannelConfig
from app.modules.notifications.rules import NotificationRules


class TestValidateConfig:
    def test_email_requires_recipients(self) -> None:
        with pytest.raises(InvalidChannelConfig):
            NotificationRules.validate_config(NotificationChannelType.EMAIL, {})

    def test_email_accepts_recipients_list(self) -> None:
        NotificationRules.validate_config(NotificationChannelType.EMAIL, {"recipients": ["a@b.com"]})

    def test_telegram_requires_bot_token_and_chat_id(self) -> None:
        with pytest.raises(InvalidChannelConfig):
            NotificationRules.validate_config(NotificationChannelType.TELEGRAM, {"chat_id": "1"})

    def test_telegram_accepts_full_config(self) -> None:
        NotificationRules.validate_config(
            NotificationChannelType.TELEGRAM, {"bot_token": "tok", "chat_id": "1"}
        )

    def test_base_vn_requires_webhook_url(self) -> None:
        with pytest.raises(InvalidChannelConfig):
            NotificationRules.validate_config(NotificationChannelType.BASE_VN, {"bot_name": "x"})

    def test_base_vn_accepts_full_config(self) -> None:
        NotificationRules.validate_config(
            NotificationChannelType.BASE_VN,
            {"webhook_url": "http://base.vn/x", "bot_name": "Alerts", "message_template": ""},
        )

    def test_other_accepts_anything(self) -> None:
        NotificationRules.validate_config(NotificationChannelType.OTHER, {"whatever": "goes"})


class TestRenderBaseContent:
    def test_substitutes_placeholder(self) -> None:
        result = NotificationRules.render_base_content("Alert: {message}", "disk full")
        assert result == "Alert: disk full"

    def test_static_template_appends_message(self) -> None:
        result = NotificationRules.render_base_content("New alert", "disk full")
        assert result == "New alert disk full"

    def test_empty_template_uses_raw_message(self) -> None:
        assert NotificationRules.render_base_content("", "disk full") == "disk full"
