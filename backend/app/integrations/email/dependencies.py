"""Dependency wiring for the email integration."""

from app.integrations.email.client import EmailClient


async def get_email_client() -> EmailClient:
    """Provide the SMTP email client."""
    return EmailClient()
