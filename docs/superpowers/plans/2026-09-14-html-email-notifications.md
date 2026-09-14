# HTML Email Notifications Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Send incident notifications rendered from a structured event: an HTML email with the incident's severity, project, environment, detection time and a link back into the app, plus a plain-text rendering for Telegram and Base.vn. All display text is Vietnamese and lives in one `i18n.yml`.

**Architecture:** `NotificationsApi.dispatch` takes a `NotificationEvent` instead of a string. `NotificationTemplates` in `notifications/utils/loader.py` loads the Jinja2 templates and `i18n.yml` once at class level and renders subject, HTML and text. `EmailClient.send` gains an optional `html` and sends `multipart/alternative`.

**Tech Stack:** Python 3.11, Jinja2 3.1.6, PyYAML, `email.message.EmailMessage`, aiosmtplib, pytest.

**Spec:** `docs/superpowers/specs/2026-09-14-html-email-notifications-design.md`

## Global Constraints

- **Git:** branch `feature/html-email-notifications`, created from `develop` at `6801234`. Local commits only; merging needs explicit approval.
- **fastapi-modular-scaffold:**
  - Template wording belongs to `modules/notifications`; `integrations/email` stays transport only.
  - Rule #16: no bare constants or functions at module level — `NotificationTemplates` is a class with `@helper` methods, and new constants are class attributes in `constants.py`.
  - Rule #18 import order: `constants` → `schemas` → `rules`/`utils` → `repository`/`uow` → `services` → `dependencies` → `router` → `public`.
  - Docstrings, not `#` comments.
  - Cross-module data crosses through `public.py` only.
- **Behaviour:** the per-channel `try`/`except` and the `sent`/`failed` audit entry around each dispatch stay exactly as they are — a broken channel must never block incident creation.
- **Wording:** every user-visible string is Vietnamese and comes from `i18n.yml`. No Vietnamese string literals in Python.
- **Test command:** `CACHE__URL=redis://localhost:6379/0 uv run pytest <path> -q -p no:cacheprovider`, with Docker running and `docker compose up -d redis`.
- **Gates:** `ruff check app tests`, `ruff format --check app tests`, `lint-imports` (10 kept), `check_module_boundaries.py --strict`, OpenAPI still 65 paths, the full backend suite, and GitNexus `detect-changes` + `check --cycles`.

## Impact (GitNexus, upstream)

| Symbol | Risk | Mitigation |
|---|---|---|
| `NotificationsApi.dispatch` | MEDIUM — the one cross-module entry point, called by both webhooks | The signature change and both call sites land in the same task (Task 4), with the full suite after it. |
| `DispatchNotification` | LOW (1 direct) | Task 3, covered by `tests/notifications/test_services.py`. |
| `EmailClient.send` | LOW (2 direct: dispatch, and the test fakes) | `html` is optional, so the single-part path is unchanged; Task 2. |
| `TestSendNotificationChannel` | LOW | Task 4. |

## File Map

| Task | Create | Modify |
|---|---|---|
| 1 | `app/modules/notifications/templates/{i18n.yml,base.html,incident_detected.html,incident_detected.txt,test.html,test.txt}`, `app/modules/notifications/utils/{__init__.py,loader.py}`, `tests/notifications/test_loader.py` | `app/modules/notifications/{constants,schemas}.py` |
| 2 | — | `app/integrations/email/client.py`, `tests/integrations/email/test_client.py` |
| 3 | — | `app/modules/notifications/services/dispatch_notification.py`, `tests/notifications/test_services.py` |
| 4 | — | `app/modules/notifications/public.py`, `services/test_send_channel.py`, `app/modules/observability/services/webhooks/{handle_cloudflare_webhook,handle_loki_webhook}.py`, `tests/notifications/test_public.py`, `tests/observability/test_services.py` |
| 5 | — | `backend/README.md` if needed, this plan (execution notes) |

---

### Task 1: The event, the templates and the loader

**Files:**
- Create: the six template files, `utils/__init__.py`, `utils/loader.py`, `tests/notifications/test_loader.py`
- Modify: `app/modules/notifications/constants.py`, `app/modules/notifications/schemas.py`

