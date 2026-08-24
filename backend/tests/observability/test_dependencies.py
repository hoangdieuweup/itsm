"""Unit tests for observability's webhook-secret verification dependencies —
no I/O, pure hmac.compare_digest checks against a fake CloudflareApi / the
module's own settings singleton."""

from uuid import uuid4

import pytest

from app.modules.observability.config import observability_settings
from app.modules.observability.dependencies import (
    verify_cloudflare_webhook_secret,
    verify_loki_webhook_secret,
)
from app.modules.observability.exceptions import InvalidWebhookSecret


class FakeCloudflareApiForWebhook:
    def __init__(self, secrets: dict) -> None:
        self._secrets = secrets

    async def get_webhook_secret(self, account_id):
        return self._secrets.get(account_id)


class TestVerifyCloudflareWebhookSecret:
    async def test_missing_header_rejects(self) -> None:
        account_id = uuid4()
        with pytest.raises(InvalidWebhookSecret):
            await verify_cloudflare_webhook_secret(
                cloudflare_account_id=account_id,
                cf_webhook_auth=None,
                cloudflare_api=FakeCloudflareApiForWebhook({account_id: "real-secret"}),
            )

    async def test_wrong_secret_rejects(self) -> None:
        account_id = uuid4()
        with pytest.raises(InvalidWebhookSecret):
            await verify_cloudflare_webhook_secret(
                cloudflare_account_id=account_id,
                cf_webhook_auth="wrong",
                cloudflare_api=FakeCloudflareApiForWebhook({account_id: "real-secret"}),
            )

    async def test_unregistered_account_rejects(self) -> None:
        account_id = uuid4()
        with pytest.raises(InvalidWebhookSecret):
            await verify_cloudflare_webhook_secret(
                cloudflare_account_id=account_id,
                cf_webhook_auth="anything",
                cloudflare_api=FakeCloudflareApiForWebhook({}),
            )

    async def test_correct_secret_passes(self) -> None:
        account_id = uuid4()
        await verify_cloudflare_webhook_secret(
            cloudflare_account_id=account_id,
            cf_webhook_auth="real-secret",
            cloudflare_api=FakeCloudflareApiForWebhook({account_id: "real-secret"}),
        )  # no raise


class TestVerifyLokiWebhookSecret:
    async def test_missing_header_rejects(self, monkeypatch) -> None:
        monkeypatch.setattr(observability_settings, "LOKI_WEBHOOK_SECRET", "real-secret")
        with pytest.raises(InvalidWebhookSecret):
            await verify_loki_webhook_secret(authorization=None)

    async def test_wrong_bearer_rejects(self, monkeypatch) -> None:
        monkeypatch.setattr(observability_settings, "LOKI_WEBHOOK_SECRET", "real-secret")
        with pytest.raises(InvalidWebhookSecret):
            await verify_loki_webhook_secret(authorization="Bearer wrong")

    async def test_unconfigured_secret_rejects(self, monkeypatch) -> None:
        monkeypatch.setattr(observability_settings, "LOKI_WEBHOOK_SECRET", "")
        with pytest.raises(InvalidWebhookSecret):
            await verify_loki_webhook_secret(authorization="Bearer ")

    async def test_correct_bearer_passes(self, monkeypatch) -> None:
        monkeypatch.setattr(observability_settings, "LOKI_WEBHOOK_SECRET", "real-secret")
        await verify_loki_webhook_secret(authorization="Bearer real-secret")  # no raise
