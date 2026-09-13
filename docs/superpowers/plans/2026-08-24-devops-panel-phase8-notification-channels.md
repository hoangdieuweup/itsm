# DevOps Panel Phase 8 — Notification Channels

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user create notification channels (Email/Base.vn/Telegram/Other) scoped to a project (optionally narrowed to one environment), with per-type secrets encrypted, and send a test message through any real channel to confirm delivery — independent of Phase 9's alert-routing, which reuses these channels once it exists.

**Architecture:** 3 new integration leaves (`app/integrations/{email,telegram,base_vn}/`), each a single-purpose `send`-shaped client, no shared "notification" abstraction across them. New `app/modules/notifications/` module (full tier) owns `notification_channels`, encrypts per-type secret sub-fields individually within the JSONB `config` column (not the whole blob), and dispatches test-sends to the right client based on `type`. RBAC: plain CRUD on a new `notification_channel` resource, no 2-layer ACL. Frontend: `entities/notification-channel/` (Phase 9 needs it for the alert-rule multiselect) + `modules/notifications/` rendered as a new section on the existing project detail page.

**Tech Stack:** `aiosmtplib==5.1.2` (new dependency, async SMTP), `httpx` (already present, used for Telegram Bot API + Base.vn webhook — both plain HTTP POST).

**Spec:** The "Phase 8 — Detailed Plan: Notification channels" section of `/Users/hoangdieu/.claude/plans/rosy-juggling-pine.md` (9 numbered Decisions). Also `docs/tasks/devops-control-panel-schema.md` §5 (per-type `config` field shapes — read in full, source of truth for exact field names).

## Global Constraints