**Interfaces:**
- Produces `NotificationKind(StrEnum)` in `constants.py`: `INCIDENT_DETECTED = "incident_detected"`, `TEST = "test"`.
- Produces `NotificationTemplateDefaults` in `constants.py`: `DIRECTORY = "templates"`, `I18N_FILE = "i18n.yml"`, `INCIDENT_PATH = "/admin/incidents"`, `DATETIME_FORMAT = "%d/%m/%Y %H:%M"`.
- Produces `NotificationEvent(FrozenModel)` in `schemas.py` with the fields in the spec's table.
- Produces `NotificationTemplates` in `utils/loader.py` with `subject(event) -> str`, `render_html(event) -> str`, `render_text(event) -> str`.

- [ ] **Step 1: Write the failing test** `tests/notifications/test_loader.py`

```python
"""Unit tests for the notification template loader — no I/O beyond reading
the module's own template files."""

from datetime import UTC, datetime

import pytest

from app.modules.notifications.constants import NotificationKind
from app.modules.notifications.schemas import NotificationEvent
from app.modules.notifications.utils import NotificationTemplates


def _incident_event(**overrides) -> NotificationEvent:
    defaults = {
        "kind": NotificationKind.INCIDENT_DETECTED,
        "title": "DDoS trên example.com",
        "severity": "CRITICAL",
        "category": "DDOS",
        "source": "CLOUDFLARE",
        "detected_at": datetime(2026, 9, 14, 10, 30, tzinfo=UTC),
        "project_name": "Cổng thanh toán",
        "environment_name": "Production",
        "rule_name": "Cảnh báo DDoS",
        "incident_url": "https://itsm.test/admin/incidents",
    }
    defaults.update(overrides)
    return NotificationEvent(**defaults)


class TestSubject:
    def test_incident_subject_carries_the_severity_and_title(self) -> None:
        subject = NotificationTemplates.subject(_incident_event())

        assert "Nghiêm trọng" in subject
        assert "DDoS trên example.com" in subject

    def test_test_event_has_its_own_subject(self) -> None:
        event = NotificationEvent(kind=NotificationKind.TEST, title="Xin chào")

        assert NotificationTemplates.subject(event) != ""
        assert "{" not in NotificationTemplates.subject(event)


class TestRenderHtml:
    def test_incident_html_shows_every_field_in_vietnamese(self) -> None:
        html = NotificationTemplates.render_html(_incident_event())

        for expected in (
            "DDoS trên example.com",
            "Nghiêm trọng",
            "Cổng thanh toán",
            "Production",
            "Cảnh báo DDoS",
            "14/09/2026",
            "https://itsm.test/admin/incidents",
        ):
            assert expected in html
        assert "{{" not in html

    def test_missing_optional_fields_leave_no_empty_rows(self) -> None:
        html = NotificationTemplates.render_html(
            NotificationEvent(kind=NotificationKind.INCIDENT_DETECTED, title="Chỉ có tiêu đề")
        )

        assert "Chỉ có tiêu đề" in html
        assert "Mức độ" not in html
        assert "None" not in html

    def test_html_escapes_the_title(self) -> None:
        html = NotificationTemplates.render_html(_incident_event(title="<script>x</script>"))

        assert "<script>" not in html
        assert "&lt;script&gt;" in html


class TestRenderText:
    def test_incident_text_is_plain_and_complete(self) -> None:
        text = NotificationTemplates.render_text(_incident_event())

        assert "DDoS trên example.com" in text
        assert "Nghiêm trọng" in text
        assert "<" not in text
        assert "{{" not in text

    def test_text_does_not_escape_html_entities(self) -> None:
        text = NotificationTemplates.render_text(_incident_event(title="A & B"))

        assert "A & B" in text


class TestI18nCoverage:
    @pytest.mark.parametrize("kind", list(NotificationKind))
    def test_every_kind_renders_all_three_outputs(self, kind: NotificationKind) -> None:
        event = NotificationEvent(kind=kind, title="Tiêu đề")

        assert NotificationTemplates.subject(event)
        assert NotificationTemplates.render_html(event)
        assert NotificationTemplates.render_text(event)

    def test_every_severity_has_a_label(self) -> None:
        from app.modules.observability.constants import AlertSeverity

        for severity in AlertSeverity:
            assert NotificationTemplates.severity_label(severity.value) != severity.value
```

- [ ] **Step 2: Run it and confirm it fails.** Run: `... pytest tests/notifications/test_loader.py`. Expected: `ImportError` for `NotificationKind`.

