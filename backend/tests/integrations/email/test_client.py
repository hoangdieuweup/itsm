"""Unit tests for app.integrations.email.client — no real SMTP server,
aiosmtplib.send is patched directly."""

from unittest.mock import AsyncMock, patch

import pytest
from aiosmtplib.errors import SMTPAuthenticationError, SMTPConnectError, SMTPRecipientsRefused

from app.integrations.email.client import EmailClient
from app.integrations.email.exceptions import EmailApiUnavailable, EmailRejected, InvalidEmailCredential


class TestSend:
    async def test_builds_message_and_calls_aiosmtplib(self) -> None:
        with patch("app.integrations.email.client.aiosmtplib.send", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = ({}, "OK")
            await EmailClient().send(recipients=["a@b.com"], subject="Test", body="Hello")

        assert mock_send.await_count == 1
        message = mock_send.await_args.args[0]
        kwargs = mock_send.await_args.kwargs
        assert message["Subject"] == "Test"
        assert message["To"] == "a@b.com"
        assert kwargs["recipients"] == ["a@b.com"]

    async def test_auth_error_raises_invalid_credential(self) -> None:
        with patch("app.integrations.email.client.aiosmtplib.send", new_callable=AsyncMock) as mock_send:
            mock_send.side_effect = SMTPAuthenticationError(535, "bad creds")
            with pytest.raises(InvalidEmailCredential):
                await EmailClient().send(recipients=["a@b.com"], subject="Test", body="Hello")

    async def test_recipients_refused_raises_rejected(self) -> None:
        with patch("app.integrations.email.client.aiosmtplib.send", new_callable=AsyncMock) as mock_send:
            mock_send.side_effect = SMTPRecipientsRefused([])
            with pytest.raises(EmailRejected):
                await EmailClient().send(recipients=["a@b.com"], subject="Test", body="Hello")

    async def test_connect_error_raises_unavailable(self) -> None:
        with patch("app.integrations.email.client.aiosmtplib.send", new_callable=AsyncMock) as mock_send:
            mock_send.side_effect = SMTPConnectError("refused")
            with pytest.raises(EmailApiUnavailable):
                await EmailClient().send(recipients=["a@b.com"], subject="Test", body="Hello")


class TestHtmlAlternative:
    async def test_sends_both_parts_with_text_first(self) -> None:
        """A client that can't render HTML must still find something to show, so the
        text part is set before the HTML alternative is added."""
        with patch("app.integrations.email.client.aiosmtplib.send", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = ({}, "OK")
            await EmailClient().send(
                recipients=["a@b.com"], subject="Test", body="Xin chào", html="<p>Xin chào</p>"
            )

        message = mock_send.await_args.args[0]
        assert message.get_content_type() == "multipart/alternative"
        assert [part.get_content_subtype() for part in message.iter_parts()] == ["plain", "html"]

    async def test_stays_single_part_without_html(self) -> None:
        with patch("app.integrations.email.client.aiosmtplib.send", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = ({}, "OK")
            await EmailClient().send(recipients=["a@b.com"], subject="Test", body="Xin chào")

        message = mock_send.await_args.args[0]
        assert message.get_content_type() == "text/plain"
