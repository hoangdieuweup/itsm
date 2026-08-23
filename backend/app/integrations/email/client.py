"""SMTP client. Talks to the app-wide SMTP relay only — no database, no
business logic."""

from email.message import EmailMessage

import aiosmtplib
from aiosmtplib.errors import (
    SMTPAuthenticationError,
    SMTPDataError,
    SMTPException,
    SMTPRecipientRefused,
    SMTPRecipientsRefused,
    SMTPSenderRefused,
)

from app.core.base.markers import integration
from app.integrations.email.config import email_settings
from app.integrations.email.exceptions import EmailApiUnavailable, EmailRejected, InvalidEmailCredential


class EmailClient:
    """Sends via the app-wide SMTP relay configured in EmailIntegrationConfig.
    One instance per request, built in dependencies.py."""

    @integration
    async def send(self, *, recipients: list[str], subject: str, body: str) -> None:
        message = EmailMessage()
        message["From"] = email_settings.SMTP_FROM_ADDRESS
        message["To"] = ", ".join(recipients)
        message["Subject"] = subject
        message.set_content(body)

        try:
            await aiosmtplib.send(
                message,
                recipients=recipients,
                hostname=email_settings.SMTP_HOST,
                port=email_settings.SMTP_PORT,
                username=email_settings.SMTP_USERNAME or None,
                password=email_settings.SMTP_PASSWORD or None,
                start_tls=email_settings.SMTP_START_TLS,
            )
        except SMTPAuthenticationError as exc:
            raise InvalidEmailCredential() from exc
        except (SMTPRecipientRefused, SMTPRecipientsRefused, SMTPSenderRefused, SMTPDataError) as exc:
            raise EmailRejected() from exc
        except (SMTPException, OSError) as exc:
            raise EmailApiUnavailable() from exc