- [ ] **Step 3: Constants and schema.**

In `constants.py`, add next to the existing classes:

```python
class NotificationKind(StrEnum):
    """What happened, deciding which template and subject a notification uses."""

    INCIDENT_DETECTED = "incident_detected"
    TEST = "test"


class NotificationTemplateDefaults:
    """Where the templates live and how they format values."""

    DIRECTORY = "templates"
    I18N_FILE = "i18n.yml"
    INCIDENT_PATH = "/admin/incidents"
    DATETIME_FORMAT = "%d/%m/%Y %H:%M"
```

In `schemas.py`:

```python
class NotificationEvent(FrozenModel):
    """What happened, in the shape the templates render. Every field beyond kind
    and title is optional: the test-send event carries only a title."""

    kind: NotificationKind
    title: str
    severity: str | None = None
    category: str | None = None
    source: str | None = None
    detected_at: datetime | None = None
    project_name: str | None = None
    environment_name: str | None = None
    rule_name: str | None = None
    incident_url: str | None = None
```

- [ ] **Step 4: Write `templates/i18n.yml`**

```yaml
subjects:
  incident_detected: "[{severity}] Sự cố mới: {title}"
  test: "Thông báo thử từ ITSM"
headings:
  incident_detected: "Phát hiện sự cố mới"
  test: "Thông báo thử"
labels:
  severity: "Mức độ"
  category: "Loại sự cố"
  source: "Nguồn phát hiện"
  project: "Dự án"
  environment: "Môi trường"
  detected_at: "Thời điểm phát hiện"
  rule: "Quy tắc cảnh báo"
  view_incident: "Xem sự cố"
  footer: "Email này được gửi tự động từ hệ thống ITSM."
  test_body: "Nếu bạn nhận được email này, kênh thông báo đã cấu hình đúng."
severity:
  LOW: "Thấp"
  MEDIUM: "Trung bình"
  HIGH: "Cao"
  CRITICAL: "Nghiêm trọng"
category:
  TRAFFIC: "Lưu lượng"
  DDOS: "Tấn công DDoS"
  ORIGIN_ERROR: "Lỗi máy chủ gốc"
  DNS_DRIFT: "Sai lệch DNS"
  TUNNEL_DRIFT: "Sai lệch Tunnel"
  LOG_MATCH: "Khớp mẫu log"
  MANUAL: "Tạo thủ công"
source:
  CLOUDFLARE: "Cloudflare"
  LOKI: "Grafana Loki"
  MANUAL: "Thủ công"
```

- [ ] **Step 5: Write the templates.**

`base.html` is the shell: an inline-styled container with the heading, a `{% block body %}` and the footer. Inline CSS only — email clients drop `<style>` blocks. `incident_detected.html` extends it and renders a two-column table, one row per present field, using `labels`. `test.html` extends it and renders `labels.test_body`. The `.txt` pair renders the same content as `Nhãn: giá trị` lines with no markup.

- [ ] **Step 6: Write `utils/loader.py`**

```python
"""Renders a NotificationEvent into the subject, HTML and text a channel sends."""

from functools import cached_property
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from app.core.base.markers import helper
from app.modules.notifications.constants import NotificationKind, NotificationTemplateDefaults
from app.modules.notifications.schemas import NotificationEvent


class NotificationTemplates:
    """Loads the Jinja2 templates and i18n.yml once, then renders one event.

    StrictUndefined on purpose: a template naming a key i18n.yml doesn't have
    must fail the test suite, not ship an email with a blank cell.
    """

    _DIRECTORY = Path(__file__).resolve().parent.parent / NotificationTemplateDefaults.DIRECTORY
    _environment = Environment(
        loader=FileSystemLoader(_DIRECTORY),
        autoescape=select_autoescape(default_for_string=False, enabled_extensions=("html",)),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    _text: dict[str, Any] = yaml.safe_load(
        (_DIRECTORY / NotificationTemplateDefaults.I18N_FILE).read_text(encoding="utf-8")
    )

    @classmethod
    @helper
    def subject(cls, event: NotificationEvent) -> str:
        """The email subject for this kind, with the severity label filled in."""
        template = cls._text["subjects"][event.kind.value]
        return template.format(severity=cls.severity_label(event.severity), title=event.title)

    @classmethod
    @helper
    def render_html(cls, event: NotificationEvent) -> str:
        """The HTML body for this kind."""
        return cls._render(f"{event.kind.value}.html", event)

    @classmethod
    @helper
    def render_text(cls, event: NotificationEvent) -> str:
        """The plain-text body for this kind, for Telegram, Base.vn and the email's text part."""
        return cls._render(f"{event.kind.value}.txt", event)

    @classmethod
    @helper
    def severity_label(cls, severity: str | None) -> str:
        """The Vietnamese label for a severity, or an empty string when absent."""
        return cls._text["severity"].get(severity, severity or "")

    @classmethod
    @helper
    def _render(cls, name: str, event: NotificationEvent) -> str:
        """Render one template with the event and the shared wording."""
        return cls._environment.get_template(name).render(
            event=event,
            labels=cls._text["labels"],
            heading=cls._text["headings"][event.kind.value],
            severity_label=cls.severity_label(event.severity),
            category_label=cls._text["category"].get(event.category, event.category),
            source_label=cls._text["source"].get(event.source, event.source),
            detected_at=(
                event.detected_at.strftime(NotificationTemplateDefaults.DATETIME_FORMAT)
                if event.detected_at
                else None
            ),
        )
```