- Per-secret encryption within `config` JSONB, not whole-blob encryption: `TELEGRAM.bot_token`, `BASE_VN.webhook_url` are individually Fernet-encrypted; other fields (`recipients`, `chat_id`, `bot_name`, `message_template`) stay plaintext in the same JSON object (Decision #1).
- `NotificationChannelRead.config` is a service-built, type-appropriate masked view — never the raw stored JSON (Decision #2).
- `EMAIL` sends via one app-wide SMTP relay (`EmailIntegrationConfig`, env-driven), not per-channel credentials (Decision #3).
- `BASE_VN.message_template` supports one `{message}` placeholder; empty template falls back to the raw message (Decision #4).
- Test-send (`POST /notification-channels/{id}/test-send`) is gated at `notification_channel:update`, not `:read` (Decision #5).
- Each client is single-purpose: `EmailClient.send`, `TelegramClient.send_message`, `BaseVnClient.send` — `TestSendNotificationChannel` is the only place that dispatches on `type` (Decision #6).
- Error mapping per integration: `*ApiUnavailable` / `Invalid*Credential` (Email, Telegram only) / `*Rejected`, mirroring Loki/Cloudflare's established 3-way (2-way for Base.vn, no credential concept) pattern (Decision #7).
- `project_id` required, `environment_id` optional (null = every environment of the project), both validated via `ProjectsApi` (Decision #8).
- `OTHER` is fully CRUD-able but `TestSendNotificationChannel` raises `UnsupportedChannelType` for it — not a silent success (Decision #9).
- Router thinness (rule #10) and class-scoped constants (rule #16) apply throughout.

---

## Task 1: `app/integrations/email/` — SMTP client

**Files:**
- Create: `backend/app/integrations/email/{__init__,config,constants,exceptions,client}.py`
- Test: `backend/tests/integrations/email/test_client.py`

**Interfaces:**
- Produces: `email_settings: EmailIntegrationConfig`, `EmailApiUnavailable`, `InvalidEmailCredential`, `EmailRejected`, `EmailClient.send(self, *, recipients: list[str], subject: str, body: str) -> None`.

- [ ] **Step 1: Write the failing tests**

`aiosmtplib` ships a way to inject a custom SMTP class for testing; the most faithful approach without a real SMTP server is patching `aiosmtplib.send` itself (a single top-level function this client calls directly) — read `aiosmtplib`'s real `send()` signature first (`inspect.signature(aiosmtplib.send)`, already confirmed this session: `send(message, /, *, sender=None, recipients=None, hostname='localhost', port=None, username=None, password=None, ..., start_tls=None, ...)`). Use `unittest.mock.patch("app.integrations.email.client.aiosmtplib.send", ...)`.

```python
# backend/tests/integrations/email/test_client.py
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
        _, kwargs = mock_send.await_args
        message = mock_send.await_args.args[0]
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
```

Verify `SMTPAuthenticationError`/`SMTPRecipientsRefused`/`SMTPConnectError`'s real constructors against the installed `aiosmtplib==5.1.2` before finalizing (`inspect.signature`) — the args above are best-effort, not independently re-confirmed the way Task 1's `send()` signature already was.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/integrations/email/test_client.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

```python
# backend/app/integrations/email/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict


class EmailIntegrationConfig(BaseSettings):
    """Environment driven settings for the app-wide SMTP relay. Every
    notification_channels.type=EMAIL row only stores `recipients` — the
    actual sending credentials are global, not per-channel."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="EMAIL__", extra="ignore")

    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_ADDRESS: str = ""
    SMTP_START_TLS: bool = True


email_settings = EmailIntegrationConfig()
```

```python
# backend/app/integrations/email/constants.py
from enum import StrEnum


class EmailErrorCode(StrEnum):
    UNAVAILABLE = "email_unavailable"
    INVALID_CREDENTIAL = "email_invalid_credential"
    REJECTED = "email_rejected"
```

```python
# backend/app/integrations/email/exceptions.py
from app.core.exceptions import IntegrationError, ValidationFailedError
from app.integrations.email.constants import EmailErrorCode


class EmailApiUnavailable(IntegrationError):
    code = EmailErrorCode.UNAVAILABLE
    message = "SMTP relay unavailable"


class InvalidEmailCredential(ValidationFailedError):
    code = EmailErrorCode.INVALID_CREDENTIAL
    message = "SMTP relay rejected the configured credentials"


class EmailRejected(ValidationFailedError):
    code = EmailErrorCode.REJECTED
    message = "SMTP relay rejected this message"
```

```python
# backend/app/integrations/email/client.py
"""SMTP client. HTTP-adjacent (SMTP) only — no database, no business logic."""

from email.message import EmailMessage

import aiosmtplib
from aiosmtplib.errors import (
    SMTPAuthenticationError,
    SMTPDataError,
    SMTPRecipientRefused,
    SMTPRecipientsRefused,
    SMTPSenderRefused,
    SMTPException,
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
```

Confirm the exact exception import names/hierarchy against the installed `aiosmtplib==5.1.2` before finalizing (`from aiosmtplib.errors import ...` — the module path itself, `aiosmtplib.errors`, was confirmed this session; individual class availability was listed but not each one's exact constructor).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/integrations/email/test_client.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/integrations/email tests/integrations/email
git commit -m "feat(email): add EmailClient wrapping aiosmtplib"
```

---

## Task 2: `app/integrations/telegram/` — Bot API client

**Files:**
- Create: `backend/app/integrations/telegram/{__init__,config,constants,exceptions,client}.py`
- Test: `backend/tests/integrations/telegram/test_client.py`

**Interfaces:**
- Produces: `TelegramApiUnavailable`, `InvalidTelegramCredential`, `TelegramRejected`, `TelegramClient.send_message(self, *, bot_token: str, chat_id: str, text: str) -> None`.

- [ ] **Step 1: Write the failing tests**

Mirror `app/integrations/cloudflare/client.py`'s `httpx.MockTransport`-based test style exactly (already an established pattern in this codebase, read `tests/integrations/cloudflare/test_client.py` first).

```python
# backend/tests/integrations/telegram/test_client.py
import httpx
import pytest

from app.integrations.telegram.client import TelegramClient
from app.integrations.telegram.exceptions import (
    InvalidTelegramCredential,
    TelegramApiUnavailable,
    TelegramRejected,
)


class TestSendMessage:
    async def test_succeeds_on_ok_true(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/bottok123/sendMessage"
            body = request.read()
            assert b"chat-1" in body
            assert b"hello" in body
            return httpx.Response(200, json={"ok": True, "result": {}})

        client = TelegramClient(transport=httpx.MockTransport(handler))
        await client.send_message(bot_token="tok123", chat_id="chat-1", text="hello")

    async def test_401_raises_invalid_credential(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"ok": False, "error_code": 401, "description": "Unauthorized"})

        client = TelegramClient(transport=httpx.MockTransport(handler))
        with pytest.raises(InvalidTelegramCredential):
            await client.send_message(bot_token="bad", chat_id="chat-1", text="hello")

    async def test_ok_false_raises_rejected(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"ok": False, "error_code": 400, "description": "chat not found"})

        client = TelegramClient(transport=httpx.MockTransport(handler))
        with pytest.raises(TelegramRejected):
            await client.send_message(bot_token="tok123", chat_id="wrong", text="hello")

    async def test_transport_failure_raises_unavailable(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused")

        client = TelegramClient(transport=httpx.MockTransport(handler))
        with pytest.raises(TelegramApiUnavailable):
            await client.send_message(bot_token="tok123", chat_id="chat-1", text="hello")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/integrations/telegram/test_client.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

```python
# backend/app/integrations/telegram/config.py
from pydantic import HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class TelegramIntegrationConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="TELEGRAM__", extra="ignore")

    API_BASE_URL: HttpUrl = HttpUrl("https://api.telegram.org")
    HTTP_TIMEOUT_SECONDS: float = 10.0


telegram_settings = TelegramIntegrationConfig()
```

```python
# backend/app/integrations/telegram/constants.py
from enum import StrEnum


class TelegramErrorCode(StrEnum):
    UNAVAILABLE = "telegram_unavailable"
    INVALID_CREDENTIAL = "telegram_invalid_credential"
    REJECTED = "telegram_rejected"
```

```python
# backend/app/integrations/telegram/exceptions.py
from app.core.exceptions import IntegrationError, ValidationFailedError
from app.integrations.telegram.constants import TelegramErrorCode


class TelegramApiUnavailable(IntegrationError):
    code = TelegramErrorCode.UNAVAILABLE
    message = "Telegram Bot API unavailable"


class InvalidTelegramCredential(ValidationFailedError):
    code = TelegramErrorCode.INVALID_CREDENTIAL
    message = "Telegram rejected the provided bot token"


class TelegramRejected(ValidationFailedError):
    code = TelegramErrorCode.REJECTED
    message = "Telegram rejected this message"
```

```python
# backend/app/integrations/telegram/client.py
"""Telegram Bot API client. HTTP only — no database, no business logic."""

import httpx

from app.core.base.markers import integration
from app.integrations.telegram.config import telegram_settings
from app.integrations.telegram.exceptions import (
    InvalidTelegramCredential,
    TelegramApiUnavailable,
    TelegramRejected,
)


class TelegramClient:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    @integration
    async def send_message(self, *, bot_token: str, chat_id: str, text: str) -> None:
        """POST /bot{token}/sendMessage. Checks the response's own
        {"ok": bool, ...} envelope, not just HTTP status — same lesson
        Cloudflare's v4 API already taught this codebase."""
        try:
            async with httpx.AsyncClient(
                base_url=str(telegram_settings.API_BASE_URL), transport=self._transport
            ) as client:
                response = await client.post(
                    f"/bot{bot_token}/sendMessage",
                    json={"chat_id": chat_id, "text": text},
                    timeout=telegram_settings.HTTP_TIMEOUT_SECONDS,
                )
        except httpx.HTTPError as exc:
            raise TelegramApiUnavailable() from exc

        if response.status_code in (401, 403):
            raise InvalidTelegramCredential()
        if response.status_code >= 500:
            raise TelegramApiUnavailable(status_code=response.status_code)
        body = response.json()
        if not body.get("ok", False):
            raise TelegramRejected(message=body.get("description", "Telegram rejected this message"))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/integrations/telegram/test_client.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/integrations/telegram tests/integrations/telegram
git commit -m "feat(telegram): add TelegramClient.send_message"
```

---

## Task 3: `app/integrations/base_vn/` — Incoming Webhook client

**Files:**
- Create: `backend/app/integrations/base_vn/{__init__,config,constants,exceptions,client}.py`
- Test: `backend/tests/integrations/base_vn/test_client.py`

**Interfaces:**
- Produces: `BaseVnApiUnavailable`, `BaseVnRejected`, `BaseVnClient.send(self, *, webhook_url: str, base_content: str) -> None`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/integrations/base_vn/test_client.py
import httpx
import pytest

from app.integrations.base_vn.client import BaseVnClient
from app.integrations.base_vn.exceptions import BaseVnApiUnavailable, BaseVnRejected


class TestSend:
    async def test_succeeds_on_2xx(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert b"base_content" in request.read()
            return httpx.Response(200, json={"success": True})

        client = BaseVnClient(transport=httpx.MockTransport(handler))
        await client.send(webhook_url="http://base.vn/webhook/abc", base_content="hello")

    async def test_4xx_raises_rejected(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"success": False, "message": "bad payload"})

        client = BaseVnClient(transport=httpx.MockTransport(handler))
        with pytest.raises(BaseVnRejected):
            await client.send(webhook_url="http://base.vn/webhook/abc", base_content="hello")

    async def test_5xx_raises_unavailable(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500)

        client = BaseVnClient(transport=httpx.MockTransport(handler))
        with pytest.raises(BaseVnApiUnavailable):
            await client.send(webhook_url="http://base.vn/webhook/abc", base_content="hello")

    async def test_transport_failure_raises_unavailable(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused")

        client = BaseVnClient(transport=httpx.MockTransport(handler))
        with pytest.raises(BaseVnApiUnavailable):
            await client.send(webhook_url="http://base.vn/webhook/abc", base_content="hello")
```

Note `webhook_url` is the FULL target URL (not a path against a fixed base) — unlike Cloudflare/Telegram/Loki, there is no single fixed Base.vn host; every channel's webhook points at a different, user-provided URL (created per Base Message group in their UI). The client's `httpx.AsyncClient` must therefore be constructed with `base_url=""` and the request made against the full `webhook_url` directly, not a relative path.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/integrations/base_vn/test_client.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

```python
# backend/app/integrations/base_vn/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseVnIntegrationConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="BASE_VN__", extra="ignore")

    HTTP_TIMEOUT_SECONDS: float = 10.0


base_vn_settings = BaseVnIntegrationConfig()
```

```python
# backend/app/integrations/base_vn/constants.py
from enum import StrEnum


class BaseVnErrorCode(StrEnum):
    UNAVAILABLE = "base_vn_unavailable"
    REJECTED = "base_vn_rejected"
```

```python
# backend/app/integrations/base_vn/exceptions.py
from app.core.exceptions import IntegrationError, ValidationFailedError
from app.integrations.base_vn.constants import BaseVnErrorCode


class BaseVnApiUnavailable(IntegrationError):
    code = BaseVnErrorCode.UNAVAILABLE
    message = "Base.vn webhook unavailable"


class BaseVnRejected(ValidationFailedError):
    """No credential concept for a bearer-in-URL webhook — every non-2xx
    that isn't a transport/5xx failure means the webhook itself declined
    the payload."""

    code = BaseVnErrorCode.REJECTED
    message = "Base.vn webhook rejected this message"
```

```python
# backend/app/integrations/base_vn/client.py
"""Base.vn Incoming Webhook client. HTTP only — no database, no business logic."""

import httpx

from app.core.base.markers import integration
from app.integrations.base_vn.config import base_vn_settings
from app.integrations.base_vn.exceptions import BaseVnApiUnavailable, BaseVnRejected


class BaseVnClient:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    @integration
    async def send(self, *, webhook_url: str, base_content: str) -> None:
        """POST webhook_url with {"base_content": ...} — the field name
        Base.vn's own Incoming Webhook mechanism expects. Every channel's
        webhook_url is a distinct, user-provided full URL (no fixed host),
        so this client is constructed with base_url="" and posts to the
        full URL directly."""
        try:
            async with httpx.AsyncClient(transport=self._transport) as client:
                response = await client.post(
                    webhook_url,
                    json={"base_content": base_content},
                    timeout=base_vn_settings.HTTP_TIMEOUT_SECONDS,
                )
        except httpx.HTTPError as exc:
            raise BaseVnApiUnavailable() from exc

        if response.status_code >= 500:
            raise BaseVnApiUnavailable(status_code=response.status_code)
        if response.is_error:
            raise BaseVnRejected()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/integrations/base_vn/test_client.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/integrations/base_vn tests/integrations/base_vn
git commit -m "feat(base_vn): add BaseVnClient.send for Incoming Webhook"
```

---

## Task 4: `app/modules/notifications/` — scaffold (config, constants, models, schemas, exceptions, rules)

**Files:**
- Create: `backend/app/modules/notifications/{__init__,config,constants,models,schemas,exceptions,rules}.py`
- Test: `backend/tests/notifications/{__init__,test_models,test_rules}.py`

**Interfaces:**
- Consumes: `Base` (`app.core.database`, confirmed real import path from Phase 6/7), `FernetCodec`.
- Produces: `NotificationChannelType(StrEnum)`, `NotificationsLimits`, `ErrorCode(StrEnum)`, `NotificationsAuditActions(StrEnum)`, `NotificationChannel` (model), `NotificationChannelRead`/`Create`/`Update`/`TestSendRequest`, exceptions, `NotificationRules.validate_config`/`.render_base_content`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/notifications/test_rules.py
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
```

```python
# backend/tests/notifications/test_models.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/notifications/ -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.modules.notifications'`

- [ ] **Step 3: Write the implementation**

```python
# backend/app/modules/notifications/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict


class NotificationsConfig(BaseSettings):
    """Environment driven settings for the notifications module."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="NOTIFICATIONS__", extra="ignore")

    # Fernet key encrypting NotificationChannel.config's secret sub-fields
    # (TELEGRAM.bot_token, BASE_VN.webhook_url) at rest.
    FERNET_KEY: str = ""


notifications_settings = NotificationsConfig()
```

```python
# backend/app/modules/notifications/constants.py
from enum import StrEnum


class NotificationChannelType(StrEnum):
    EMAIL = "email"
    BASE_VN = "base_vn"
    TELEGRAM = "telegram"
    OTHER = "other"


class NotificationsLimits:
    MAX_NAME_LENGTH = 255
    MAX_MESSAGE_TEMPLATE_LENGTH = 2000
    MAX_TEST_MESSAGE_LENGTH = 2000


class ErrorCode(StrEnum):
    CHANNEL_NOT_FOUND = "notification_channel_not_found"
    PROJECT_NOT_FOUND = "notifications_project_not_found"
    ENVIRONMENT_NOT_FOUND = "notifications_environment_not_found"
    INVALID_CONFIG = "notification_channel_invalid_config"
    UNSUPPORTED_TYPE = "notification_channel_unsupported_type"


class NotificationsAuditActions(StrEnum):
    CHANNEL_CREATED = "NOTIFICATION_CHANNEL_CREATED"
    CHANNEL_UPDATED = "NOTIFICATION_CHANNEL_UPDATED"
    CHANNEL_DELETED = "NOTIFICATION_CHANNEL_DELETED"
    TEST_SENT = "NOTIFICATION_CHANNEL_TEST_SENT"
```

```python
# backend/app/modules/notifications/models.py
"""SQLAlchemy models owned exclusively by the notifications module."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.modules.notifications.constants import NotificationChannelType, NotificationsLimits


class NotificationChannel(Base):
    __tablename__ = "notification_channels"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    environment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("environments.id", ondelete="CASCADE"), nullable=True
    )
    type: Mapped[NotificationChannelType] = mapped_column(Enum(NotificationChannelType, native_enum=False))
    name: Mapped[str] = mapped_column(String(NotificationsLimits.MAX_NAME_LENGTH))
    config: Mapped[dict] = mapped_column(JSONB)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
```

```python
# backend/app/modules/notifications/schemas.py
from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.core.models import CustomModel, FrozenModel
from app.modules.notifications.constants import NotificationChannelType, NotificationsLimits


class NotificationChannelRead(FrozenModel):
    id: UUID
    project_id: UUID
    environment_id: UUID | None
    type: NotificationChannelType
    name: str
    config: dict
    """Type-appropriate masked view, never the raw stored JSON — see
    NotificationChannelRepository's read-mapping for what each type
    actually exposes (Decision #2)."""
    is_active: bool
    created_at: datetime
    updated_at: datetime


class NotificationChannelCreate(CustomModel):
    project_id: UUID
    environment_id: UUID | None = None
    type: NotificationChannelType
    name: str = Field(max_length=NotificationsLimits.MAX_NAME_LENGTH)
    config: dict


class NotificationChannelUpdate(CustomModel):
    name: str | None = Field(default=None, max_length=NotificationsLimits.MAX_NAME_LENGTH)
    config: dict | None = None
    is_active: bool | None = None


class TestSendRequest(CustomModel):
    message: str | None = Field(default=None, max_length=NotificationsLimits.MAX_TEST_MESSAGE_LENGTH)
```

```python
# backend/app/modules/notifications/exceptions.py
from app.core.exceptions import NotFoundError, ValidationFailedError
from app.modules.notifications.constants import ErrorCode


class NotificationChannelNotFound(NotFoundError):
    code = ErrorCode.CHANNEL_NOT_FOUND
    message = "Notification channel not found"


class NotificationsProjectNotFound(NotFoundError):
    code = ErrorCode.PROJECT_NOT_FOUND
    message = "Project not found"


class NotificationsEnvironmentNotFound(NotFoundError):
    """Module-local on purpose — notifications defines its own rather than
    importing projects' EnvironmentNotFound, keeping cross-module coupling
    to data only (mirrors CloudflareEnvironmentNotFound's reasoning)."""

    code = ErrorCode.ENVIRONMENT_NOT_FOUND
    message = "Environment not found"


class InvalidChannelConfig(ValidationFailedError):
    code = ErrorCode.INVALID_CONFIG
    message = "This channel's config is missing required fields for its type"


class UnsupportedChannelType(ValidationFailedError):
    code = ErrorCode.UNSUPPORTED_TYPE
    message = "This channel type does not support sending yet"
```

```python
# backend/app/modules/notifications/rules.py
"""Pure business rules for the notifications module — no I/O."""

from app.core.base.markers import rule
from app.modules.notifications.constants import NotificationChannelType
from app.modules.notifications.exceptions import InvalidChannelConfig


class NotificationRules:
    @staticmethod
    @rule
    def validate_config(channel_type: NotificationChannelType, config: dict) -> None:
        """Raises InvalidChannelConfig if config is missing required fields
        for channel_type. OTHER has no defined required fields by design
        (Decision #9 — reserved for a future channel)."""
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
        """Decision #4: substitute {message} if present; static text gets
        the message appended; empty template falls back to the raw message."""
        if not template:
            return message
        if "{message}" in template:
            return template.replace("{message}", message)
        return f"{template} {message}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/notifications/ -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/modules/notifications tests/notifications
git commit -m "feat(notifications): add module scaffold (config, constants, models, schemas, exceptions, rules)"
```

---

## Task 5: Alembic migration for `notification_channels`

**Files:**
- Create: `backend/alembic/versions/<new>_create_notification_channels_schema.py`
- Modify: `backend/alembic/env.py`

**Interfaces:**
- Consumes: `NotificationChannel` model (Task 4).

- [ ] **Step 1: Register the model for autogenerate awareness**

Add to `alembic/env.py` (mirrors the `observability_models` import added in Phase 6):
```python
from app.modules.notifications import (
    models as notifications_models,  # noqa: F401 -- registers notification_channels on Base.metadata for autogenerate
)
```

- [ ] **Step 2: Confirm the current alembic head**

Run: `cd backend && uv run alembic heads` — use the returned revision id as `down_revision`. As of the start of this phase it is `9b4d2e7f5c1a` (Phase 6's `create_loki_configs_schema`) unless Phase 7 added a migration (it did not — Phase 7 was purely additive to existing tables/code, no new DB table). Verify this is still true before writing the migration; if `alembic heads` returns something else, use that instead.

- [ ] **Step 3: Hand-write the migration**

Given this repo's `env.py` does not import every module's models (confirmed during Phase 6 — only `dx_core`/`users`/`rbac`/`observability` are registered, `cloudflare`/`projects`/`audit` are not), autogenerate would incorrectly propose dropping every unregistered table's schema. Hand-write the migration instead, mirroring `9b4d2e7f5c1a_create_loki_configs_schema.py`'s exact style (`sa.Enum(..., native_enum=False)`, `op.f(...)` named constraints):

```python
"""create_notification_channels_schema

Revision ID: <generated>
Revises: 9b4d2e7f5c1a
Create Date: 2026-08-24 00:00:00.000000
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = '<generated>'
down_revision = '9b4d2e7f5c1a'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('notification_channels',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('project_id', sa.UUID(), nullable=False),
    sa.Column('environment_id', sa.UUID(), nullable=True),
    sa.Column(
        'type',
        sa.Enum('email', 'base_vn', 'telegram', 'other', name='notificationchanneltype', native_enum=False),
        nullable=False,
    ),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(
        ['project_id'], ['projects.id'], name=op.f('notification_channels_project_id_fkey'),
        ondelete='CASCADE'
    ),
    sa.ForeignKeyConstraint(
        ['environment_id'], ['environments.id'], name=op.f('notification_channels_environment_id_fkey'),
        ondelete='CASCADE'
    ),
    sa.PrimaryKeyConstraint('id', name=op.f('notification_channels_pkey')),
    )
    op.create_index(op.f('notification_channels_project_id_idx'), 'notification_channels', ['project_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('notification_channels_project_id_idx'), table_name='notification_channels')
    op.drop_table('notification_channels')
```

- [ ] **Step 4: Apply to `itsm_test`**

Run against the `itsm_test` sibling database on the shared 5435 Postgres server (`business-chatbot-postgres` container) — never the live `itsm` database:
```bash
DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5435/itsm_test" uv run alembic upgrade head
```
Verify the current head with `psql -h localhost -p 5435 -U postgres -d itsm_test -c "SELECT version_num FROM alembic_version;"` before applying, matching the exact standing-constraint verification step every prior phase's migration task has done.

- [ ] **Step 5: Verify reversibility**

```bash
DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5435/itsm_test" uv run alembic downgrade -1
DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5435/itsm_test" uv run alembic upgrade head
```

- [ ] **Step 6: Commit**

```bash
git add alembic/versions/ alembic/env.py
git commit -m "feat(notifications): add notification_channels migration"
```

---

## Task 6: RBAC catalog additions

**Files:**
- Modify: `backend/app/modules/rbac/constants.py`

**Interfaces:**
- Produces: `RbacResources.NOTIFICATION_CHANNEL`, 4 new `RbacPermissionCatalog.CATALOG` rows.

- [ ] **Step 1: No test needed — this is a static data addition**

Per Phase 3's own established precedent, catalog additions are covered by the router integration tests (Task 8) that exercise the new permission gates, not a dedicated catalog test.

- [ ] **Step 2: Add the catalog rows and resource constant**

```python
# add to RbacPermissionCatalog.CATALOG in backend/app/modules/rbac/constants.py
        ("notification_channel", "create", "permissions.notification_channel.create"),
        ("notification_channel", "read", "permissions.notification_channel.read"),
        ("notification_channel", "update", "permissions.notification_channel.update"),
        ("notification_channel", "delete", "permissions.notification_channel.delete"),
```
```python
# add to RbacResources in the same file
    NOTIFICATION_CHANNEL = "notification_channel"
```

- [ ] **Step 3: Verify**

Run: `cd backend && uv run python -m app.seeds.seed_rbac` against `itsm_test` (or confirm via a quick `uv run python -c "from app.modules.rbac.constants import RbacPermissionCatalog; print(len(RbacPermissionCatalog.CATALOG))"` that the count increased by 4) — the seed script picks up new catalog rows automatically per its own docstring, no script change needed.

- [ ] **Step 4: Commit**

```bash
git add app/modules/rbac/constants.py
git commit -m "feat(rbac): add notification_channel permission catalog"
```

---

## Task 7: `.importlinter` additions

**Files:**
- Modify: `backend/.importlinter`

- [ ] **Step 1: Add `app.modules.notifications` to the 4 existing facade contracts' `source_modules`**

`rbac-facade`, `users-facade`, `projects-facade`, `audit-facade` — same 4 contracts every prior module-adding phase (`cloudflare` in Phase 3, `observability` in Phase 6) was added to.

- [ ] **Step 2: Add a new `notifications-facade` stanza**

```ini
[importlinter:contract:notifications-facade]
name = Other modules reach notifications only through public.py
type = forbidden
source_modules =
    app.modules.auth
    app.modules.rbac
    app.modules.users
    app.modules.projects
    app.modules.audit
    app.modules.cloudflare
    app.modules.observability
    app.modules.common
forbidden_modules =
    app.modules.notifications.repository
    app.modules.notifications.models
    app.modules.notifications.uow
    app.modules.notifications.services
allow_indirect_imports = True
```

- [ ] **Step 3: Add the 3 new integration leaves to `integrations-are-leaves` and `root-is-mechanism`**

`app.integrations.email`, `app.integrations.telegram`, `app.integrations.base_vn` added to both contracts' relevant lists, mirroring exactly how `app.integrations.loki` was added in Phase 6.

- [ ] **Step 4: Verify**

Run: `cd backend && lint-imports && python scripts/check_module_boundaries.py --strict`
Expected: all green (no violations yet — `notifications` doesn't import anything cross-module until Task 8).

- [ ] **Step 5: Commit**

```bash
git add .importlinter
git commit -m "chore(importlinter): add notifications-facade contract and 3 new integration leaves"
```

---

## Task 8: `repository.py` + `uow.py` (with secret encryption on write, masking on read)

**Files:**
- Create: `backend/app/modules/notifications/repository.py`
- Create: `backend/app/modules/notifications/uow.py`
- Test: `backend/tests/notifications/test_repository.py`

**Interfaces:**
- Consumes: `FernetCodec`, `notifications_settings`, `NotificationChannel` model, `NotificationChannelRead` schema.
- Produces: `AbstractNotificationChannelRepository`/`NotificationChannelRepository` (`get_by_id`, `list_page`, `list_for_project`, `create`, `update`, `delete`, `get_config_ciphertext_fields`), `AbstractNotificationsUnitOfWork`/`NotificationsUnitOfWork`.

- [ ] **Step 1: Write the failing tests**

Mirror `tests/observability/test_repository.py`'s real-Postgres `_session` fixture pattern exactly (session-scoped `engine`, truncate-after-test). This repository is the one place secret encryption/masking actually happens — Decision #1/#2 — so these tests are the ground truth for that behavior, not the service layer's.

```python
# backend/tests/notifications/test_repository.py
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.crypto import FernetCodec
from app.modules.notifications.config import notifications_settings
from app.modules.notifications.constants import NotificationChannelType
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
            project_id=project.id, environment_id=None, type=NotificationChannelType.EMAIL,
            name="Team", config={"recipients": ["a@b.com"]},
        )
        assert created.config == {"recipients": ["a@b.com"]}

    async def test_get_config_ciphertext_fields_returns_raw_secrets(self, _session: AsyncSession) -> None:
        project = await _make_project(_session)
        repo = NotificationChannelRepository(_session)
        created = await repo.create(
            project_id=project.id, environment_id=None, type=NotificationChannelType.TELEGRAM,
            name="Ops", config={"bot_token": "raw-token", "chat_id": "1"},
        )

        fields = await repo.get_config_ciphertext_fields(created.id)
        assert FernetCodec.decrypt(fields["bot_token"], key=TEST_FERNET_KEY) == "raw-token"
        assert fields["chat_id"] == "1"

    async def test_list_for_project_filters_by_environment(self, _session: AsyncSession) -> None:
        project = await _make_project(_session)
        env = Environment(project_id=project.id, type="dev", name="Dev", base_url=None)
        _session.add(env)
        await _session.flush()
        repo = NotificationChannelRepository(_session)
        await repo.create(
            project_id=project.id, environment_id=None, type=NotificationChannelType.EMAIL,
            name="All-env", config={"recipients": ["a@b.com"]},
        )
        await repo.create(
            project_id=project.id, environment_id=env.id, type=NotificationChannelType.EMAIL,
            name="Dev-only", config={"recipients": ["b@b.com"]},
        )

        all_channels = await repo.list_for_project(project.id, environment_id=None)
        assert len(all_channels) == 2

        dev_channels = await repo.list_for_project(project.id, environment_id=env.id)
        assert len(dev_channels) == 1
        assert dev_channels[0].name == "Dev-only"
```

`list_for_project(project_id, environment_id=None)` returning "all channels for the project regardless of environment scoping" vs. "channels visible to one specific environment (its own `environment_id` OR `environment_id IS NULL`)" is a real query-semantics decision — the test above assumes the latter (a `environment_id` filter narrows to that environment's own channels plus project-wide ones), matching how "null = applies to every environment" (Decision #8) should behave for a caller asking "what channels apply to this specific environment." Confirm this interpretation makes sense during implementation; if the intended UI always lists ALL of a project's channels with environment scope shown as a column (not filtered), simplify `list_for_project` to a single `project_id`-only query and adjust the test accordingly — read `docs/tasks/devops-control-panel-schema.md` line 265 once more during implementation to settle this if it feels ambiguous.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/notifications/test_repository.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

```python
# backend/app/modules/notifications/repository.py
"""Single access path to the notification_channels table. Owns the only
place secret sub-fields within `config` get encrypted (on write) and
masked (on read) — Decisions #1/#2."""

from abc import abstractmethod
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.markers import database
from app.core.base.repository import AbstractRepository
from app.core.crypto import FernetCodec
from app.modules.notifications.config import notifications_settings
from app.modules.notifications.constants import NotificationChannelType
from app.modules.notifications.models import NotificationChannel
from app.modules.notifications.schemas import NotificationChannelRead

_SECRET_FIELDS_BY_TYPE: dict[NotificationChannelType, str] = {
    NotificationChannelType.TELEGRAM: "bot_token",
    NotificationChannelType.BASE_VN: "webhook_url",
}


def _mask_config(channel_type: NotificationChannelType, config: dict) -> dict:
    """Replaces a type's known secret field (if any) with a has_<field>
    boolean, leaving every other key as-is. OTHER has no known secret
    field, so its config passes through unmasked — there's nothing to mask
    by definition (Decision #2)."""
    secret_field = _SECRET_FIELDS_BY_TYPE.get(channel_type)
    if secret_field is None:
        return dict(config)
    masked = {k: v for k, v in config.items() if k != secret_field}
    masked[f"has_{secret_field}"] = secret_field in config and bool(config[secret_field])
    return masked


def _encrypt_config(channel_type: NotificationChannelType, config: dict) -> dict:
    secret_field = _SECRET_FIELDS_BY_TYPE.get(channel_type)
    if secret_field is None or secret_field not in config:
        return dict(config)
    encrypted = dict(config)
    encrypted[secret_field] = FernetCodec.encrypt(config[secret_field], key=notifications_settings.FERNET_KEY)
    return encrypted


def _to_read(row: NotificationChannel) -> NotificationChannelRead:
    return NotificationChannelRead(
        id=row.id,
        project_id=row.project_id,
        environment_id=row.environment_id,
        type=row.type,
        name=row.name,
        config=_mask_config(row.type, row.config),
        is_active=row.is_active,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class AbstractNotificationChannelRepository(AbstractRepository[NotificationChannelRead, UUID]):
    @abstractmethod
    async def list_for_project(
        self, project_id: UUID, *, environment_id: UUID | None
    ) -> list[NotificationChannelRead]:
        raise NotImplementedError

    @abstractmethod
    async def create(
        self, *, project_id: UUID, environment_id: UUID | None, type: NotificationChannelType,
        name: str, config: dict,
    ) -> NotificationChannelRead:
        raise NotImplementedError

    @abstractmethod
    async def update(
        self, channel_id: UUID, *, name: str | None, config: dict | None, is_active: bool | None,
    ) -> NotificationChannelRead:
        raise NotImplementedError

    @abstractmethod
    async def delete(self, channel_id: UUID) -> None:
        raise NotImplementedError

    @abstractmethod
    async def get_config_ciphertext_fields(self, channel_id: UUID) -> dict:
        """Returns the raw stored config (secret sub-field still ciphertext,
        everything else plaintext) — for the send path only, bypassing
        NotificationChannelRead's masking entirely."""
        raise NotImplementedError


class NotificationChannelRepository(AbstractNotificationChannelRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @database
    async def get_by_id(self, entity_id: UUID) -> NotificationChannelRead | None:
        row = await self._session.get(NotificationChannel, entity_id)
        return _to_read(row) if row else None

    @database
    async def list_page(self, limit: int, offset: int) -> tuple[list[NotificationChannelRead], int]:
        rows = await self._session.scalars(
            select(NotificationChannel).order_by(NotificationChannel.id).limit(limit).offset(offset)
        )
        items = [_to_read(row) for row in rows]
        total = await self._session.scalar(select(func.count()).select_from(NotificationChannel))
        return items, total or 0

    @database
    async def list_for_project(
        self, project_id: UUID, *, environment_id: UUID | None
    ) -> list[NotificationChannelRead]:
        stmt = select(NotificationChannel).where(NotificationChannel.project_id == project_id)
        if environment_id is not None:
            stmt = stmt.where(
                (NotificationChannel.environment_id == environment_id)
                | (NotificationChannel.environment_id.is_(None))
            )
        rows = await self._session.scalars(stmt.order_by(NotificationChannel.name))
        return [_to_read(row) for row in rows]

    @database
    async def create(
        self, *, project_id: UUID, environment_id: UUID | None, type: NotificationChannelType,
        name: str, config: dict,
    ) -> NotificationChannelRead:
        row = NotificationChannel(
            project_id=project_id,
            environment_id=environment_id,
            type=type,
            name=name,
            config=_encrypt_config(type, config),
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return _to_read(row)

    @database
    async def update(
        self, channel_id: UUID, *, name: str | None, config: dict | None, is_active: bool | None,
    ) -> NotificationChannelRead:
        row = await self._session.get(NotificationChannel, channel_id)
        if row is None:
            raise ValueError(f"notification channel {channel_id} does not exist")
        if name is not None:
            row.name = name
        if config is not None:
            row.config = _encrypt_config(row.type, config)
        if is_active is not None:
            row.is_active = is_active
        await self._session.flush()
        await self._session.refresh(row)
        return _to_read(row)

    @database
    async def delete(self, channel_id: UUID) -> None:
        row = await self._session.get(NotificationChannel, channel_id)
        if row is not None:
            await self._session.delete(row)
            await self._session.flush()

    @database
    async def get_config_ciphertext_fields(self, channel_id: UUID) -> dict:
        row = await self._session.get(NotificationChannel, channel_id)
        return dict(row.config) if row is not None else {}
```

```python
# backend/app/modules/notifications/uow.py
"""Transaction boundary for the notifications module."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.markers import database
from app.core.base.uow import AbstractUnitOfWork
from app.modules.notifications.repository import (
    AbstractNotificationChannelRepository,
    NotificationChannelRepository,
)

logger = logging.getLogger(__name__)


class AbstractNotificationsUnitOfWork(AbstractUnitOfWork):
    channels: AbstractNotificationChannelRepository


class NotificationsUnitOfWork(AbstractNotificationsUnitOfWork):
    """No cache invalidation plumbing — same low-traffic reasoning as
    observability/uow.py's ObservabilityUnitOfWork."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.channels = NotificationChannelRepository(session)

    @database
    async def commit(self) -> None:
        await self._session.commit()

    @database
    async def rollback(self) -> None:
        await self._session.rollback()
        logger.warning("notifications unit of work rolled back")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/notifications/test_repository.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/modules/notifications/repository.py app/modules/notifications/uow.py tests/notifications/test_repository.py
git commit -m "feat(notifications): add repository and unit of work with per-secret encryption/masking"
```

---

## Task 9: Services (Create/Update/Delete/Get/List/TestSend)

**Files:**
- Create: `backend/app/modules/notifications/services/{__init__,create_channel,update_channel,delete_channel,get_channel,list_channels,test_send_channel}.py`
- Test: `backend/tests/notifications/test_services.py`

**Interfaces:**
- Consumes: `NotificationRules`, `ProjectsApi`, `AuditApi`, `AbstractNotificationsUnitOfWork`, the 3 integration clients.
- Produces: `CreateNotificationChannel`, `UpdateNotificationChannel`, `DeleteNotificationChannel`, `GetNotificationChannel`, `ListNotificationChannels`, `TestSendNotificationChannel`.

- [ ] **Step 1: Write the failing tests**

Mirror `tests/observability/test_services.py`'s Fake-based style exactly (FakeUnitOfWork, FakeProjectsApi, FakeAuditApi, Fake clients per integration).

```python
# backend/tests/notifications/test_services.py
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.core.crypto import FernetCodec
from app.integrations.telegram.exceptions import TelegramApiUnavailable
from app.modules.notifications.config import notifications_settings
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
TEST_FERNET_KEY = "kL8Zx3vQ9mN2pR7wT4yU6bC1dF5gH0jK3lM6nO9pQ2s="


@pytest.fixture(autouse=True)
def _fernet_key(monkeypatch) -> None:
    monkeypatch.setattr(notifications_settings, "FERNET_KEY", TEST_FERNET_KEY)


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
        stored_config = dict(config)
        if type == NotificationChannelType.TELEGRAM and "bot_token" in config:
            stored_config["bot_token"] = FernetCodec.encrypt(config["bot_token"], key=TEST_FERNET_KEY)
        if type == NotificationChannelType.BASE_VN and "webhook_url" in config:
            stored_config["webhook_url"] = FernetCodec.encrypt(config["webhook_url"], key=TEST_FERNET_KEY)
        self._raw_config[channel_id] = stored_config
        channel = NotificationChannelRead(
            id=channel_id, project_id=project_id, environment_id=environment_id, type=type, name=name,
            config={k: v for k, v in config.items() if k not in ("bot_token", "webhook_url")},
            is_active=True, created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        self._rows[channel_id] = channel
        return channel

    async def update(self, channel_id, *, name, config, is_active):
        existing = self._rows[channel_id]
        updated = existing.model_copy(update={k: v for k, v in {"name": name, "is_active": is_active}.items() if v is not None})
        self._rows[channel_id] = updated
        return updated

    async def delete(self, channel_id):
        self._rows.pop(channel_id, None)
        self._raw_config.pop(channel_id, None)

    async def get_config_ciphertext_fields(self, channel_id):
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
                project_id=uuid4(), environment_id=None, type=NotificationChannelType.EMAIL,
                name="Team", config={"recipients": ["a@b.com"]}, actor=_actor(),
            )

    async def test_rejects_invalid_config_for_type(self) -> None:
        project_id = uuid4()
        uow = FakeNotificationsUnitOfWork()
        use_case = CreateNotificationChannel(uow, FakeProjectsApi({project_id: object()}), FakeAuditApi())
        with pytest.raises(InvalidChannelConfig):
            await use_case.execute(
                project_id=project_id, environment_id=None, type=NotificationChannelType.TELEGRAM,
                name="Ops", config={}, actor=_actor(),
            )

    async def test_creates_and_audits(self) -> None:
        project_id = uuid4()
        uow = FakeNotificationsUnitOfWork()
        audit_api = FakeAuditApi()
        use_case = CreateNotificationChannel(uow, FakeProjectsApi({project_id: object()}), audit_api)

        channel = await use_case.execute(
            project_id=project_id, environment_id=None, type=NotificationChannelType.EMAIL,
            name="Team", config={"recipients": ["a@b.com"]}, actor=_actor(),
        )

        assert channel.name == "Team"
        assert uow.commits == 1
        assert len(audit_api.events) == 1


class TestDeleteNotificationChannel:
    async def test_raises_not_found(self) -> None:
        uow = FakeNotificationsUnitOfWork()
        use_case = DeleteNotificationChannel(uow, FakeAuditApi())
        with pytest.raises(NotificationChannelNotFound):
            await use_case.execute(uuid4(), actor=_actor())


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
            uow, telegram_client=FakeTelegramClient(), email_client=None, base_vn_client=None, audit_api=FakeAuditApi()
        )
        with pytest.raises(NotificationChannelNotFound):
            await use_case.execute(uuid4(), message=None, actor=_actor())

    async def test_other_type_raises_unsupported(self) -> None:
        project_id = uuid4()
        uow = FakeNotificationsUnitOfWork()
        create_use_case = CreateNotificationChannel(uow, FakeProjectsApi({project_id: object()}), FakeAuditApi())
        channel = await create_use_case.execute(
            project_id=project_id, environment_id=None, type=NotificationChannelType.OTHER,
            name="Future", config={"whatever": "x"}, actor=_actor(),
        )
        use_case = TestSendNotificationChannel(
            uow, telegram_client=FakeTelegramClient(), email_client=None, base_vn_client=None, audit_api=FakeAuditApi()
        )
        with pytest.raises(UnsupportedChannelType):
            await use_case.execute(channel.id, message=None, actor=_actor())

    async def test_telegram_dispatches_to_client_and_decrypts_token(self) -> None:
        project_id = uuid4()
        uow = FakeNotificationsUnitOfWork()
        create_use_case = CreateNotificationChannel(uow, FakeProjectsApi({project_id: object()}), FakeAuditApi())
        channel = await create_use_case.execute(
            project_id=project_id, environment_id=None, type=NotificationChannelType.TELEGRAM,
            name="Ops", config={"bot_token": "real-token", "chat_id": "chat-1"}, actor=_actor(),
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
        create_use_case = CreateNotificationChannel(uow, FakeProjectsApi({project_id: object()}), FakeAuditApi())
        channel = await create_use_case.execute(
            project_id=project_id, environment_id=None, type=NotificationChannelType.TELEGRAM,
            name="Ops", config={"bot_token": "real-token", "chat_id": "chat-1"}, actor=_actor(),
        )
        audit_api = FakeAuditApi()
        use_case = TestSendNotificationChannel(
            uow, telegram_client=FakeTelegramClient(raises=TelegramApiUnavailable()),
            email_client=None, base_vn_client=None, audit_api=audit_api,
        )

        with pytest.raises(TelegramApiUnavailable):
            await use_case.execute(channel.id, message="hello", actor=_actor())

        assert any(e["action"] == "NOTIFICATION_CHANNEL_TEST_SENT" for e in audit_api.events)
```

`TestSendNotificationChannel`'s exact constructor signature (`telegram_client`/`email_client`/`base_vn_client`/`audit_api` as shown above, all keyword) is this plan's own design choice — confirm it against whatever actually gets written in Step 3 below and adjust these tests' construction calls to match if it drifts during implementation; the dispatch behavior (decrypt the right secret, call the right client, audit regardless of outcome) is what actually matters, not the exact parameter order.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/notifications/test_services.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

```python
# backend/app/modules/notifications/services/create_channel.py
from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.notifications.constants import NotificationChannelType, NotificationsAuditActions
from app.modules.notifications.exceptions import NotificationsEnvironmentNotFound, NotificationsProjectNotFound
from app.modules.notifications.rules import NotificationRules
from app.modules.notifications.schemas import NotificationChannelRead
from app.modules.notifications.uow import AbstractNotificationsUnitOfWork
from app.modules.projects.public import ProjectsApi
from app.modules.users.public import UserRead


class CreateNotificationChannel(AbstractUseCase):
    def __init__(self, uow: AbstractNotificationsUnitOfWork, projects_api: ProjectsApi, audit_api: AuditApi) -> None:
        self._uow = uow
        self._projects_api = projects_api
        self._audit_api = audit_api

    @use_case
    async def execute(
        self, *, project_id: UUID, environment_id: UUID | None, type: NotificationChannelType,
        name: str, config: dict, actor: UserRead,
    ) -> NotificationChannelRead:
        if await self._projects_api.get_project_by_id(project_id) is None:
            raise NotificationsProjectNotFound()
        if environment_id is not None and await self._projects_api.get_environment_by_id(environment_id) is None:
            raise NotificationsEnvironmentNotFound()

        NotificationRules.validate_config(type, config)

        channel = await self._uow.channels.create(
            project_id=project_id, environment_id=environment_id, type=type, name=name, config=config
        )
        await self._uow.commit()

        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action=NotificationsAuditActions.CHANNEL_CREATED,
            severity=AuditSeverity.INFO,
            message=f"Notification channel '{name}' created",
            actor=AuditActor(user_id=actor.id, email=actor.email),
            project_id=project_id,
            environment_id=environment_id,
        )
        return channel
```

```python
# backend/app/modules/notifications/services/get_channel.py
from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.notifications.exceptions import NotificationChannelNotFound
from app.modules.notifications.schemas import NotificationChannelRead
from app.modules.notifications.uow import AbstractNotificationsUnitOfWork


class GetNotificationChannel(AbstractUseCase):
    def __init__(self, uow: AbstractNotificationsUnitOfWork) -> None:
        self._uow = uow

    @use_case
    async def execute(self, channel_id: UUID) -> NotificationChannelRead:
        channel = await self._uow.channels.get_by_id(channel_id)
        if channel is None:
            raise NotificationChannelNotFound()
        return channel
```

```python
# backend/app/modules/notifications/services/list_channels.py
from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.notifications.exceptions import NotificationsProjectNotFound
from app.modules.notifications.schemas import NotificationChannelRead
from app.modules.notifications.uow import AbstractNotificationsUnitOfWork
from app.modules.projects.public import ProjectsApi


class ListNotificationChannels(AbstractUseCase):
    def __init__(self, uow: AbstractNotificationsUnitOfWork, projects_api: ProjectsApi) -> None:
        self._uow = uow
        self._projects_api = projects_api

    @use_case
    async def execute(self, project_id: UUID, *, environment_id: UUID | None) -> list[NotificationChannelRead]:
        if await self._projects_api.get_project_by_id(project_id) is None:
            raise NotificationsProjectNotFound()
        return await self._uow.channels.list_for_project(project_id, environment_id=environment_id)
```

```python
# backend/app/modules/notifications/services/update_channel.py
```
Mirror `UpdateLokiConfig`'s "omitted field keeps existing value" convention (Phase 6) — `execute(self, channel_id: UUID, *, name: str | None = None, config: dict | None = None, is_active: bool | None = None, actor: UserRead) -> NotificationChannelRead`: load existing (404 via `NotificationChannelNotFound` if absent), if `config` provided run `NotificationRules.validate_config(existing.type, config)` before persisting (type itself is immutable — not in the Update schema at all, matching `record_type`'s immutability precedent from Phase 4's DNS records), delegate to `uow.channels.update(...)`, commit, audit `CHANNEL_UPDATED`.

```python
# backend/app/modules/notifications/services/delete_channel.py
```
Mirror `DeleteLokiConfig` exactly: load-by-id (404 if absent), delete, commit, audit `CHANNEL_DELETED`.

```python
# backend/app/modules/notifications/services/test_send_channel.py
from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.core.crypto import FernetCodec
from app.integrations.base_vn.client import BaseVnClient
from app.integrations.email.client import EmailClient
from app.integrations.telegram.client import TelegramClient
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.notifications.config import notifications_settings
from app.modules.notifications.constants import NotificationChannelType, NotificationsAuditActions
from app.modules.notifications.exceptions import NotificationChannelNotFound, UnsupportedChannelType
from app.modules.notifications.rules import NotificationRules
from app.modules.notifications.uow import AbstractNotificationsUnitOfWork
from app.modules.users.public import UserRead

_DEFAULT_TEST_MESSAGE = "Test notification from ITSM"


class TestSendNotificationChannel(AbstractUseCase):
    """Dispatches on channel.type to the one client that knows how to send
    through it (Decision #6) — the only place in this module that does."""

    def __init__(
        self,
        uow: AbstractNotificationsUnitOfWork,
        *,
        telegram_client: TelegramClient,
        email_client: EmailClient,
        base_vn_client: BaseVnClient,
        audit_api: AuditApi,
    ) -> None:
        self._uow = uow
        self._telegram_client = telegram_client
        self._email_client = email_client
        self._base_vn_client = base_vn_client
        self._audit_api = audit_api

    @use_case
    async def execute(self, channel_id: UUID, *, message: str | None, actor: UserRead) -> None:
        channel = await self._uow.channels.get_by_id(channel_id)
        if channel is None:
            raise NotificationChannelNotFound()

        text = message or _DEFAULT_TEST_MESSAGE
        try:
            await self._dispatch(channel, text)
        finally:
            await self._audit_api.log_event(
                type=AuditEventType.AUDIT,
                source=AuditSource.USER_ACTION,
                action=NotificationsAuditActions.TEST_SENT,
                severity=AuditSeverity.INFO,
                message=f"Test-sent through notification channel '{channel.name}'",
                actor=AuditActor(user_id=actor.id, email=actor.email),
                project_id=channel.project_id,
                environment_id=channel.environment_id,
            )

    async def _dispatch(self, channel, text: str) -> None:
        if channel.type == NotificationChannelType.OTHER:
            raise UnsupportedChannelType()

        raw_config = await self._uow.channels.get_config_ciphertext_fields(channel.id)

        if channel.type == NotificationChannelType.TELEGRAM:
            bot_token = FernetCodec.decrypt(raw_config["bot_token"], key=notifications_settings.FERNET_KEY)
            await self._telegram_client.send_message(bot_token=bot_token, chat_id=raw_config["chat_id"], text=text)
        elif channel.type == NotificationChannelType.EMAIL:
            await self._email_client.send(recipients=raw_config["recipients"], subject="ITSM Test Notification", body=text)
        elif channel.type == NotificationChannelType.BASE_VN:
            webhook_url = FernetCodec.decrypt(raw_config["webhook_url"], key=notifications_settings.FERNET_KEY)
            content = NotificationRules.render_base_content(raw_config.get("message_template", ""), text)
            await self._base_vn_client.send(webhook_url=webhook_url, base_content=content)
```

Note the `try/finally` around `_dispatch` — the audit call happens whether the send succeeded or raised, matching Decision #6/the test above (`test_telegram_send_failure_still_audits`); the original exception still propagates normally after the `finally` block runs (Python's own `try/finally` semantics — no explicit re-raise needed).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/notifications/ -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/modules/notifications/services tests/notifications/test_services.py
git commit -m "feat(notifications): add create/update/delete/get/list/test-send services"
```

---

## Task 10: `dependencies.py` + `router.py` + `public.py` + `main.py` registration

**Files:**
- Create: `backend/app/modules/notifications/dependencies.py`
- Create: `backend/app/modules/notifications/router.py`
- Create: `backend/app/modules/notifications/public.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/notifications/test_router.py`

**Interfaces:**
- Consumes: everything from Task 9, `require_permission`/`RbacResources.NOTIFICATION_CHANNEL`/`RbacActions` (Task 6).
- Produces: 6 registered routes.

- [ ] **Step 1: Write the failing tests**

Mirror `tests/observability/test_router.py`'s exact `_login_with_permissions`/real-HTTP-project-creation helper shape.

```python
# backend/tests/notifications/test_router.py
"""Integration tests for app.modules.notifications.router — real Postgres via testcontainers."""

from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.security import JwtCodec
from app.integrations.telegram.dependencies import get_telegram_client
from app.main import app
from app.modules.auth.config import auth_settings
from app.modules.auth.constants import AuthCookies
from app.modules.notifications.config import notifications_settings
from app.modules.rbac.models import Permission, Role, RolePermission, UserRole
from app.modules.users.models import User


@pytest.fixture(autouse=True)
def _fernet_key(monkeypatch) -> None:
    monkeypatch.setattr(notifications_settings, "FERNET_KEY", "kL8Zx3vQ9mN2pR7wT4yU6bC1dF5gH0jK3lM6nO9pQ2s=")


async def _login_with_permissions(
    client: AsyncClient, engine: AsyncEngine, *, permissions: list[tuple[str, str]], email: str = "actor@example.com"
) -> UUID:
    async with engine.begin() as conn:
        user_result = await conn.execute(
            insert(User).values(
                email=email, name=email, status="active", external_user_id=f"dx-{email}",
                employee_code=None, email_confirmed=True,
            )
        )
        user_id = user_result.inserted_primary_key[0]
        role_result = await conn.execute(insert(Role).values(name=f"role-{email}", is_system=False))
        role_id = role_result.inserted_primary_key[0]
        for resource, action in permissions:
            existing = await conn.execute(
                select(Permission.id).where(Permission.resource == resource, Permission.action == action)
            )
            permission_id = existing.scalar_one_or_none()
            if permission_id is None:
                perm_result = await conn.execute(
                    insert(Permission).values(resource=resource, action=action, description_key="x")
                )
                permission_id = perm_result.inserted_primary_key[0]
            await conn.execute(insert(RolePermission).values(role_id=role_id, permission_id=permission_id))
        await conn.execute(insert(UserRole).values(user_id=user_id, role_id=role_id))

    token = JwtCodec.encode(
        {"sub": str(user_id), "type": "access", "jti": f"test-jti-{email}"},
        secret=auth_settings.JWT_SECRET, ttl_seconds=3600,
    )
    client.cookies.set(AuthCookies.ACCESS_TOKEN, token)
    return user_id


async def _make_project(client: AsyncClient, engine: AsyncEngine) -> str:
    await _login_with_permissions(client, engine, permissions=[("project", "create")])
    resp = await client.post("/api/v1/projects", json={"name": "Site"})
    return resp.json()["data"]["id"]


class TestCreateAndListChannels:
    async def test_requires_create_permission(self, client: AsyncClient, engine: AsyncEngine) -> None:
        project_id = await _make_project(client, engine)
        await _login_with_permissions(client, engine, permissions=[], email="nope@x.com")

        response = await client.post(
            "/api/v1/notification-channels",
            json={"projectId": project_id, "type": "email", "name": "Team", "config": {"recipients": ["a@b.com"]}},
        )
        assert response.status_code == 403

    async def test_create_then_list(self, client: AsyncClient, engine: AsyncEngine) -> None:
        project_id = await _make_project(client, engine)
        await _login_with_permissions(
            client, engine, permissions=[("notification_channel", "create"), ("notification_channel", "read")],
            email="admin@x.com",
        )

        create_response = await client.post(
            "/api/v1/notification-channels",
            json={"projectId": project_id, "type": "telegram", "name": "Ops", "config": {"botToken": "tok", "chatId": "1"}},
        )
        assert create_response.status_code == 200, create_response.text
        body = create_response.json()["data"]
        assert "botToken" not in body["config"]
        assert body["config"]["hasBotToken"] is True

        list_response = await client.get(f"/api/v1/notification-channels?projectId={project_id}")
        assert list_response.status_code == 200
        assert len(list_response.json()["data"]) == 1


class TestTestSendChannel:
    async def test_dispatches_to_telegram_client(self, client: AsyncClient, engine: AsyncEngine) -> None:
        project_id = await _make_project(client, engine)
        await _login_with_permissions(
            client, engine, permissions=[("notification_channel", "create"), ("notification_channel", "update")],
            email="sender@x.com",
        )
        create_response = await client.post(
            "/api/v1/notification-channels",
            json={"projectId": project_id, "type": "telegram", "name": "Ops", "config": {"botToken": "tok", "chatId": "1"}},
        )
        channel_id = create_response.json()["data"]["id"]

        class FakeTelegramClient:
            calls: list[dict] = []

            async def send_message(self, **kwargs):
                FakeTelegramClient.calls.append(kwargs)

        app.dependency_overrides[get_telegram_client] = lambda: FakeTelegramClient()
        try:
            response = await client.post(f"/api/v1/notification-channels/{channel_id}/test-send", json={})
            assert response.status_code == 200, response.text
        finally:
            del app.dependency_overrides[get_telegram_client]

        assert FakeTelegramClient.calls[0]["bot_token"] == "tok"
```

Confirm the real casing of `NotificationChannelCreate`'s wire fields (`config` sub-keys `bot_token`/`chat_id`/`webhook_url`/etc. — since `CustomModel` camelCases at the Pydantic model's OWN declared field level, but `config: dict` is a raw, un-typed nested object, its inner keys are NOT auto-camelCased by the alias generator, which only applies to declared Pydantic field names, not arbitrary dict contents). This means `config` dict keys sent over the wire should stay `snake_case` as literally written (`bot_token`, not `botToken`) since they're opaque dict keys, not schema fields — **the test sketch above using `botToken`/`chatId` inside `config` is likely wrong; verify directly against how `NotificationChannelCreate.config: dict` actually serializes/deserializes during implementation and correct the test to send `{"bot_token": ..., "chat_id": ...}` if snake_case is confirmed correct, per the pattern found.**

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/notifications/test_router.py -v`
Expected: FAIL (404 route not found / `ModuleNotFoundError`)

- [ ] **Step 3: Write the implementation**

```python
# backend/app/integrations/telegram/dependencies.py
from app.integrations.telegram.client import TelegramClient


async def get_telegram_client() -> TelegramClient:
    return TelegramClient()
```
Mirror the identical shape for `app/integrations/email/dependencies.py` (`get_email_client`) and `app/integrations/base_vn/dependencies.py` (`get_base_vn_client`).

```python
# backend/app/modules/notifications/dependencies.py
"""FastAPI dependency providers for the notifications module."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.integrations.base_vn.client import BaseVnClient
from app.integrations.base_vn.dependencies import get_base_vn_client
from app.integrations.email.client import EmailClient
from app.integrations.email.dependencies import get_email_client
from app.integrations.telegram.client import TelegramClient
from app.integrations.telegram.dependencies import get_telegram_client
from app.modules.audit.public import AuditApi, get_audit_api
from app.modules.notifications.services.create_channel import CreateNotificationChannel
from app.modules.notifications.services.delete_channel import DeleteNotificationChannel
from app.modules.notifications.services.get_channel import GetNotificationChannel
from app.modules.notifications.services.list_channels import ListNotificationChannels
from app.modules.notifications.services.test_send_channel import TestSendNotificationChannel
from app.modules.notifications.services.update_channel import UpdateNotificationChannel
from app.modules.notifications.uow import AbstractNotificationsUnitOfWork, NotificationsUnitOfWork
from app.modules.projects.public import ProjectsApi, get_projects_api


async def get_uow(session: AsyncSession = Depends(get_session)) -> NotificationsUnitOfWork:
    return NotificationsUnitOfWork(session)


async def get_create_notification_channel(
    uow: AbstractNotificationsUnitOfWork = Depends(get_uow),
    projects_api: ProjectsApi = Depends(get_projects_api),
    audit_api: AuditApi = Depends(get_audit_api),
) -> CreateNotificationChannel:
    return CreateNotificationChannel(uow, projects_api, audit_api)


async def get_get_notification_channel(
    uow: AbstractNotificationsUnitOfWork = Depends(get_uow),
) -> GetNotificationChannel:
    return GetNotificationChannel(uow)


async def get_list_notification_channels(
    uow: AbstractNotificationsUnitOfWork = Depends(get_uow),
    projects_api: ProjectsApi = Depends(get_projects_api),
) -> ListNotificationChannels:
    return ListNotificationChannels(uow, projects_api)


async def get_update_notification_channel(
    uow: AbstractNotificationsUnitOfWork = Depends(get_uow),
    audit_api: AuditApi = Depends(get_audit_api),
) -> UpdateNotificationChannel:
    return UpdateNotificationChannel(uow, audit_api)


async def get_delete_notification_channel(
    uow: AbstractNotificationsUnitOfWork = Depends(get_uow),
    audit_api: AuditApi = Depends(get_audit_api),
) -> DeleteNotificationChannel:
    return DeleteNotificationChannel(uow, audit_api)


async def get_test_send_notification_channel(
    uow: AbstractNotificationsUnitOfWork = Depends(get_uow),
    telegram_client: TelegramClient = Depends(get_telegram_client),
    email_client: EmailClient = Depends(get_email_client),
    base_vn_client: BaseVnClient = Depends(get_base_vn_client),
    audit_api: AuditApi = Depends(get_audit_api),
) -> TestSendNotificationChannel:
    return TestSendNotificationChannel(
        uow, telegram_client=telegram_client, email_client=email_client,
        base_vn_client=base_vn_client, audit_api=audit_api,
    )
```

```python
# backend/app/modules/notifications/router.py
from uuid import UUID

from fastapi import APIRouter, Depends

from app.core.models import ApiResponse
from app.modules.notifications.dependencies import (
    get_create_notification_channel,
    get_delete_notification_channel,
    get_get_notification_channel,
    get_list_notification_channels,
    get_test_send_notification_channel,
    get_update_notification_channel,
)
from app.modules.notifications.schemas import (
    NotificationChannelCreate,
    NotificationChannelRead,
    NotificationChannelUpdate,
    TestSendRequest,
)
from app.modules.notifications.services.create_channel import CreateNotificationChannel
from app.modules.notifications.services.delete_channel import DeleteNotificationChannel
from app.modules.notifications.services.get_channel import GetNotificationChannel
from app.modules.notifications.services.list_channels import ListNotificationChannels
from app.modules.notifications.services.test_send_channel import TestSendNotificationChannel
from app.modules.notifications.services.update_channel import UpdateNotificationChannel
from app.modules.rbac.public import RbacActions, RbacResources, require_permission
from app.modules.users.public import UserRead

router = APIRouter(tags=["notifications"])


@router.post("/notification-channels")
async def create_notification_channel(
    body: NotificationChannelCreate,
    use_case: CreateNotificationChannel = Depends(get_create_notification_channel),
    user: UserRead = Depends(require_permission(RbacResources.NOTIFICATION_CHANNEL, RbacActions.CREATE)),
) -> ApiResponse[NotificationChannelRead]:
    channel = await use_case.execute(**body.model_dump(), actor=user)
    return ApiResponse[NotificationChannelRead](success=True, data=channel)


@router.get("/notification-channels")
async def list_notification_channels(
    project_id: UUID,
    environment_id: UUID | None = None,
    use_case: ListNotificationChannels = Depends(get_list_notification_channels),
    _user: UserRead = Depends(require_permission(RbacResources.NOTIFICATION_CHANNEL, RbacActions.READ)),
) -> ApiResponse[list[NotificationChannelRead]]:
    channels = await use_case.execute(project_id, environment_id=environment_id)
    return ApiResponse[list[NotificationChannelRead]](success=True, data=channels)


@router.get("/notification-channels/{channel_id}")
async def get_notification_channel(
    channel_id: UUID,
    use_case: GetNotificationChannel = Depends(get_get_notification_channel),
    _user: UserRead = Depends(require_permission(RbacResources.NOTIFICATION_CHANNEL, RbacActions.READ)),
) -> ApiResponse[NotificationChannelRead]:
    channel = await use_case.execute(channel_id)
    return ApiResponse[NotificationChannelRead](success=True, data=channel)


@router.patch("/notification-channels/{channel_id}")
async def update_notification_channel(
    channel_id: UUID,
    body: NotificationChannelUpdate,
    use_case: UpdateNotificationChannel = Depends(get_update_notification_channel),
    user: UserRead = Depends(require_permission(RbacResources.NOTIFICATION_CHANNEL, RbacActions.UPDATE)),
) -> ApiResponse[NotificationChannelRead]:
    channel = await use_case.execute(channel_id, **body.model_dump(exclude_unset=True), actor=user)
    return ApiResponse[NotificationChannelRead](success=True, data=channel)


@router.delete("/notification-channels/{channel_id}")
async def delete_notification_channel(
    channel_id: UUID,
    use_case: DeleteNotificationChannel = Depends(get_delete_notification_channel),
    user: UserRead = Depends(require_permission(RbacResources.NOTIFICATION_CHANNEL, RbacActions.DELETE)),
) -> ApiResponse[None]:
    await use_case.execute(channel_id, actor=user)
    return ApiResponse[None](success=True, data=None)


@router.post("/notification-channels/{channel_id}/test-send")
async def test_send_notification_channel(
    channel_id: UUID,
    body: TestSendRequest,
    use_case: TestSendNotificationChannel = Depends(get_test_send_notification_channel),
    user: UserRead = Depends(require_permission(RbacResources.NOTIFICATION_CHANNEL, RbacActions.UPDATE)),
) -> ApiResponse[None]:
    """UPDATE-gated, not READ (Decision #5) — exercises the channel's real
    stored secret to send a real external message."""
    await use_case.execute(channel_id, message=body.message, actor=user)
    return ApiResponse[None](success=True, data=None)
```

```python
# backend/app/modules/notifications/public.py
"""Contract exposed to other modules. Empty for now — Phase 9's alert
routing will add a facade method here to resolve channels for an alert
rule, once it exists."""

__all__: list[str] = []
```

Register in `backend/app/main.py`: `from app.modules.notifications.router import router as notifications_router` + `app.include_router(notifications_router, prefix="/api/v1")`, mirroring the exact existing registration block.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/notifications/ -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/integrations/telegram/dependencies.py app/integrations/email/dependencies.py app/integrations/base_vn/dependencies.py app/modules/notifications/dependencies.py app/modules/notifications/router.py app/modules/notifications/public.py app/main.py tests/notifications/test_router.py
git commit -m "feat(notifications): add router, dependencies, public facade, and main.py registration"
```

---

## Task 11: Full backend verification pass

**Files:** none (verification only).

- [ ] **Step 1: Run the full backend suite**

Run: `cd backend && ruff check && ruff format --check && python scripts/check_module_boundaries.py --strict && lint-imports && uv run pytest -q`
Expected: all green.

- [ ] **Step 2: Fix any failures, re-run until green**

- [ ] **Step 3: Commit if any fixes were needed**

```bash
git add -A
git commit -m "fix(notifications): resolve verification findings"
```

---

## Task 12: Frontend — `entities/notification-channel/`

**Files:**
- Create: `frontend/src/entities/notification-channel/{model/schema.ts,api/query-keys.ts,api/fetchers.ts,hooks/use-notification-channels.ts,index.ts}`
- Test: `frontend/src/entities/notification-channel/model/schema.test.ts`

**Interfaces:**
- Produces: `notificationChannelSchema`, `NOTIFICATION_CHANNEL_TYPES`, `notificationChannelsKeys`, `fetchNotificationChannels(projectId, environmentId?)`, `useNotificationChannelsQuery(projectId, environmentId?)`.

- [ ] **Step 1: Write the failing test**

Read `entities/cloudflare-account/model/schema.ts` first (the closest flat-entity precedent) before writing this.

```typescript
// frontend/src/entities/notification-channel/model/schema.test.ts
import { describe, expect, it } from "vitest";
import { notificationChannelSchema } from "./schema";

describe("notificationChannelSchema", () => {
  it("parses a telegram channel with masked config", () => {
    const parsed = notificationChannelSchema.parse({
      id: "b3f1c2e4-1111-4444-8888-000000000000",
      projectId: "b3f1c2e4-2222-4444-8888-000000000000",
      environmentId: null,
      type: "telegram",
      name: "Ops Alerts",
      config: { chatId: "1", hasBotToken: true },
      isActive: true,
      createdAt: "2026-01-01T00:00:00Z",
      updatedAt: "2026-01-01T00:00:00Z",
    });
    expect(parsed.type).toBe("telegram");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/entities/notification-channel/model/schema.test.ts`
Expected: FAIL (`Cannot find module './schema'`)

- [ ] **Step 3: Write the implementation**

```typescript
// frontend/src/entities/notification-channel/model/schema.ts
import { z } from "zod";

export const NOTIFICATION_CHANNEL_TYPES = ["email", "base_vn", "telegram", "other"] as const;
export type NotificationChannelType = (typeof NOTIFICATION_CHANNEL_TYPES)[number];

export const notificationChannelSchema = z.object({
  id: z.uuid(),
  projectId: z.uuid(),
  environmentId: z.uuid().nullable(),
  type: z.enum(NOTIFICATION_CHANNEL_TYPES),
  name: z.string(),
  config: z.record(z.string(), z.unknown()),
  isActive: z.boolean(),
  createdAt: z.string(),
  updatedAt: z.string(),
});
export type NotificationChannel = z.infer<typeof notificationChannelSchema>;
```

```typescript
// frontend/src/entities/notification-channel/api/query-keys.ts
export const notificationChannelsKeys = {
  all: ["notification-channels"] as const,
  list: (projectId: string, environmentId?: string) =>
    [...notificationChannelsKeys.all, "list", projectId, environmentId ?? null] as const,
  detail: (id: string) => [...notificationChannelsKeys.all, "detail", id] as const,
};
```

```typescript
// frontend/src/entities/notification-channel/api/fetchers.ts
import { apiFetch } from "@/shared/lib/api-client";
import { API_CONFIG } from "@/shared/constants/api";
import { notificationChannelSchema, type NotificationChannel } from "../model/schema";

export async function fetchNotificationChannels(
  projectId: string,
  environmentId?: string,
): Promise<NotificationChannel[]> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.NOTIFICATION_CHANNELS.ROOT, {
    params: { projectId, ...(environmentId && { environmentId }) },
  });
  return notificationChannelSchema.array().parse(raw);
}
```

Confirm `API_CONFIG.ENDPOINTS.NOTIFICATION_CHANNELS` gets added to `shared/constants/api.ts` in Task 13 before this compiles — this file's `import` will dangle until then; write Task 13's `api.ts` addition first if executing tasks out of written order, or accept the temporary red state within this same working session.

```typescript
// frontend/src/entities/notification-channel/hooks/use-notification-channels.ts
"use client";

import { useSuspenseQuery } from "@tanstack/react-query";
import { fetchNotificationChannels } from "../api/fetchers";
import { notificationChannelsKeys } from "../api/query-keys";

export function useNotificationChannelsQuery(projectId: string, environmentId?: string) {
  return useSuspenseQuery({
    queryKey: notificationChannelsKeys.list(projectId, environmentId),
    queryFn: () => fetchNotificationChannels(projectId, environmentId),
  });
}
```

```typescript
// frontend/src/entities/notification-channel/index.ts
export { fetchNotificationChannels } from "./api/fetchers";
export { notificationChannelsKeys } from "./api/query-keys";
export { useNotificationChannelsQuery } from "./hooks/use-notification-channels";
export { notificationChannelSchema, NOTIFICATION_CHANNEL_TYPES } from "./model/schema";
export type { NotificationChannel, NotificationChannelType } from "./model/schema";
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/entities/notification-channel/model/schema.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/entities/notification-channel
git commit -m "feat(notification-channel): add entities layer (schema, query-keys, fetchers, read hook)"
```

---

## Task 13: Frontend — `shared/constants/api.ts` + `permissions.ts` additions

**Files:**
- Modify: `frontend/src/shared/constants/api.ts`
- Modify: `frontend/src/shared/constants/permissions.ts`

- [ ] **Step 1: Add the endpoint block**

```typescript
// add to API_CONFIG.ENDPOINTS in shared/constants/api.ts
NOTIFICATION_CHANNELS: {
  ROOT: "/notification-channels",
  DETAIL: (id: string) => `/notification-channels/${id}`,
  TEST_SEND: (id: string) => `/notification-channels/${id}/test-send`,
},
```

- [ ] **Step 2: Add the permission constants**

Read `shared/constants/permissions.ts`'s `ENVIRONMENT` block first (the CRUD-shaped precedent to mirror, not `CLOUDFLARE_ACCOUNT`'s view/manage shape):
```typescript
// add to RESOURCES
NOTIFICATION_CHANNEL: "notification_channel",
```
```typescript
// add to PERMISSIONS
NOTIFICATION_CHANNEL: {
  RESOURCE: RESOURCES.NOTIFICATION_CHANNEL,
  CREATE: `${RESOURCES.NOTIFICATION_CHANNEL}.${ACTIONS.CREATE}` as const,
  READ: `${RESOURCES.NOTIFICATION_CHANNEL}.${ACTIONS.READ}` as const,
  UPDATE: `${RESOURCES.NOTIFICATION_CHANNEL}.${ACTIONS.UPDATE}` as const,
  DELETE: `${RESOURCES.NOTIFICATION_CHANNEL}.${ACTIONS.DELETE}` as const,
},
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npx tsc --noEmit`

- [ ] **Step 4: Commit**

```bash
git add frontend/src/shared/constants/api.ts frontend/src/shared/constants/permissions.ts
git commit -m "feat(notifications): add API endpoints and permission constants"
```

---

## Task 14: Frontend — `modules/notifications/` (hooks, form dialog, page section, wiring into project detail page)

**Files:**
- Create: `frontend/src/modules/notifications/api/fetchers.ts`
- Create: `frontend/src/modules/notifications/hooks/{use-create-channel,use-update-channel,use-delete-channel,use-test-send-channel}.ts`
- Create: `frontend/src/modules/notifications/ui/{notification-channel-form-dialog,notification-channels-section}.tsx`
- Create: `frontend/src/modules/notifications/index.ts`
- Modify: `frontend/src/modules/projects/ui/project-detail-view.tsx`
- Create: `frontend/locales/{en,vi}/modules/notifications.json`
- Modify: `frontend/src/shared/lib/i18n/request.ts`

**Interfaces:**
- Consumes: `entities/notification-channel` (Task 12), `useProjectQuery`/whatever `project-detail-view.tsx` already uses for the current project id and its environment list.

- [ ] **Step 1: Invoke `ui-ux-pro-max` before writing markup**

Mandatory per AGENTS.md Phase 3 rule. Query for a channel-type-conditional form (mirrors `loki-config-form-dialog.tsx`'s auth-type-conditional pattern from Phase 6, and `dns-record-form-dialog.tsx`'s record-type-conditional pattern from Phase 4) and a "send test" action's feedback state:
```bash
python "/Users/hoangdieu/.claude/plugins/cache/ui-ux-pro-max-skill/ui-ux-pro-max/2.13.0/.claude/skills/ui-ux-pro-max/scripts/search.py" "test action button success failure feedback" --domain ux
python "/Users/hoangdieu/.claude/plugins/cache/ui-ux-pro-max-skill/ui-ux-pro-max/2.13.0/.claude/skills/ui-ux-pro-max/scripts/search.py" "conditional form fields by type" --domain ux
```

- [ ] **Step 2: Fetchers + mutation hooks**

```typescript
// frontend/src/modules/notifications/api/fetchers.ts
import { apiFetch } from "@/shared/lib/api-client";
import { API_CONFIG } from "@/shared/constants/api";
import { notificationChannelSchema, type NotificationChannel, type NotificationChannelType } from "@/entities/notification-channel";

export interface NotificationChannelFormValues {
  projectId: string;
  environmentId: string | null;
  type: NotificationChannelType;
  name: string;
  config: Record<string, unknown>;
}

export async function createNotificationChannel(data: NotificationChannelFormValues): Promise<NotificationChannel> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.NOTIFICATION_CHANNELS.ROOT, { method: "POST", data });
  return notificationChannelSchema.parse(raw);
}

export async function updateNotificationChannel(
  id: string,
  data: Partial<Pick<NotificationChannelFormValues, "name" | "config">> & { isActive?: boolean },
): Promise<NotificationChannel> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.NOTIFICATION_CHANNELS.DETAIL(id), { method: "PATCH", data });
  return notificationChannelSchema.parse(raw);
}

export async function deleteNotificationChannel(id: string): Promise<void> {
  await apiFetch<unknown>(API_CONFIG.ENDPOINTS.NOTIFICATION_CHANNELS.DETAIL(id), { method: "DELETE" });
}

export async function testSendNotificationChannel(id: string, message?: string): Promise<void> {
  await apiFetch<unknown>(API_CONFIG.ENDPOINTS.NOTIFICATION_CHANNELS.TEST_SEND(id), {
    method: "POST",
    data: { message },
  });
}
```

4 mutation hooks (`use-create-channel.ts`, `use-update-channel.ts`, `use-delete-channel.ts`, `use-test-send-channel.ts`), each mirroring `modules/log-viewer/hooks/use-loki-config.ts`'s exact `useMutation` + `queryClient.invalidateQueries({ queryKey: notificationChannelsKeys.list(projectId, environmentId) })` pattern on success. `use-test-send-channel.ts` does NOT invalidate any query (a test-send doesn't change the channel's own data) — mirrors why `useRunLogQuery` (Phase 6) never invalidates anything either.

- [ ] **Step 3: Form dialog**

`notification-channel-form-dialog.tsx` mirrors `loki-config-form-dialog.tsx`'s structure: a `type` `<select>` (immutable when editing — matches `record_type`'s and `auth_type`'s... actually `auth_type` IS editable in Loki's dialog; for notifications, `type` is immutable per Update schema Task 9 excludes it from `NotificationChannelUpdate` — disable the `<select>` when `channel !== null`, matching `RecordTypeField`'s `disabled={isEditing}` precedent from Phase 4's DNS dialog exactly), then conditionally rendered fields per selected type:
- `EMAIL`: a `recipients` multi-value text input (comma-separated, split/joined at the boundary — no multi-value input component exists elsewhere in this repo to reuse, keep it simple).
- `TELEGRAM`: `bot_token` (password-type input with show/hide toggle, mirrors `CredentialField` from Phase 6 exactly) + `chat_id` (plain text).
- `BASE_VN`: `webhook_url` (password-type input with show/hide toggle — same reasoning as Cloudflare/Loki secrets, it's bearer-equivalent) + `bot_name` (plain text) + `message_template` (plain text, with a hint mentioning the `{message}` placeholder).
- `OTHER`: a raw JSON textarea (free-form, matches its schema-level freedom) — parse/stringify at the form boundary, catch a JSON parse error inline rather than crashing the form.

- [ ] **Step 4: `notification-channels-section.tsx`**

A `<section>` matching `project-detail-view.tsx`'s existing Environments/Links card style exactly (`className="flex flex-col gap-3 rounded-xl border bg-card p-5"`), listing channels via `useNotificationChannelsQuery(projectId)`, each row showing name/type/active-state + edit/delete/"Send test" actions gated by `<Can I={ACTIONS.UPDATE|DELETE} a={RESOURCES.NOTIFICATION_CHANNEL}>`. "Send test" shows inline pending/success/error state next to the button (no separate dialog) using the mutation hook's own `isPending`/`isSuccess`/`error` — matches the ui-ux-pro-max guidance queried in Step 1 once results are in hand.

- [ ] **Step 5: Wire into `project-detail-view.tsx`**

Add `<NotificationChannelsSection projectId={projectId} />` as a third `<section>`, after the existing Links section, reading the current file fresh first to match its exact import/composition style.

- [ ] **Step 6: i18n**

`locales/{en,vi}/modules/notifications.json` with keys for the section title, form fields per type, "Send test" states, delete confirmation. Register in `shared/lib/i18n/request.ts` following the exact pattern every prior phase's locale file registration used.

- [ ] **Step 7: `index.ts`**

```typescript
export { NotificationChannelsSection } from "./ui/notification-channels-section";
```

- [ ] **Step 8: Verify**

Run: `cd frontend && npx tsc --noEmit && npm run lint && npx vitest run && npm run build`

- [ ] **Step 9: Manual smoke test**

Requires real Telegram bot / Base.vn webhook / SMTP credentials this environment does not have — disclose explicitly if skipped rather than claiming it passed, same as Phase 6/7's own external-dependency disclosures.

- [ ] **Step 10: Commit**

```bash
git add frontend/src/modules/notifications frontend/src/modules/projects/ui/project-detail-view.tsx frontend/locales frontend/src/shared/lib/i18n/request.ts
git commit -m "feat(notifications): add channel CRUD UI, test-send action, and project detail page section"
```

---

## Task 15: GitNexus + skills review + finish branch

**Files:** none (verification + branch lifecycle only).

- [ ] **Step 1: Re-index and review impact**

```bash
node .gitnexus/run.cjs analyze
```
If it fails with an FTS index corruption error (seen twice already this session), run `node .gitnexus/run.cjs clean --force && npx gitnexus analyze` to rebuild from scratch. If `detect_changes`/`check` MCP tools are exposed this session, use them; otherwise `git diff develop..feature/notification-channels --stat` and compare against this plan's Architecture Impact section.

- [ ] **Step 2: Full verification, both stacks**

```bash
cd backend && ruff check && ruff format --check && python scripts/check_module_boundaries.py --strict && lint-imports && uv run pytest -q
cd ../frontend && npx tsc --noEmit && npm run lint && npx vitest run && npm run build
```

- [ ] **Step 3: `reviewing-code-against-skills` checklist**

Fix loop: max 2 rounds for architectural findings, unlimited for mechanical/lint findings.

- [ ] **Step 4: Finish the branch**

Use superpowers:finishing-a-development-branch. Present the standard 3-option menu (base branch `develop`). On "Merge back to develop locally": merge `--no-ff`, re-run both verification commands from Step 2 against the merged result, delete the branch only after both pass.
