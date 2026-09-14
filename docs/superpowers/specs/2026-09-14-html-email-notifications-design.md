# HTML Email Notifications — Design

- **Date:** 2026-09-14
- **Status:** approved in chat, section by section.
- **Scope:** `app/modules/notifications`, `app/integrations/email`, the two observability webhooks.

## Problem

Every notification this app sends is one line of text. `NotificationsApi.dispatch(channel_id, message: str)` takes a string, and the email channel sends it as `text/plain` under the hardcoded subject "ITSM Notification". A recipient sees the incident title and nothing else: not the severity, not which project or environment, not when it was detected, and no way back into the app.

The string is built by the caller, so each channel gets the same text no matter what it can render, and the wording lives inline in Python across the observability module.

## Decisions

1. **Structured payload.** `dispatch` takes a `NotificationEvent` instead of a string. Templates render it per channel: HTML for email, plain text for Telegram and Base.vn.
2. **Vietnamese, from one file.** All display text lives in a single `i18n.yml`. The backend has no i18n mechanism today — error codes are translated by the frontend — and a notification email is the one thing the backend renders for a human, so it carries its own wording rather than growing a translation layer.
3. **A loader owns both.** One `loader.py` loads the Jinja2 templates and `i18n.yml`, and exposes rendering to the module.
4. **Scope:** the two flows that dispatch today — the Cloudflare webhook and the Loki webhook — plus the test-send button. Acknowledge, resolve and drift reconciliation only write audit entries today; adding notifications there is a separate decision.

## 1. Payload and file layout

`NotificationEvent` is a `FrozenModel` owned by `notifications/schemas.py`:

| Field | Type | Source |
|---|---|---|
| `kind` | `NotificationKind` | `INCIDENT_DETECTED` or `TEST` |
| `title` | `str` | `incident.title`, the string dispatched today |
| `severity` | `str \| None` | `incident.severity` |
| `category` | `str \| None` | `incident.category` |
| `source` | `str \| None` | `incident.source` |
| `detected_at` | `datetime \| None` | `incident.detected_at` |
| `project_name` | `str \| None` | `ProjectsApi.get_project_by_id` |
| `environment_name` | `str \| None` | `ProjectsApi.get_environment_by_id`, already loaded by both webhooks |
| `rule_name` | `str \| None` | `AlertRuleRead.name` |
| `incident_url` | `str \| None` | `FRONTEND_BASE_URL` + `/admin/incidents` |

Every field but `kind` and `title` is optional, so the test-send event carries only what it has.

Files, in the notifications module because the wording of a notification is this module's concern while `integrations/email` is only transport:

```
app/modules/notifications/
├── templates/
│   ├── i18n.yml
│   ├── base.html
│   ├── incident_detected.html
│   ├── incident_detected.txt
│   ├── test.html
│   └── test.txt
└── utils/
    ├── __init__.py
    └── loader.py
```

`loader.py` holds one class, `NotificationTemplates`, with `@helper` methods `subject(event)`, `render_html(event)` and `render_text(event)`. The Jinja2 `Environment` and the parsed `i18n.yml` are built once at class level, not per send. `autoescape` is on for `.html` and off for `.txt`.

`i18n.yml` keys the wording by kind, plus the enum labels:

```yaml
subjects:
  incident_detected: "[{severity}] Sự cố mới: {title}"
  test: "Thông báo thử từ ITSM"
labels:
  severity: "Mức độ"
  project: "Dự án"
  environment: "Môi trường"
  detected_at: "Thời điểm phát hiện"
  rule: "Quy tắc cảnh báo"
  view_incident: "Xem sự cố"
severity:
  LOW: "Thấp"
  MEDIUM: "Trung bình"
  HIGH: "Cao"
  CRITICAL: "Nghiêm trọng"
category:
  TRAFFIC: "Lưu lượng"
  ...
```

`pyyaml` is already a dependency; `jinja2` is added. The Dockerfile copies `app/` wholesale, so the templates ship with the image.

## 2. Per-channel delivery

- **Email:** `EmailClient.send` takes an optional `html`. When present it sends `multipart/alternative` — `set_content(text)` first, then `add_alternative(html, subtype="html")`, in that order, so a client that can't render HTML still shows the text part. The subject comes from `i18n.yml` per kind, replacing the hardcoded string.
- **Telegram:** the rendered `.txt`.
- **Base.vn:** the rendered `.txt`, still passed through `NotificationRules.render_base_content(message_template, text)`, so the per-channel "message template" field in the UI keeps its current meaning.

## 3. Call sites and testing

Both webhooks build a `NotificationEvent` instead of passing `title`. The per-channel `try/except` and the `sent`/`failed` audit entry around each dispatch are unchanged, so a broken channel still cannot block incident creation. `TestSendNotificationChannel` builds a `TEST` event, keeping its optional custom message as the title.

Tests:
- `NotificationTemplates` renders every kind for both formats, leaves no placeholder unfilled, and `i18n.yml` has a key for every `NotificationKind` and every severity.
- `EmailClient` sends two MIME parts in the right order, and stays single-part when `html` is omitted.
- `DispatchNotification` sends the HTML to email and the text to Telegram and Base.vn.
- The observability fakes take an event; the existing assertions on the dispatched title move to `event.title`.

## Out of scope

- Notifications on acknowledge, resolve, or drift reconciliation.
- A second language, or per-channel language selection.
- A deep link to one incident: the frontend has no incident detail route, so the link points at `/admin/incidents`.
- Any change to the notification channel schema or its UI.