Drop `cached_property` from the imports if it ends up unused.

`utils/__init__.py`:

```python
"""Non business helpers for the notifications module, grouped by concern."""

from app.modules.notifications.utils.loader import NotificationTemplates

__all__ = ["NotificationTemplates"]
```

- [ ] **Step 7: Run.** Run: `... pytest tests/notifications/test_loader.py`. Expected: all pass.

- [ ] **Step 8: Commit** `feat(notifications): render notification events from Jinja2 templates and one i18n file`.

---

### Task 2: Email sends multipart/alternative

**Files:** `app/integrations/email/client.py`, `tests/integrations/email/test_client.py`

**Interfaces:** `EmailClient.send(*, recipients: list[str], subject: str, body: str, html: str | None = None) -> None`.

- [ ] **Step 1: Write the failing tests.** Append to `tests/integrations/email/test_client.py`:

```python
class TestHtmlAlternative:
    async def test_sends_both_parts_with_text_first(self) -> None:
        with patch("app.integrations.email.client.aiosmtplib.send", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = ({}, "OK")
            await EmailClient().send(
                recipients=["a@b.com"], subject="Test", body="Xin chào", html="<p>Xin chào</p>"
            )

        message = mock_send.await_args.args[0]
        assert message.get_content_type() == "multipart/alternative"
        subtypes = [part.get_content_subtype() for part in message.iter_parts()]
        assert subtypes == ["plain", "html"]

    async def test_stays_single_part_without_html(self) -> None:
        with patch("app.integrations.email.client.aiosmtplib.send", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = ({}, "OK")
            await EmailClient().send(recipients=["a@b.com"], subject="Test", body="Xin chào")

        message = mock_send.await_args.args[0]
        assert message.get_content_type() == "text/plain"
```

- [ ] **Step 2: Run and confirm the failure** (`TypeError: unexpected keyword argument 'html'`).

- [ ] **Step 3: Implement.** In `client.py`, change the signature to add `html: str | None = None`, keep `message.set_content(body)`, and after it:

```python
        if html is not None:
            message.add_alternative(html, subtype="html")
```

Update the docstring to say the text part is set first so a client that can't render HTML still shows something.

- [ ] **Step 4: Run.** Run: `... pytest tests/integrations/email`. Expected: all pass.

- [ ] **Step 5: Commit** `feat(email): send an HTML alternative alongside the text body`.

---

### Task 3: Dispatch renders per channel

**Files:** `app/modules/notifications/services/dispatch_notification.py`, `tests/notifications/test_services.py`

**Interfaces:** `DispatchNotification.execute(channel: NotificationChannelRead, event: NotificationEvent) -> None`.

- [ ] **Step 1: Update the tests first.** In `tests/notifications/test_services.py`:
  - Add a `FakeEmailClient` recording `(recipients, subject, body, html)`.
  - Change the dispatch tests to pass a `NotificationEvent` instead of a string.
  - Add: an email channel receives an HTML part whose text contains the title; Telegram receives text with no `<` in it; Base.vn still runs through `message_template`.

- [ ] **Step 2: Run and confirm the failure.**

- [ ] **Step 3: Implement.** `execute` takes `event: NotificationEvent`, renders once:

```python
        text = NotificationTemplates.render_text(event)
```

  - Telegram: `text=text`.
  - Email: `subject=NotificationTemplates.subject(event)`, `body=text`, `html=NotificationTemplates.render_html(event)`.
  - Base.vn: `NotificationRules.render_base_content(config.get("message_template", ""), text)`.

- [ ] **Step 4: Run.** Run: `... pytest tests/notifications`. Expected: all pass.

- [ ] **Step 5: Commit** `feat(notifications): dispatch a rendered event per channel`.

---

### Task 4: Call sites build the event

**Files:** `app/modules/notifications/public.py`, `services/test_send_channel.py`, both observability webhooks, `tests/notifications/test_public.py`, `tests/observability/test_services.py`

**Interfaces:**
- `NotificationsApi.dispatch(channel_id: UUID, event: NotificationEvent) -> None`.
- `notifications.public` exports `NotificationEvent` and `NotificationKind`.

- [ ] **Step 1: Update the tests first.**
  - `tests/notifications/test_public.py`: `dispatch` takes an event; assert the email fake got a subject and an HTML part.
  - `tests/observability/test_services.py`: `FakeNotificationsApiForWebhook.dispatch(channel_id, event)` records `(channel_id, event)`; the existing assertions on the dispatched title become `event.title`; add one asserting `event.severity` and `event.environment_name` are carried.

- [ ] **Step 2: Run and confirm the failure.**

- [ ] **Step 3: Implement.**
  - `public.py`: `dispatch` takes `event: NotificationEvent`; add both names to the imports and `__all__`.
  - `test_send_channel.py`: build `NotificationEvent(kind=NotificationKind.TEST, title=message or NotificationsDefaults.TEST_MESSAGE)`.
  - Both webhooks: after creating the incident, build

    ```python
    project = await self._projects_api.get_project_by_id(incident.project_id)
    event = NotificationEvent(
        kind=NotificationKind.INCIDENT_DETECTED,
        title=title,
        severity=incident.severity.value,
        category=incident.category.value,
        source=incident.source.value,
        detected_at=incident.detected_at,
        project_name=project.name if project else None,
        environment_name=environment.name,
        rule_name=rule.name,
        incident_url=f"{settings.FRONTEND_BASE_URL.rstrip('/')}{NotificationTemplateDefaults.INCIDENT_PATH}",
    )
    ```

    and pass `event` to `dispatch`. The Cloudflare webhook's `_fan_out` takes the event instead of `message`. `NotificationTemplateDefaults` comes through `notifications.public`, so add it there too.

- [ ] **Step 4: Run.** Run: the full backend suite. Expected: all pass.

- [ ] **Step 5: Commit** `feat(observability): send incident notifications as a structured event`.

---

### Task 5: Gates and notes

- [ ] **Step 1: Run every gate** from Global Constraints, plus `grep -rn "Tiếng\|Sự cố\|Mức độ" app --include=*.py` to confirm no Vietnamese string literal sits in Python.
- [ ] **Step 2: Check the templates ship** — `uv run python -c "from app.modules.notifications.utils import NotificationTemplates; print(NotificationTemplates.subject(...))"` from a different working directory, proving the loader resolves its path from `__file__` rather than the process's cwd.
- [ ] **Step 3: GitNexus** — `analyze --force`, restore `AGENTS.md`/`CLAUDE.md`, `detect-changes --scope compare --base-ref develop`, `check --cycles`.
- [ ] **Step 4: Append `## Execution Notes`** and commit `docs: record how the HTML email notification work went`.

## Self-Review

- **Spec coverage:** §1 payload and layout → Task 1; §2 per-channel delivery → Tasks 2 and 3; §3 call sites and testing → Task 4; gates → Task 5.
- **Placeholders:** none — every step carries the code or the exact command.
- **Type consistency:** `NotificationKind`, `NotificationEvent`, `NotificationTemplates`, `NotificationTemplateDefaults`, `subject`, `render_html`, `render_text`, `severity_label` and `EmailClient.send(html=...)` are spelled the same in every task.
- **Risk noted:** `StrictUndefined` turns a missing i18n key into a test failure rather than a blank cell in a sent email — deliberate, and Task 1's coverage test exists to catch it early.
