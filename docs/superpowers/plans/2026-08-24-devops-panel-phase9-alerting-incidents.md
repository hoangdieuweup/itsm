# DevOps Panel Phase 9 — Alerting + Incidents

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user define alert rules per environment (Cloudflare-native Notification Policies, or Loki/LogQL rules evaluated by Loki's own Ruler), pick which Phase 8 notification channels fire when a rule triggers, and manage the resulting incidents (OPEN → ACKNOWLEDGED → RESOLVED) in a dashboard. Two new inbound webhooks turn real external alert traffic into `incidents` rows and fan out notifications.

**Architecture:** All backend code extends the **existing** `app/modules/observability/` module — no new backend module (confirmed by the schema doc's own module-assignment line). New facade methods on `app/modules/cloudflare/public.py` (get a ready client + decrypted token for an environment; ensure a webhook destination exists) and `app/modules/notifications/public.py` (dispatch a message through a channel — extracted from a private method). 7 new `CloudflareClient` methods, 1 new `LokiClient` method. Two new webhook routes use a brand-new "shared secret, no session" auth dependency — genuinely new ground, no precedent in this codebase. Frontend gets 3 new pieces: `entities/incident/` (promoted — Phase 10 is a known second consumer), `modules/alerting/`, `modules/incidents/`.

**Tech Stack:** No new backend dependencies. `hmac.compare_digest` (stdlib) for constant-time webhook-secret comparison.

**Spec:** The "Phase 9 — Detailed Plan: Alerting + Incidents" section of `/Users/hoangdieu/.claude/plans/rosy-juggling-pine.md` (12 numbered Decisions — read in full, source of truth). Also `docs/tasks/devops-control-panel-schema.md` (verbatim `alert_rules`/`alert_rule_channels`/`incidents` ERD), `docs/tasks/cloudflare-api-reference.md` §4 (Notifications/Alerting), `docs/tasks/grafana-loki-integration.md` §3 (Ruler). The inbound Cloudflare webhook payload shape was independently verified live against `developers.cloudflare.com/notifications/reference/webhook-payload-schema/` — not merely trusted from local docs.

## Global Constraints

- `alert_rules.source` is 2-valued (`CLOUDFLARE_NATIVE | LOKI_QUERY`); `incidents.source` is 3-valued (`CLOUDFLARE | LOKI | MANUAL`) — never conflate them (Decision #2).
- `alert_rules` gets a `name varchar(255) not null` column beyond the literal ERD — no other column is safe to derive a display label from (Decision #1).
- Incident transitions: only `{(OPEN,ACKNOWLEDGED), (OPEN,RESOLVED), (ACKNOWLEDGED,RESOLVED)}` are legal; anything else raises `InvalidIncidentTransition` (Decision #3).
- The Cloudflare webhook receiver resolves incidents via `cf_policy_id` (confirmed always-present in Cloudflare's real payload), never auto-resolves on `ALERT_STATE_EVENT_END`, and dedupes by `alert_correlation_id` (new `incidents` column) against any non-RESOLVED incident (Decision #4).
- Webhook destination secret/id live on `cloudflare_accounts` (2 new nullable columns), owned by `cloudflare`, keyed by the URL path segment `{cloudflare_account_id}` (Decision #5).
- Incident severity always comes from `alert_rules.severity`, never parsed from the external payload — verified against 6 real Cloudflare example payloads, none of which carry a common severity field (Decision #6).
- Notification fan-out reuses Phase 8 via an extracted `DispatchNotification` use case + a new `NotificationsApi.dispatch` facade method; a failed dispatch is logged, never allowed to roll back incident creation (Decision #7).
- `cloudflare/public.py` gets `get_ready_client_for_environment` + `ensure_webhook_destination`; `.importlinter`'s `cloudflare-facade` and `notifications-facade` contracts both get `app.modules.observability` added to `source_modules` (Decisions #7/#8).
- `CreateAlertRule` (CLOUDFLARE_NATIVE) sequence: resolve environment → ready client → ensure webhook destination → `create_policy` → persist with `cf_policy_id` → commit → audit. Nothing persists if the Cloudflare call fails (Decision #9).
- `CreateAlertRule` (LOKI_QUERY) additionally calls `LokiClient.upsert_rule_group` (namespace `"itsm"`, group `alert-rule-{id}`, rule labeled `app_alert_rule_id` for the webhook join) — a LOKI_QUERY row with no matching Ruler rule would never fire (Decision #10).
- `/webhooks/loki-alert` parses the standard Prometheus Alertmanager webhook body, bearer-token auth, only processes `alerts[].status == "firing"`, dedupes by Alertmanager's own `fingerprint` (Decision #11).
- RBAC: brand-new `alert_rule:{create,read,update,delete}` + `incident:{create,read,acknowledge,resolve}` (no update/delete on incidents — append-only business record), new `RbacActions.ACKNOWLEDGE`/`.RESOLVE` on both backend and frontend (Decision #12).
- Router thinness and class-scoped constants apply throughout, as every prior phase.

---

## Task 1: `observability` module scaffold — constants, models, schemas, exceptions, rules

**Files:**
- Modify: `backend/app/modules/observability/constants.py`, `models.py`, `schemas.py`, `exceptions.py`, `rules.py`
- Modify: `backend/app/modules/cloudflare/models.py` (2 new columns on `CloudflareAccount`)
- Test: `backend/tests/observability/test_models.py`, `backend/tests/observability/test_rules.py`

**Interfaces:**
- Produces: `AlertRuleSource`, `IncidentSource`, `IncidentCategory`, `AlertSeverity`, `IncidentStatus` (all `StrEnum`); `AlertRule`, `AlertRuleChannel`, `Incident` (ORM models); `AlertRuleRead`/`Create`/`Update`, `AvailableAlertOption`, `IncidentRead`, `CreateManualIncidentRequest` (Pydantic schemas); `AlertRuleNotFound`, `InvalidIncidentTransition`, `InvalidWebhookSecret`, `CloudflarePolicyNotFound` (exceptions); `IncidentRules.validate_transition(current, target) -> None`, `AlertingRules.category_for_cloudflare_alert_type(alert_type: str) -> IncidentCategory`.
- Consumes: `app.core.exceptions.{NotFoundError, ForbiddenError, ValidationFailedError}`, `app.core.models.{FrozenModel, CustomModel}`, `app.core.base.markers.rule`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/observability/test_rules.py
import pytest

from app.modules.observability.constants import IncidentCategory, IncidentStatus
from app.modules.observability.exceptions import InvalidIncidentTransition
from app.modules.observability.rules import AlertingRules, IncidentRules


class TestValidateTransition:
    @pytest.mark.parametrize(
        "current,target",
        [
            (IncidentStatus.OPEN, IncidentStatus.ACKNOWLEDGED),
            (IncidentStatus.OPEN, IncidentStatus.RESOLVED),
            (IncidentStatus.ACKNOWLEDGED, IncidentStatus.RESOLVED),
        ],
    )
    def test_allowed_transitions_pass(self, current, target) -> None:
        IncidentRules.validate_transition(current, target)  # no raise

    @pytest.mark.parametrize(
        "current,target",
        [
            (IncidentStatus.RESOLVED, IncidentStatus.OPEN),
            (IncidentStatus.RESOLVED, IncidentStatus.ACKNOWLEDGED),
            (IncidentStatus.ACKNOWLEDGED, IncidentStatus.OPEN),
            (IncidentStatus.OPEN, IncidentStatus.OPEN),
            (IncidentStatus.RESOLVED, IncidentStatus.RESOLVED),
        ],
    )
    def test_disallowed_transitions_raise(self, current, target) -> None:
        with pytest.raises(InvalidIncidentTransition):
            IncidentRules.validate_transition(current, target)


class TestCategoryForCloudflareAlertType:
    def test_ddos_l4(self) -> None:
        assert AlertingRules.category_for_cloudflare_alert_type(
            "advanced_ddos_attack_l4_alert"
        ) == IncidentCategory.DDOS

    def test_ddos_l7(self) -> None:
        assert AlertingRules.category_for_cloudflare_alert_type(
            "advanced_ddos_attack_l7_alert"
        ) == IncidentCategory.DDOS

    def test_health_check(self) -> None:
        assert AlertingRules.category_for_cloudflare_alert_type(
            "health_check_status_notification"
        ) == IncidentCategory.ORIGIN_ERROR

    def test_unmapped_falls_back_to_traffic(self) -> None:
        assert AlertingRules.category_for_cloudflare_alert_type(
            "dedicated_ssl_certificate_event_type"
        ) == IncidentCategory.TRAFFIC
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && uv run pytest tests/observability/test_rules.py -v`
Expected: `ModuleNotFoundError`/`ImportError` — `AlertingRules`/`IncidentRules`/`InvalidIncidentTransition` don't exist yet.

- [ ] **Step 3: Implement constants, models, exceptions, rules**

```python
# backend/app/modules/observability/constants.py — append to the existing file
class AlertRuleSource(StrEnum):
    CLOUDFLARE_NATIVE = "CLOUDFLARE_NATIVE"
    LOKI_QUERY = "LOKI_QUERY"


class IncidentSource(StrEnum):
    CLOUDFLARE = "CLOUDFLARE"
    LOKI = "LOKI"
    MANUAL = "MANUAL"


class IncidentCategory(StrEnum):
    TRAFFIC = "TRAFFIC"
    DDOS = "DDOS"
    ORIGIN_ERROR = "ORIGIN_ERROR"
    DNS_DRIFT = "DNS_DRIFT"
    TUNNEL_DRIFT = "TUNNEL_DRIFT"
    LOG_MATCH = "LOG_MATCH"
    MANUAL = "MANUAL"


class AlertSeverity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class IncidentStatus(StrEnum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"


# extend ErrorCode (existing class) with:
    ALERT_RULE_NOT_FOUND = "alert_rule_not_found"
    INCIDENT_NOT_FOUND = "incident_not_found"
    INVALID_INCIDENT_TRANSITION = "invalid_incident_transition"
    INVALID_WEBHOOK_SECRET = "invalid_webhook_secret"


class AlertingLimits:
    MAX_NAME_LENGTH = 255
    MAX_TITLE_LENGTH = 255
    MAX_CF_ALERT_TYPE_LENGTH = 100
    MAX_CF_POLICY_ID_LENGTH = 64
    MAX_LOG_REF_ID_LENGTH = 64
    MAX_CORRELATION_ID_LENGTH = 64


class AlertingAuditActions(StrEnum):
    ALERT_RULE_CREATED = "ALERT_RULE_CREATED"
    ALERT_RULE_UPDATED = "ALERT_RULE_UPDATED"
    ALERT_RULE_DELETED = "ALERT_RULE_DELETED"
    INCIDENT_DETECTED = "INCIDENT_DETECTED"
    INCIDENT_CREATED_MANUALLY = "INCIDENT_CREATED_MANUALLY"
    INCIDENT_ACKNOWLEDGED = "INCIDENT_ACKNOWLEDGED"
    INCIDENT_RESOLVED = "INCIDENT_RESOLVED"
    INCIDENT_NOTIFICATION_SENT = "INCIDENT_NOTIFICATION_SENT"
```

```python
# backend/app/modules/observability/models.py — append to the existing file
import uuid
from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from app.modules.observability.constants import (
    AlertingLimits, AlertRuleSource, AlertSeverity, IncidentCategory, IncidentSource, IncidentStatus,
)


class AlertRule(Base):
    __tablename__ = "alert_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    environment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("environments.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(AlertingLimits.MAX_NAME_LENGTH))
    source: Mapped[AlertRuleSource] = mapped_column(Enum(AlertRuleSource, native_enum=False))
    cf_alert_type: Mapped[str | None] = mapped_column(
        String(AlertingLimits.MAX_CF_ALERT_TYPE_LENGTH), nullable=True
    )
    cf_policy_id: Mapped[str | None] = mapped_column(
        String(AlertingLimits.MAX_CF_POLICY_ID_LENGTH), nullable=True, index=True
    )
    condition: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    severity: Mapped[AlertSeverity] = mapped_column(Enum(AlertSeverity, native_enum=False))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AlertRuleChannel(Base):
    __tablename__ = "alert_rule_channels"

    alert_rule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("alert_rules.id", ondelete="CASCADE"), primary_key=True
    )
    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("notification_channels.id", ondelete="CASCADE"), primary_key=True
    )


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="RESTRICT"), index=True
    )
    environment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("environments.id", ondelete="RESTRICT"), index=True
    )
    alert_rule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("alert_rules.id", ondelete="SET NULL"), nullable=True
    )
    source: Mapped[IncidentSource] = mapped_column(Enum(IncidentSource, native_enum=False))
    category: Mapped[IncidentCategory] = mapped_column(Enum(IncidentCategory, native_enum=False))
    severity: Mapped[AlertSeverity] = mapped_column(Enum(AlertSeverity, native_enum=False))
    status: Mapped[IncidentStatus] = mapped_column(
        Enum(IncidentStatus, native_enum=False), default=IncidentStatus.OPEN
    )
    title: Mapped[str] = mapped_column(String(AlertingLimits.MAX_TITLE_LENGTH))
    log_ref_id: Mapped[str | None] = mapped_column(String(AlertingLimits.MAX_LOG_REF_ID_LENGTH), nullable=True)
    alert_correlation_id: Mapped[str | None] = mapped_column(
        String(AlertingLimits.MAX_CORRELATION_ID_LENGTH), nullable=True, index=True
    )
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
```

```python
# backend/app/modules/cloudflare/models.py — add to CloudflareAccount, after api_token
    cf_webhook_destination_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    webhook_secret_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
```

```python
# backend/app/modules/observability/schemas.py — append to the existing file
class AvailableAlertOption(FrozenModel):
    alert_type: str
    display_name: str


class AlertRuleRead(FrozenModel):
    id: UUID
    environment_id: UUID
    name: str
    source: AlertRuleSource
    cf_alert_type: str | None
    cf_policy_id: str | None
    condition: dict | None
    severity: AlertSeverity
    is_active: bool
    channel_ids: list[UUID]
    created_at: datetime
    updated_at: datetime


class AlertRuleCreate(CustomModel):
    name: str = Field(max_length=AlertingLimits.MAX_NAME_LENGTH)
    source: AlertRuleSource
    cf_alert_type: str | None = None
    condition: dict | None = None
    severity: AlertSeverity
    channel_ids: list[UUID] = Field(default_factory=list)


class AlertRuleUpdate(CustomModel):
    name: str | None = Field(default=None, max_length=AlertingLimits.MAX_NAME_LENGTH)
    is_active: bool | None = None
    severity: AlertSeverity | None = None
    channel_ids: list[UUID] | None = None


class IncidentRead(FrozenModel):
    id: UUID
    project_id: UUID
    environment_id: UUID
    alert_rule_id: UUID | None
    source: IncidentSource
    category: IncidentCategory
    severity: AlertSeverity
    status: IncidentStatus
    title: str
    log_ref_id: str | None
    detected_at: datetime
    acknowledged_at: datetime | None
    acknowledged_by: UUID | None
    resolved_at: datetime | None
    resolved_by: UUID | None
    created_at: datetime
    updated_at: datetime


class CreateManualIncidentRequest(CustomModel):
    environment_id: UUID
    category: IncidentCategory
    severity: AlertSeverity
    title: str = Field(max_length=AlertingLimits.MAX_TITLE_LENGTH)
```

```python
# backend/app/modules/observability/exceptions.py — append to the existing file
class AlertRuleNotFound(NotFoundError):
    code = ErrorCode.ALERT_RULE_NOT_FOUND
    message = "Alert rule not found"


class IncidentNotFound(NotFoundError):
    code = ErrorCode.INCIDENT_NOT_FOUND
    message = "Incident not found"


class InvalidIncidentTransition(ValidationFailedError):
    code = ErrorCode.INVALID_INCIDENT_TRANSITION
    message = "This status change is not allowed from the incident's current state"


class InvalidWebhookSecret(ForbiddenError):
    """The one 401 in this codebase outside auth/ — mirrors auth/exceptions.py's
    NotAuthenticated, the only existing precedent for overriding status_code."""

    code = ErrorCode.INVALID_WEBHOOK_SECRET
    message = "Invalid webhook secret"
    status_code = 401


class CloudflarePolicyNotFound(Exception):
    """Internal control-flow signal only — never raised past the webhook
    receiver's own try/except; a webhook whose policy_id matches nothing
    logs a warning and returns 200, it never surfaces this as an HTTP error
    to Cloudflare (Decision #4)."""
```

```python
# backend/app/modules/observability/rules.py (new file)
from app.core.base.markers import rule
from app.modules.observability.constants import IncidentCategory, IncidentStatus
from app.modules.observability.exceptions import InvalidIncidentTransition

_ALLOWED_TRANSITIONS = {
    (IncidentStatus.OPEN, IncidentStatus.ACKNOWLEDGED),
    (IncidentStatus.OPEN, IncidentStatus.RESOLVED),
    (IncidentStatus.ACKNOWLEDGED, IncidentStatus.RESOLVED),
}

_CLOUDFLARE_ALERT_TYPE_CATEGORY = {
    "advanced_ddos_attack_l4_alert": IncidentCategory.DDOS,
    "advanced_ddos_attack_l7_alert": IncidentCategory.DDOS,
    "health_check_status_notification": IncidentCategory.ORIGIN_ERROR,
}


class IncidentRules:
    @staticmethod
    @rule
    def validate_transition(current: IncidentStatus, target: IncidentStatus) -> None:
        if (current, target) not in _ALLOWED_TRANSITIONS:
            raise InvalidIncidentTransition()


class AlertingRules:
    @staticmethod
    @rule
    def category_for_cloudflare_alert_type(alert_type: str) -> IncidentCategory:
        """Falls back to TRAFFIC for anything not explicitly mapped (SSL/Access
        cert expiry, Workers alerts, and any future alert_type Cloudflare adds) —
        the closest generic fit; DNS_DRIFT/TUNNEL_DRIFT are Phase 10's territory
        and are never set here."""
        return _CLOUDFLARE_ALERT_TYPE_CATEGORY.get(alert_type, IncidentCategory.TRAFFIC)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && uv run pytest tests/observability/test_rules.py -v`
Expected: PASS, all 8 tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/observability/{constants,models,schemas,exceptions,rules}.py backend/app/modules/cloudflare/models.py backend/tests/observability/test_rules.py
git commit -m "feat(observability): add alert-rule/incident constants, models, schemas, exceptions, rules"
```

---

## Task 2: Alembic migration

**Files:**
- Create: `backend/alembic/versions/<new_hash>_create_alerting_incidents_schema.py`

**Interfaces:**
- Consumes: current alembic head `7e2d9a4c8b1f` (confirmed — nothing declares it as a `down_revision`).
- Produces: `alert_rules`, `alert_rule_channels`, `incidents` tables; 2 new nullable columns on `cloudflare_accounts`.

- [ ] **Step 1: Write the migration**

```python
"""create alerting/incidents schema

Revision ID: <generate via `uv run alembic revision --rev-id` or let alembic assign one>
Revises: 7e2d9a4c8b1f
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "<new_hash>"
down_revision = "7e2d9a4c8b1f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cloudflare_accounts", sa.Column("cf_webhook_destination_id", sa.String(64), nullable=True))
    op.add_column("cloudflare_accounts", sa.Column("webhook_secret_ciphertext", sa.Text(), nullable=True))

    op.create_table(
        "alert_rules",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("environment_id", UUID(as_uuid=True), sa.ForeignKey("environments.id", ondelete="CASCADE"), index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("source", sa.Enum("CLOUDFLARE_NATIVE", "LOKI_QUERY", name="alert_rule_source", native_enum=False), nullable=False),
        sa.Column("cf_alert_type", sa.String(100), nullable=True),
        sa.Column("cf_policy_id", sa.String(64), nullable=True, index=True),
        sa.Column("condition", JSONB(), nullable=True),
        sa.Column("severity", sa.Enum("LOW", "MEDIUM", "HIGH", "CRITICAL", name="alert_severity", native_enum=False), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "alert_rule_channels",
        sa.Column("alert_rule_id", UUID(as_uuid=True), sa.ForeignKey("alert_rules.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("channel_id", UUID(as_uuid=True), sa.ForeignKey("notification_channels.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_table(
        "incidents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="RESTRICT"), index=True),
        sa.Column("environment_id", UUID(as_uuid=True), sa.ForeignKey("environments.id", ondelete="RESTRICT"), index=True),
        sa.Column("alert_rule_id", UUID(as_uuid=True), sa.ForeignKey("alert_rules.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source", sa.Enum("CLOUDFLARE", "LOKI", "MANUAL", name="incident_source", native_enum=False), nullable=False),
        sa.Column("category", sa.Enum("TRAFFIC", "DDOS", "ORIGIN_ERROR", "DNS_DRIFT", "TUNNEL_DRIFT", "LOG_MATCH", "MANUAL", name="incident_category", native_enum=False), nullable=False),
        sa.Column("severity", sa.Enum("LOW", "MEDIUM", "HIGH", "CRITICAL", name="alert_severity", native_enum=False), nullable=False),
        sa.Column("status", sa.Enum("OPEN", "ACKNOWLEDGED", "RESOLVED", name="incident_status", native_enum=False), nullable=False, server_default="OPEN"),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("log_ref_id", sa.String(64), nullable=True),
        sa.Column("alert_correlation_id", sa.String(64), nullable=True, index=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("incidents")
    op.drop_table("alert_rule_channels")
    op.drop_table("alert_rules")
    op.drop_column("cloudflare_accounts", "webhook_secret_ciphertext")
    op.drop_column("cloudflare_accounts", "cf_webhook_destination_id")
```

Note: reuse `alert_severity` enum name across both `alert_rules.severity` and `incidents.severity` — same value set, one Postgres enum type (even with `native_enum=False` this keeps the migration internally consistent; confirm the exact enum-naming convention already in use for shared enums by checking an earlier migration, e.g. `ManagedBy` reused across `dns_records`/`tunnel_public_hostnames`, before finalizing).

- [ ] **Step 2: Apply and verify**

Run: `cd backend && uv run alembic upgrade head` (against `itsm_test`, never `business-chatbot-postgres`)
Expected: succeeds, no errors. Then `uv run alembic downgrade -1 && uv run alembic upgrade head` to confirm reversibility.

- [ ] **Step 3: Commit**

```bash
git add backend/alembic/versions/
git commit -m "feat(observability): add alerting/incidents migration"
```

---

## Task 3: `CloudflareClient` — 6 new alerting methods

**Files:**
- Modify: `backend/app/integrations/cloudflare/client.py`
- Test: `backend/tests/integrations/cloudflare/test_client.py`

**Interfaces:**
- Produces: `CloudflareClient.list_available_alerts`, `.create_webhook_destination`, `.create_policy`, `.update_policy`, `.delete_policy`, `.test_policy`.
- Consumes: the existing `_write` helper (envelope-checked authenticated call), `CloudflareApiUnavailable`, `CloudflareDnsOperationRejected`, `InvalidCloudflareToken`.

- [ ] **Step 1: Write the failing tests** (one class per method, mirroring the existing `TestCreateDnsRecord`-style shape — success + rejected + unavailable per method; abbreviated here to the two riskiest, `create_webhook_destination` and `create_policy` — the remaining 4 follow the identical fake-transport pattern already used for every other `_write`-based method in this file)

```python
# backend/tests/integrations/cloudflare/test_client.py — append
import httpx
import pytest

from app.integrations.cloudflare.client import CloudflareClient
from app.integrations.cloudflare.exceptions import CloudflareApiUnavailable, CloudflareDnsOperationRejected


def _transport(handler):
    return httpx.MockTransport(handler)


class TestCreateWebhookDestination:
    async def test_success_returns_id_and_echoes_secret(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/accounts/acc1/alerting/v3/destinations/webhooks"
            body = request.read()
            import json
            payload = json.loads(body)
            assert payload == {"name": "itsm-webhook", "url": "https://x/webhooks/cloudflare-alert/acc1", "secret": "s3cr3t"}
            return httpx.Response(200, json={"success": True, "result": {"id": "wh-123"}})

        client = CloudflareClient(transport=_transport(handler))
        webhook_id = await client.create_webhook_destination(
            cf_account_id="acc1", api_token="tok", name="itsm-webhook",
            url="https://x/webhooks/cloudflare-alert/acc1", secret="s3cr3t",
        )
        assert webhook_id == "wh-123"

    async def test_rejected_raises(self) -> None:
        client = CloudflareClient(transport=_transport(lambda r: httpx.Response(400, json={"success": False, "errors": []})))
        with pytest.raises(CloudflareDnsOperationRejected):
            await client.create_webhook_destination(cf_account_id="acc1", api_token="tok", name="n", url="u", secret="s")

    async def test_unavailable_raises(self) -> None:
        client = CloudflareClient(transport=_transport(lambda r: httpx.Response(503)))
        with pytest.raises(CloudflareApiUnavailable):
            await client.create_webhook_destination(cf_account_id="acc1", api_token="tok", name="n", url="u", secret="s")


class TestCreatePolicy:
    async def test_success_returns_policy_id(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/accounts/acc1/alerting/v3/policies"
            return httpx.Response(200, json={"success": True, "result": {"id": "policy-789"}})

        client = CloudflareClient(transport=_transport(handler))
        policy_id = await client.create_policy(
            cf_account_id="acc1", api_token="tok", name="My rule", alert_type="health_check_status_notification",
            webhook_destination_id="wh-123",
        )
        assert policy_id == "policy-789"

    async def test_rejected_raises(self) -> None:
        client = CloudflareClient(transport=_transport(lambda r: httpx.Response(422, json={"success": False, "errors": []})))
        with pytest.raises(CloudflareDnsOperationRejected):
            await client.create_policy(cf_account_id="acc1", api_token="tok", name="n", alert_type="t", webhook_destination_id="w")
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && uv run pytest tests/integrations/cloudflare/test_client.py -v -k "WebhookDestination or CreatePolicy"`
Expected: `AttributeError: 'CloudflareClient' object has no attribute 'create_webhook_destination'`.

- [ ] **Step 3: Implement**

```python
# backend/app/integrations/cloudflare/client.py — append to CloudflareClient
    @integration
    async def list_available_alerts(self, *, cf_account_id: str, api_token: str) -> list[dict]:
        """GET /accounts/{cf_account_id}/alerting/v3/available_alerts. Returns
        the raw result list — the service layer shapes it into AvailableAlertOption."""
        body = await self._write(f"/accounts/{cf_account_id}/alerting/v3/available_alerts", "GET", api_token)
        return body.get("result", [])

    @integration
    async def create_webhook_destination(
        self, *, cf_account_id: str, api_token: str, name: str, url: str, secret: str
    ) -> str:
        """POST /accounts/{cf_account_id}/alerting/v3/destinations/webhooks.
        Returns the real webhook destination id — Cloudflare will call `url`
        with `cf-webhook-auth: <secret>` on every future notification."""
        body = await self._write(
            f"/accounts/{cf_account_id}/alerting/v3/destinations/webhooks",
            "POST",
            api_token,
            json={"name": name, "url": url, "secret": secret},
        )
        return body["result"]["id"]

    @integration
    async def create_policy(
        self, *, cf_account_id: str, api_token: str, name: str, alert_type: str, webhook_destination_id: str
    ) -> str:
        """POST /accounts/{cf_account_id}/alerting/v3/policies. mechanisms.webhooks
        points at the already-registered destination id. Returns the real
        policy_id — persisted as alert_rules.cf_policy_id for 2-way sync."""
        body = await self._write(
            f"/accounts/{cf_account_id}/alerting/v3/policies",
            "POST",
            api_token,
            json={
                "name": name,
                "alert_type": alert_type,
                "enabled": True,
                "mechanisms": {"webhooks": [{"id": webhook_destination_id}]},
            },
        )
        return body["result"]["id"]

    @integration
    async def update_policy(
        self, *, cf_account_id: str, api_token: str, policy_id: str, name: str | None, enabled: bool | None
    ) -> None:
        """PUT /accounts/{cf_account_id}/alerting/v3/policies/{policy_id}."""
        payload: dict = {}
        if name is not None:
            payload["name"] = name
        if enabled is not None:
            payload["enabled"] = enabled
        await self._write(
            f"/accounts/{cf_account_id}/alerting/v3/policies/{policy_id}", "PUT", api_token, json=payload
        )

    @integration
    async def delete_policy(self, *, cf_account_id: str, api_token: str, policy_id: str) -> None:
        """DELETE /accounts/{cf_account_id}/alerting/v3/policies/{policy_id}."""
        await self._write(f"/accounts/{cf_account_id}/alerting/v3/policies/{policy_id}", "DELETE", api_token)

    @integration
    async def test_policy(self, *, cf_account_id: str, api_token: str, policy_id: str) -> None:
        """POST .../policies/{policy_id}/test — sends a synthetic INFO-severity
        alert through the policy's configured mechanisms, no DB side effect
        here; the resulting webhook call is handled identically to a real one."""
        await self._write(f"/accounts/{cf_account_id}/alerting/v3/policies/{policy_id}/test", "POST", api_token)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && uv run pytest tests/integrations/cloudflare/test_client.py -v`
Expected: PASS, including all pre-existing tests in this file (no regressions).

- [ ] **Step 5: Add the remaining success/rejected/unavailable test triples for `list_available_alerts`, `update_policy`, `delete_policy`, `test_policy`** — same fake-transport pattern as Step 1's two examples and every pre-existing method in this file. Run again, confirm all green.

- [ ] **Step 6: Commit**

```bash
git add backend/app/integrations/cloudflare/client.py backend/tests/integrations/cloudflare/test_client.py
git commit -m "feat(cloudflare): add available_alerts, webhook destination, and policy client methods"
```

---

## Task 4: `LokiClient.upsert_rule_group`

**Files:**
- Modify: `backend/app/integrations/loki/client.py`
- Test: `backend/tests/integrations/loki/test_client.py`

**Interfaces:**
- Produces: `LokiClient.upsert_rule_group(*, endpoint_url: str, namespace: str, group_name: str, rule_name: str, expr: str, for_duration: str, labels: dict[str, str], auth_header: str | None) -> None`.

Before implementing, ground the Loki Ruler request body against Loki's real documentation (Risk flagged explicitly in the Detailed Plan — the local spec doc only lists the endpoint, not the body shape). Loki's Ruler `POST /loki/api/v1/rules/{namespace}` accepts a YAML (or JSON-as-YAML, `Content-Type: application/yaml`) body of shape:
```yaml
name: <group_name>
rules:
  - alert: <rule_name>
    expr: <LogQL expr>
    for: <duration, e.g. "5m">
    labels: {app_alert_rule_id: "<uuid>"}
    annotations: {summary: "..."}
```

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/integrations/loki/test_client.py — append
import httpx
import pytest
import yaml

from app.integrations.loki.client import LokiClient
from app.integrations.loki.exceptions import LokiApiUnavailable, LokiQueryRejected


class TestUpsertRuleGroup:
    async def test_success_posts_yaml_rule_group(self) -> None:
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/loki/api/v1/rules/itsm"
            captured["body"] = yaml.safe_load(request.read())
            return httpx.Response(202)

        client = LokiClient(transport=httpx.MockTransport(handler))
        await client.upsert_rule_group(
            endpoint_url="http://loki:3100", namespace="itsm", group_name="alert-rule-abc",
            rule_name="alert-rule-abc", expr='{app="x"} |= "error"', for_duration="5m",
            labels={"app_alert_rule_id": "abc"}, auth_header=None,
        )
        assert captured["body"]["name"] == "alert-rule-abc"
        assert captured["body"]["rules"][0]["expr"] == '{app="x"} |= "error"'
        assert captured["body"]["rules"][0]["labels"] == {"app_alert_rule_id": "abc"}

    async def test_rejected_raises(self) -> None:
        client = LokiClient(transport=httpx.MockTransport(lambda r: httpx.Response(400, text="bad LogQL")))
        with pytest.raises(LokiQueryRejected):
            await client.upsert_rule_group(
                endpoint_url="http://loki:3100", namespace="itsm", group_name="g", rule_name="r",
                expr="{{bad", for_duration="5m", labels={}, auth_header=None,
            )

    async def test_unavailable_raises(self) -> None:
        client = LokiClient(transport=httpx.MockTransport(lambda r: httpx.Response(503)))
        with pytest.raises(LokiApiUnavailable):
            await client.upsert_rule_group(
                endpoint_url="http://loki:3100", namespace="itsm", group_name="g", rule_name="r",
                expr="{}", for_duration="5m", labels={}, auth_header=None,
            )
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && uv run pytest tests/integrations/loki/test_client.py -v -k UpsertRuleGroup`
Expected: `AttributeError`.

- [ ] **Step 3: Implement** (mirror `query_range`'s exact error-mapping shape — confirm the actual current 3-way mapping in `client.py` before writing this, since it must reuse the same exceptions, not invent new ones)

```python
# backend/app/integrations/loki/client.py — append to LokiClient; add `import yaml` (new dep — run
# `uv add pyyaml` first and confirm it's not already transitively available via another package)
    @integration
    async def upsert_rule_group(
        self, *, endpoint_url: str, namespace: str, group_name: str, rule_name: str, expr: str,
        for_duration: str, labels: dict[str, str], auth_header: str | None,
    ) -> None:
        """POST {endpoint_url}/loki/api/v1/rules/{namespace}, Content-Type:
        application/yaml. One rule per group — group_name and rule_name both
        derive from alert_rule.id (Decision #10), labels carry
        app_alert_rule_id so Alertmanager's webhook payload can join back to
        this alert_rules row."""
        body = yaml.safe_dump({
            "name": group_name,
            "rules": [{"alert": rule_name, "expr": expr, "for": for_duration, "labels": labels}],
        })
        headers = {"Content-Type": "application/yaml"}
        if auth_header:
            headers["Authorization"] = auth_header
        try:
            async with httpx.AsyncClient(transport=self._transport) as client:
                response = await client.post(
                    f"{endpoint_url}/loki/api/v1/rules/{namespace}",
                    content=body, headers=headers, timeout=loki_settings.HTTP_TIMEOUT_SECONDS,
                )
        except httpx.HTTPError as exc:
            raise LokiApiUnavailable() from exc
        if response.status_code in (401, 403):
            raise InvalidLokiCredential()
        if response.is_error:
            raise LokiQueryRejected(response.text)
```

(Reconcile the exact exception names/constructor signature — `LokiQueryRejected(message)` vs a keyword — against the real current `query_range` implementation before finalizing; this sketch assumes the same 3-way shape documented in Phase 6's own plan section.)

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && uv run pytest tests/integrations/loki/test_client.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/integrations/loki/client.py backend/tests/integrations/loki/test_client.py backend/pyproject.toml backend/uv.lock
git commit -m "feat(loki): add upsert_rule_group for Ruler-backed LOKI_QUERY alert rules"
```

---

## Task 5: `cloudflare` facade — `ReadyCloudflareClient`, `get_ready_client_for_environment`, `ensure_webhook_destination`, `get_webhook_secret`

**Files:**
- Modify: `backend/app/modules/cloudflare/public.py`, `repository.py`
- Modify: `backend/.importlinter` (add `app.modules.observability` to `cloudflare-facade`'s `source_modules`)
- Test: `backend/tests/cloudflare/test_public.py` (new)

**Interfaces:**
- Produces: `ReadyCloudflareClient` (frozen dataclass: `client: CloudflareClient`, `cf_account_id: str`, `api_token: str`, `cloudflare_account_id: UUID`), `CloudflareApi.get_ready_client_for_environment(environment_id) -> ReadyCloudflareClient | None`, `CloudflareApi.ensure_webhook_destination(cloudflare_account_id: UUID, *, webhook_url: str) -> str` (returns the **destination id**, registering it on first call — consumed by `CreateAlertRule` in Task 10), `CloudflareApi.get_webhook_secret(cloudflare_account_id: UUID) -> str | None` (read-only, returns the **decrypted secret** or `None` if never registered — consumed by `verify_cloudflare_webhook_secret` in Task 9). Destination id and secret are deliberately two separate facade methods returning two different values — conflating them into one polymorphic return was the original draft's mistake, caught during this plan's own self-review.
- Consumes: `AbstractCloudflareUnitOfWork.{configs,accounts}`, `FernetCodec`, `cloudflare_settings.FERNET_KEY`, `CloudflareClient.create_webhook_destination`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/cloudflare/test_public.py (new)
from uuid import uuid4

import pytest

from app.core.crypto import FernetCodec
from app.modules.cloudflare.config import cloudflare_settings
from app.modules.cloudflare.public import CloudflareApi

TEST_KEY = "kL8Zx3vQ9mN2pR7wT4yU6bC1dF5gH0jK3lM6nO9pQ2s="


@pytest.fixture(autouse=True)
def _fernet_key(monkeypatch) -> None:
    monkeypatch.setattr(cloudflare_settings, "FERNET_KEY", TEST_KEY)


class FakeAccountsRepo:
    def __init__(self, accounts=None, token_ciphertexts=None) -> None:
        self._accounts = accounts or {}
        self._tokens = token_ciphertexts or {}
        self.webhook_writes = []

    async def get_by_id(self, account_id):
        return self._accounts.get(account_id)

    async def get_token_ciphertext(self, account_id):
        return self._tokens.get(account_id)

    async def get_webhook_destination_ciphertext(self, account_id):
        row = self._accounts.get(account_id)
        return (row.cf_webhook_destination_id, self._tokens.get(f"webhook:{account_id}")) if row else (None, None)

    async def set_webhook_destination(self, account_id, *, cf_webhook_destination_id, secret_ciphertext):
        self.webhook_writes.append((account_id, cf_webhook_destination_id))


class FakeConfigsRepo:
    def __init__(self, configs=None) -> None:
        self._configs = configs or {}

    async def get_by_environment_id(self, environment_id):
        return self._configs.get(environment_id)


class FakeUow:
    def __init__(self, accounts: FakeAccountsRepo, configs: FakeConfigsRepo) -> None:
        self.accounts = accounts
        self.configs = configs

    async def commit(self):
        pass


class TestGetReadyClientForEnvironment:
    async def test_returns_none_when_unbound(self) -> None:
        api = CloudflareApi(FakeUow(FakeAccountsRepo(), FakeConfigsRepo()), client=object())
        assert await api.get_ready_client_for_environment(uuid4()) is None

    async def test_returns_ready_client_when_bound(self) -> None:
        env_id, account_id = uuid4(), uuid4()
        from types import SimpleNamespace

        account = SimpleNamespace(id=account_id, cf_account_id="cf-123", cf_webhook_destination_id=None)
        config = SimpleNamespace(cloudflare_account_id=account_id)
        ciphertext = FernetCodec.encrypt("real-token", key=TEST_KEY)
        api = CloudflareApi(
            FakeUow(FakeAccountsRepo({account_id: account}, {account_id: ciphertext}), FakeConfigsRepo({env_id: config})),
            client="the-client",
        )
        ready = await api.get_ready_client_for_environment(env_id)
        assert ready is not None
        assert ready.cf_account_id == "cf-123"
        assert ready.api_token == "real-token"
        assert ready.client == "the-client"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && uv run pytest tests/cloudflare/test_public.py -v`
Expected: `ImportError: cannot import name 'CloudflareApi'`.

- [ ] **Step 3: Implement**

```python
# backend/app/modules/cloudflare/repository.py — append to AbstractCloudflareAccountRepository + CloudflareAccountRepository
    @abstractmethod
    async def get_webhook_destination_ciphertext(self, account_id: UUID) -> tuple[str | None, str | None]:
        """Return (cf_webhook_destination_id, webhook_secret_ciphertext), both
        None if never registered."""
        raise NotImplementedError

    @abstractmethod
    async def set_webhook_destination(
        self, account_id: UUID, *, cf_webhook_destination_id: str, secret_ciphertext: str
    ) -> None:
        """Persist a newly-registered webhook destination."""
        raise NotImplementedError

# concrete implementation:
    @database
    async def get_webhook_destination_ciphertext(self, account_id: UUID) -> tuple[str | None, str | None]:
        row = await self._session.get(CloudflareAccount, account_id)
        if row is None:
            return None, None
        return row.cf_webhook_destination_id, row.webhook_secret_ciphertext

    @database
    async def set_webhook_destination(
        self, account_id: UUID, *, cf_webhook_destination_id: str, secret_ciphertext: str
    ) -> None:
        row = await self._session.get(CloudflareAccount, account_id)
        if row is None:
            raise ValueError(f"cloudflare account {account_id} does not exist")
        row.cf_webhook_destination_id = cf_webhook_destination_id
        row.webhook_secret_ciphertext = secret_ciphertext
        await self._session.flush()
```

```python
# backend/app/modules/cloudflare/public.py — add
from dataclasses import dataclass
import secrets
from app.core.crypto import FernetCodec
from app.integrations.cloudflare.client import CloudflareClient
from app.modules.cloudflare.config import cloudflare_settings

__all__ = [..., "ReadyCloudflareClient", "CloudflareApi", "get_cloudflare_api"]


@dataclass(frozen=True)
class ReadyCloudflareClient:
    client: CloudflareClient
    cf_account_id: str
    api_token: str
    cloudflare_account_id: UUID


class CloudflareApi:
    def __init__(self, uow: AbstractCloudflareUnitOfWork, client: CloudflareClient) -> None:
        self._uow = uow
        self._client = client

    @facade
    async def get_ready_client_for_environment(self, environment_id: UUID) -> ReadyCloudflareClient | None:
        config = await self._uow.configs.get_by_environment_id(environment_id)
        if config is None:
            return None
        account = await self._uow.accounts.get_by_id(config.cloudflare_account_id)
        ciphertext = await self._uow.accounts.get_token_ciphertext(config.cloudflare_account_id)
        if account is None or ciphertext is None:
            return None
        plaintext = FernetCodec.decrypt(ciphertext, key=cloudflare_settings.FERNET_KEY)
        return ReadyCloudflareClient(
            client=self._client, cf_account_id=account.cf_account_id, api_token=plaintext,
            cloudflare_account_id=account.id,
        )

    @facade
    async def ensure_webhook_destination(self, cloudflare_account_id: UUID, *, webhook_url: str) -> str:
        """Idempotent: returns the existing cf_webhook_destination_id if
        already registered, otherwise registers a new destination with a
        freshly generated secret, persists both (secret Fernet-encrypted),
        and returns the new destination id. Returns the DESTINATION ID, not
        the secret — CreateAlertRule (Task 10) needs the id immediately
        afterward for create_policy's mechanisms.webhooks; the secret is a
        separate, read-only concern (get_webhook_secret below), fetched only
        by the webhook-auth verification path (Task 9), never by the
        alert-rule creation path."""
        existing_id, _existing_ciphertext = await self._uow.accounts.get_webhook_destination_ciphertext(
            cloudflare_account_id
        )
        if existing_id:
            return existing_id

        account = await self._uow.accounts.get_by_id(cloudflare_account_id)
        ciphertext = await self._uow.accounts.get_token_ciphertext(cloudflare_account_id)
        plaintext_token = FernetCodec.decrypt(ciphertext, key=cloudflare_settings.FERNET_KEY)
        secret = secrets.token_urlsafe(32)
        destination_id = await self._client.create_webhook_destination(
            cf_account_id=account.cf_account_id, api_token=plaintext_token,
            name="itsm-alerting", url=webhook_url, secret=secret,
        )
        secret_ciphertext = FernetCodec.encrypt(secret, key=cloudflare_settings.FERNET_KEY)
        await self._uow.accounts.set_webhook_destination(
            cloudflare_account_id, cf_webhook_destination_id=destination_id, secret_ciphertext=secret_ciphertext
        )
        await self._uow.commit()
        return destination_id

    @facade
    async def get_webhook_secret(self, cloudflare_account_id: UUID) -> str | None:
        """Read-only: the decrypted webhook secret for this account, or None
        if no destination has ever been registered. Used exclusively by
        verify_cloudflare_webhook_secret (Task 9) — never registers anything,
        unlike ensure_webhook_destination."""
        _existing_id, existing_ciphertext = await self._uow.accounts.get_webhook_destination_ciphertext(
            cloudflare_account_id
        )
        if existing_ciphertext is None:
            return None
        return FernetCodec.decrypt(existing_ciphertext, key=cloudflare_settings.FERNET_KEY)


async def get_cloudflare_api(
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow),
    client: CloudflareClient = Depends(get_cloudflare_client),
) -> CloudflareApi:
    return CloudflareApi(uow, client)
```

```ini
# backend/.importlinter — cloudflare-facade contract's source_modules, add:
    app.modules.observability
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && uv run pytest tests/cloudflare/test_public.py -v && lint-imports`
Expected: PASS; 11/11 contracts kept (unchanged count, this only widens an existing contract's allow-list).

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/cloudflare/{public,repository}.py backend/.importlinter backend/tests/cloudflare/test_public.py
git commit -m "feat(cloudflare): add get_ready_client_for_environment and ensure_webhook_destination facade methods"
```

---

## Task 6: `notifications` — extract `DispatchNotification`, add `NotificationsApi.dispatch`

**Files:**
- Create: `backend/app/modules/notifications/services/dispatch_notification.py`
- Modify: `backend/app/modules/notifications/services/test_send_channel.py`, `public.py`
- Modify: `backend/.importlinter` (add `app.modules.observability` to `notifications-facade`'s `source_modules`)
- Test: `backend/tests/notifications/test_services.py` (existing `TestSendNotificationChannel` suite must pass unmodified), `backend/tests/notifications/test_public.py` (new)

**Interfaces:**
- Produces: `DispatchNotification.execute(channel: NotificationChannelRead, text: str) -> None` (raises the channel-type-specific exception on failure — `EmailRejected`, `TelegramApiUnavailable`, etc., never swallowed here), `NotificationsApi.dispatch(channel_id: UUID, message: str) -> None`.
- Consumes: `AbstractNotificationsUnitOfWork.channels`, `TelegramClient`/`EmailClient`/`BaseVnClient`, `FernetCodec`, `notifications_settings.FERNET_KEY`.

- [ ] **Step 1: Write the failing test proving the extraction preserves behavior**

```python
# backend/tests/notifications/test_services.py — the existing TestSendNotificationChannel
# tests must be run FIRST as a baseline before any change:
# `uv run pytest tests/notifications/test_services.py -k TestSendNotificationChannel -v`
# record the pass count, then re-run after Step 3's refactor and confirm identical pass count
# with zero test-code changes to that class — this is the behavior-preservation check itself,
# not a new test to write.
```

```python
# backend/tests/notifications/test_public.py (new)
from uuid import uuid4

import pytest

from app.modules.notifications.config import notifications_settings
from app.modules.notifications.constants import NotificationChannelType
from app.modules.notifications.exceptions import NotificationChannelNotFound
from app.modules.notifications.public import NotificationsApi
from app.modules.notifications.schemas import NotificationChannelRead

TEST_KEY = "kL8Zx3vQ9mN2pR7wT4yU6bC1dF5gH0jK3lM6nO9pQ2s="


@pytest.fixture(autouse=True)
def _fernet_key(monkeypatch) -> None:
    monkeypatch.setattr(notifications_settings, "FERNET_KEY", TEST_KEY)


class FakeChannelsRepo:
    def __init__(self, channel=None, raw_config=None) -> None:
        self._channel = channel
        self._raw_config = raw_config or {}

    async def get_by_id(self, channel_id):
        return self._channel

    async def get_config_ciphertext_fields(self, channel_id):
        return self._raw_config


class FakeUow:
    def __init__(self, channels) -> None:
        self.channels = channels


class FakeEmailClient:
    def __init__(self) -> None:
        self.sent = []

    async def send(self, *, recipients, subject, body):
        self.sent.append((recipients, subject, body))


class TestDispatch:
    async def test_raises_not_found_for_missing_channel(self) -> None:
        api = NotificationsApi(FakeUow(FakeChannelsRepo(channel=None)), telegram_client=None, email_client=None, base_vn_client=None)
        with pytest.raises(NotificationChannelNotFound):
            await api.dispatch(uuid4(), "hello")

    async def test_dispatches_to_email(self) -> None:
        channel = NotificationChannelRead(
            id=uuid4(), project_id=uuid4(), environment_id=None, type=NotificationChannelType.EMAIL,
            name="Team", config={"recipients": ["a@b.com"]}, is_active=True,
            created_at="2026-01-01T00:00:00Z", updated_at="2026-01-01T00:00:00Z",
        )
        email_client = FakeEmailClient()
        api = NotificationsApi(
            FakeUow(FakeChannelsRepo(channel=channel, raw_config={"recipients": ["a@b.com"]})),
            telegram_client=None, email_client=email_client, base_vn_client=None,
        )
        await api.dispatch(channel.id, "hello")
        assert email_client.sent == [(["a@b.com"], "ITSM Notification", "hello")]
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && uv run pytest tests/notifications/test_public.py -v`
Expected: `ImportError`/`AttributeError` — `NotificationsApi.dispatch` doesn't exist.

- [ ] **Step 3: Extract `DispatchNotification`, refactor `TestSendNotificationChannel`, add the facade method**

```python
# backend/app/modules/notifications/services/dispatch_notification.py (new)
"""Send a message through one channel — dispatches on channel.type to the
one client that knows how to send through it. Extracted from
TestSendNotificationChannel's private _dispatch (Decision #7 of Phase 9) so
both the test-send endpoint and cross-module incident notifications share
one implementation, never two."""

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.core.crypto import FernetCodec
from app.integrations.base_vn.client import BaseVnClient
from app.integrations.email.client import EmailClient
from app.integrations.telegram.client import TelegramClient
from app.modules.notifications.config import notifications_settings
from app.modules.notifications.constants import NotificationChannelType
from app.modules.notifications.exceptions import UnsupportedChannelType
from app.modules.notifications.rules import NotificationRules
from app.modules.notifications.schemas import NotificationChannelRead
from app.modules.notifications.uow import AbstractNotificationsUnitOfWork


class DispatchNotification(AbstractUseCase):
    def __init__(
        self, uow: AbstractNotificationsUnitOfWork, *,
        telegram_client: TelegramClient, email_client: EmailClient, base_vn_client: BaseVnClient,
    ) -> None:
        self._uow = uow
        self._telegram_client = telegram_client
        self._email_client = email_client
        self._base_vn_client = base_vn_client

    @use_case
    async def execute(self, channel: NotificationChannelRead, text: str) -> None:
        if channel.type == NotificationChannelType.OTHER:
            raise UnsupportedChannelType()

        raw_config = await self._uow.channels.get_config_ciphertext_fields(channel.id)

        if channel.type == NotificationChannelType.TELEGRAM:
            bot_token = FernetCodec.decrypt(raw_config["bot_token"], key=notifications_settings.FERNET_KEY)
            await self._telegram_client.send_message(bot_token=bot_token, chat_id=raw_config["chat_id"], text=text)
        elif channel.type == NotificationChannelType.EMAIL:
            await self._email_client.send(recipients=raw_config["recipients"], subject="ITSM Notification", body=text)
        elif channel.type == NotificationChannelType.BASE_VN:
            webhook_url = FernetCodec.decrypt(raw_config["webhook_url"], key=notifications_settings.FERNET_KEY)
            content = NotificationRules.render_base_content(raw_config.get("message_template", ""), text)
            await self._base_vn_client.send(webhook_url=webhook_url, base_content=content)
```

```python
# backend/app/modules/notifications/services/test_send_channel.py — refactor
# remove the private _dispatch method entirely; __init__ additionally builds a
# DispatchNotification instance; execute() calls it:
    def __init__(self, uow, *, telegram_client, email_client, base_vn_client, audit_api) -> None:
        self._uow = uow
        self._audit_api = audit_api
        self._dispatch_use_case = DispatchNotification(
            uow, telegram_client=telegram_client, email_client=email_client, base_vn_client=base_vn_client
        )

    @use_case
    async def execute(self, channel_id: UUID, *, message: str | None, actor: UserRead) -> None:
        channel = await self._uow.channels.get_by_id(channel_id)
        if channel is None:
            raise NotificationChannelNotFound()
        text = message or _DEFAULT_TEST_MESSAGE
        try:
            await self._dispatch_use_case.execute(channel, text)
        finally:
            await self._audit_api.log_event(...)  # unchanged
```

```python
# backend/app/modules/notifications/public.py — add
from app.modules.notifications.services.dispatch_notification import DispatchNotification

__all__ = [..., "NotificationsApi", "get_notifications_api"]


class NotificationsApi:
    def __init__(
        self, uow: AbstractNotificationsUnitOfWork, *,
        telegram_client: TelegramClient, email_client: EmailClient, base_vn_client: BaseVnClient,
    ) -> None:
        self._uow = uow
        self._dispatch_use_case = DispatchNotification(
            uow, telegram_client=telegram_client, email_client=email_client, base_vn_client=base_vn_client
        )

    @facade
    async def dispatch(self, channel_id: UUID, message: str) -> None:
        """Send `message` through channel_id. Raises NotificationChannelNotFound
        if it doesn't exist, or the channel-type-specific send exception on
        failure — the caller (observability's incident flow) decides whether
        to log-and-continue or propagate; this facade never swallows anything
        itself, since a silent no-op here would be a worse contract for a
        second, different caller than the one that motivated Decision #7."""
        channel = await self._uow.channels.get_by_id(channel_id)
        if channel is None:
            raise NotificationChannelNotFound()
        await self._dispatch_use_case.execute(channel, message)


async def get_notifications_api(
    uow: AbstractNotificationsUnitOfWork = Depends(get_uow),
    telegram_client: TelegramClient = Depends(get_telegram_client),
    email_client: EmailClient = Depends(get_email_client),
    base_vn_client: BaseVnClient = Depends(get_base_vn_client),
) -> NotificationsApi:
    return NotificationsApi(uow, telegram_client=telegram_client, email_client=email_client, base_vn_client=base_vn_client)
```

```ini
# backend/.importlinter — notifications-facade contract's source_modules, add:
    app.modules.observability
```

- [ ] **Step 4: Run to verify everything passes**

Run: `cd backend && uv run pytest tests/notifications/ -v`
Expected: PASS — the pre-existing `TestSendNotificationChannel` suite passes with **zero test-code changes**, proving the extraction was behavior-preserving; the new `test_public.py` tests also pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/notifications/{public,services/dispatch_notification,services/test_send_channel}.py backend/.importlinter backend/tests/notifications/test_public.py
git commit -m "refactor(notifications): extract DispatchNotification, add NotificationsApi.dispatch facade"
```

---

## Task 7: RBAC catalog — `alert_rule`/`incident` permissions

**Files:**
- Modify: `backend/app/modules/rbac/constants.py`
- Test: `backend/tests/rbac/test_constants.py` (or wherever the existing catalog-count assertion lives — confirm the exact file during implementation)

**Interfaces:**
- Produces: `RbacResources.ALERT_RULE = "alert_rule"`, `RbacResources.INCIDENT = "incident"`, `RbacActions.ACKNOWLEDGE = "acknowledge"`, `RbacActions.RESOLVE = "resolve"`, 8 new `RbacPermissionCatalog.CATALOG` rows.

- [ ] **Step 1: Write the failing test**

```python
def test_catalog_includes_alert_rule_and_incident_permissions() -> None:
    resources_actions = {(r, a) for r, a, _ in RbacPermissionCatalog.CATALOG}
    for action in ("create", "read", "update", "delete"):
        assert ("alert_rule", action) in resources_actions
    for action in ("create", "read", "acknowledge", "resolve"):
        assert ("incident", action) in resources_actions
    assert ("incident", "update") not in resources_actions  # append-only record, Decision #12
    assert ("incident", "delete") not in resources_actions
    assert len(RbacPermissionCatalog.CATALOG) == 32  # 24 existing + 8 new — confirm the real current count first
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && uv run pytest tests/rbac/ -v -k catalog_includes_alert_rule`
Expected: FAIL, rows don't exist yet.

- [ ] **Step 3: Implement**

```python
# backend/app/modules/rbac/constants.py — RbacResources, add:
    ALERT_RULE = "alert_rule"
    INCIDENT = "incident"

# RbacActions, add:
    ACKNOWLEDGE = "acknowledge"
    RESOLVE = "resolve"

# RbacPermissionCatalog.CATALOG, append:
    ("alert_rule", "create", "permissions.alert_rule.create"),
    ("alert_rule", "read", "permissions.alert_rule.read"),
    ("alert_rule", "update", "permissions.alert_rule.update"),
    ("alert_rule", "delete", "permissions.alert_rule.delete"),
    ("incident", "create", "permissions.incident.create"),
    ("incident", "read", "permissions.incident.read"),
    ("incident", "acknowledge", "permissions.incident.acknowledge"),
    ("incident", "resolve", "permissions.incident.resolve"),
```

- [ ] **Step 4: Run to verify it passes; re-seed the test DB**

Run: `cd backend && uv run pytest tests/rbac/ -v && uv run python -m app.seeds.seed_rbac` (against `itsm_test`)
Expected: PASS; seed script reports the 8 new rows added idempotently.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/rbac/constants.py backend/tests/rbac/
git commit -m "feat(rbac): add alert_rule and incident permission catalog rows"
```

---

## Task 8: `observability` repository + uow — `AlertRuleRepository`, `IncidentRepository`

**Files:**
- Modify: `backend/app/modules/observability/repository.py`, `uow.py`
- Test: `backend/tests/observability/test_repository.py` (real Postgres, mirrors the existing `LokiConfigRepository` test fixture shape)

**Interfaces:**
- Produces: `AbstractAlertRuleRepository`/`AlertRuleRepository` (`get_by_id`, `get_by_cf_policy_id`, `list_for_environment`, `create`, `update`, `delete`, `list_channel_ids`, `set_channels`), `AbstractIncidentRepository`/`IncidentRepository` (`get_by_id`, `get_open_by_correlation_id`, `list_page` filterable by project/environment/status, `create`, `update_status`).
- Consumes: `app.core.base.markers.database`, `AlertRule`/`AlertRuleChannel`/`Incident` models, `AlertRuleRead`/`IncidentRead` schemas.

- [ ] **Step 1: Write the failing tests** (abbreviated to the two riskiest methods — `get_by_cf_policy_id` since it's the webhook receiver's exact-match join key, and `get_open_by_correlation_id` since it backs the dedup guard; the remaining CRUD methods follow the identical shape already used by every other repository in this codebase)

```python
# backend/tests/observability/test_repository.py — append
class TestAlertRuleRepository:
    async def test_get_by_cf_policy_id_finds_exact_match(self, session) -> None:
        repo = AlertRuleRepository(session)
        env_id = await _make_environment(session)
        created = await repo.create(
            environment_id=env_id, name="DDoS rule", source=AlertRuleSource.CLOUDFLARE_NATIVE,
            cf_alert_type="advanced_ddos_attack_l4_alert", severity=AlertSeverity.HIGH,
        )
        await repo.set_cf_policy_id(created.id, cf_policy_id="policy-789")
        found = await repo.get_by_cf_policy_id("policy-789")
        assert found is not None and found.id == created.id

    async def test_get_by_cf_policy_id_returns_none_for_unknown(self, session) -> None:
        repo = AlertRuleRepository(session)
        assert await repo.get_by_cf_policy_id("nonexistent") is None


class TestIncidentRepository:
    async def test_get_open_by_correlation_id_excludes_resolved(self, session) -> None:
        repo = IncidentRepository(session)
        project_id, env_id = await _make_project_and_environment(session)
        resolved = await repo.create(
            project_id=project_id, environment_id=env_id, alert_rule_id=None, source=IncidentSource.CLOUDFLARE,
            category=IncidentCategory.DDOS, severity=AlertSeverity.HIGH, title="t",
            alert_correlation_id="corr-1",
        )
        from datetime import UTC, datetime

        await repo.update_status(resolved.id, status=IncidentStatus.RESOLVED, actor_id=None, at=datetime.now(UTC))
        assert await repo.get_open_by_correlation_id("corr-1") is None

        open_incident = await repo.create(
            project_id=project_id, environment_id=env_id, alert_rule_id=None, source=IncidentSource.CLOUDFLARE,
            category=IncidentCategory.DDOS, severity=AlertSeverity.HIGH, title="t2",
            alert_correlation_id="corr-2",
        )
        found = await repo.get_open_by_correlation_id("corr-2")
        assert found is not None and found.id == open_incident.id
```

(Ground `_make_environment`/`_make_project_and_environment` against this test file's real existing fixtures before writing — every prior phase's repository test file already has an equivalent helper to reuse, not reinvent.)

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && uv run pytest tests/observability/test_repository.py -v -k "CfPolicyId or CorrelationId"`
Expected: `ImportError`/`AttributeError`.

- [ ] **Step 3: Implement** — mirror `CloudflareTunnelRepository`'s exact shape (Abstract contract + SQLAlchemy concrete class, `@database` markers, no cache-aside per Decision #9's low-traffic-high-mutation reasoning, `AlertRuleRead`/`IncidentRead` schemas already defined in Task 1):

```python
# backend/app/modules/observability/repository.py — append
class AbstractAlertRuleRepository(AbstractRepository[AlertRuleRead, UUID]):
    @abstractmethod
    async def get_by_cf_policy_id(self, cf_policy_id: str) -> AlertRuleRead | None: ...
    @abstractmethod
    async def list_for_environment(self, environment_id: UUID) -> list[AlertRuleRead]: ...
    @abstractmethod
    async def create(self, *, environment_id, name, source, cf_alert_type=None, condition=None, severity) -> AlertRuleRead: ...
    @abstractmethod
    async def set_cf_policy_id(self, alert_rule_id: UUID, *, cf_policy_id: str) -> None: ...
    @abstractmethod
    async def update(self, alert_rule_id: UUID, *, name=None, is_active=None, severity=None) -> AlertRuleRead: ...
    @abstractmethod
    async def delete(self, alert_rule_id: UUID) -> None: ...
    @abstractmethod
    async def list_channel_ids(self, alert_rule_id: UUID) -> list[UUID]: ...
    @abstractmethod
    async def set_channels(self, alert_rule_id: UUID, channel_ids: list[UUID]) -> None: ...


class AlertRuleRepository(AbstractAlertRuleRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @database
    async def get_by_id(self, entity_id: UUID) -> AlertRuleRead | None:
        row = await self._session.get(AlertRule, entity_id)
        return await self._to_read(row) if row else None

    @database
    async def get_by_cf_policy_id(self, cf_policy_id: str) -> AlertRuleRead | None:
        row = await self._session.scalar(select(AlertRule).where(AlertRule.cf_policy_id == cf_policy_id))
        return await self._to_read(row) if row else None

    @database
    async def list_for_environment(self, environment_id: UUID) -> list[AlertRuleRead]:
        rows = await self._session.scalars(
            select(AlertRule).where(AlertRule.environment_id == environment_id).order_by(AlertRule.created_at)
        )
        return [await self._to_read(row) for row in rows]

    @database
    async def create(self, *, environment_id, name, source, cf_alert_type=None, condition=None, severity) -> AlertRuleRead:
        row = AlertRule(
            environment_id=environment_id, name=name, source=source,
            cf_alert_type=cf_alert_type, condition=condition, severity=severity,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return await self._to_read(row)

    @database
    async def set_cf_policy_id(self, alert_rule_id: UUID, *, cf_policy_id: str) -> None:
        row = await self._session.get(AlertRule, alert_rule_id)
        row.cf_policy_id = cf_policy_id
        await self._session.flush()

    @database
    async def update(self, alert_rule_id: UUID, *, name=None, is_active=None, severity=None) -> AlertRuleRead:
        row = await self._session.get(AlertRule, alert_rule_id)
        if name is not None: row.name = name
        if is_active is not None: row.is_active = is_active
        if severity is not None: row.severity = severity
        await self._session.flush()
        await self._session.refresh(row)
        return await self._to_read(row)

    @database
    async def delete(self, alert_rule_id: UUID) -> None:
        row = await self._session.get(AlertRule, alert_rule_id)
        if row is not None:
            await self._session.delete(row)
            await self._session.flush()

    @database
    async def list_channel_ids(self, alert_rule_id: UUID) -> list[UUID]:
        rows = await self._session.scalars(
            select(AlertRuleChannel.channel_id).where(AlertRuleChannel.alert_rule_id == alert_rule_id)
        )
        return list(rows)

    @database
    async def set_channels(self, alert_rule_id: UUID, channel_ids: list[UUID]) -> None:
        await self._session.execute(delete(AlertRuleChannel).where(AlertRuleChannel.alert_rule_id == alert_rule_id))
        for channel_id in channel_ids:
            self._session.add(AlertRuleChannel(alert_rule_id=alert_rule_id, channel_id=channel_id))
        await self._session.flush()

    @helper
    async def _to_read(self, row: AlertRule) -> AlertRuleRead:
        channel_ids = await self.list_channel_ids(row.id)
        return AlertRuleRead(
            id=row.id, environment_id=row.environment_id, name=row.name, source=row.source,
            cf_alert_type=row.cf_alert_type, cf_policy_id=row.cf_policy_id, condition=row.condition,
            severity=row.severity, is_active=row.is_active, channel_ids=channel_ids,
            created_at=row.created_at, updated_at=row.updated_at,
        )


class AbstractIncidentRepository(AbstractRepository[IncidentRead, UUID]):
    @abstractmethod
    async def get_open_by_correlation_id(self, correlation_id: str) -> IncidentRead | None: ...
    @abstractmethod
    async def list_page_filtered(self, *, project_id=None, environment_id=None, status=None, limit, offset) -> tuple[list[IncidentRead], int]: ...
    @abstractmethod
    async def create(self, *, project_id, environment_id, alert_rule_id, source, category, severity, title,
                      alert_correlation_id=None, log_ref_id=None) -> IncidentRead: ...
    @abstractmethod
    async def update_status(self, incident_id: UUID, *, status, actor_id, at) -> IncidentRead: ...


class IncidentRepository(AbstractIncidentRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @database
    async def get_by_id(self, entity_id: UUID) -> IncidentRead | None:
        row = await self._session.get(Incident, entity_id)
        return IncidentRead.model_validate(row) if row else None

    @database
    async def get_open_by_correlation_id(self, correlation_id: str) -> IncidentRead | None:
        row = await self._session.scalar(
            select(Incident).where(
                Incident.alert_correlation_id == correlation_id, Incident.status != IncidentStatus.RESOLVED
            )
        )
        return IncidentRead.model_validate(row) if row else None

    @database
    async def list_page_filtered(self, *, project_id=None, environment_id=None, status=None, limit, offset):
        stmt = select(Incident)
        if project_id is not None: stmt = stmt.where(Incident.project_id == project_id)
        if environment_id is not None: stmt = stmt.where(Incident.environment_id == environment_id)
        if status is not None: stmt = stmt.where(Incident.status == status)
        rows = await self._session.scalars(stmt.order_by(Incident.detected_at.desc()).limit(limit).offset(offset))
        items = [IncidentRead.model_validate(r) for r in rows]
        total = await self._session.scalar(select(func.count()).select_from(stmt.subquery()))
        return items, total or 0

    @database
    async def create(self, *, project_id, environment_id, alert_rule_id, source, category, severity, title,
                      alert_correlation_id=None, log_ref_id=None) -> IncidentRead:
        row = Incident(
            project_id=project_id, environment_id=environment_id, alert_rule_id=alert_rule_id,
            source=source, category=category, severity=severity, title=title,
            alert_correlation_id=alert_correlation_id, log_ref_id=log_ref_id,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return IncidentRead.model_validate(row)

    @database
    async def update_status(self, incident_id: UUID, *, status, actor_id, at) -> IncidentRead:
        row = await self._session.get(Incident, incident_id)
        row.status = status
        if status == IncidentStatus.ACKNOWLEDGED:
            row.acknowledged_at, row.acknowledged_by = at, actor_id
        elif status == IncidentStatus.RESOLVED:
            row.resolved_at, row.resolved_by = at, actor_id
        await self._session.flush()
        await self._session.refresh(row)
        return IncidentRead.model_validate(row)
```

```python
# backend/app/modules/observability/uow.py — extend
class AbstractObservabilityUnitOfWork(AbstractUnitOfWork):
    loki_configs: AbstractLokiConfigRepository
    alert_rules: AbstractAlertRuleRepository
    incidents: AbstractIncidentRepository


class ObservabilityUnitOfWork(AbstractObservabilityUnitOfWork):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.loki_configs = LokiConfigRepository(session)
        self.alert_rules = AlertRuleRepository(session)
        self.incidents = IncidentRepository(session)
    # commit/rollback unchanged
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && uv run pytest tests/observability/test_repository.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/observability/{repository,uow}.py backend/tests/observability/test_repository.py
git commit -m "feat(observability): add AlertRuleRepository and IncidentRepository"
```

---

## Task 9: `observability/dependencies.py` — webhook-secret verification

**Files:**
- Modify: `backend/app/modules/observability/dependencies.py`, `config.py`
- Test: `backend/tests/observability/test_dependencies.py` (new)

**Interfaces:**
- Produces: `verify_cloudflare_webhook_secret(cloudflare_account_id: UUID, ...) -> None` (Depends factory-free — path param resolves directly), `verify_loki_webhook_secret(...) -> None`. Both raise `InvalidWebhookSecret` (401) on mismatch.
- Consumes: `ObservabilityConfig.LOKI_WEBHOOK_SECRET` (new field), `CloudflareApi` (to look up the account's stored secret), `hmac.compare_digest`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/observability/test_dependencies.py (new)
import hmac
from uuid import uuid4

import pytest
from fastapi import Header, HTTPException

from app.modules.observability.config import observability_settings
from app.modules.observability.exceptions import InvalidWebhookSecret


class FakeCloudflareApiForWebhook:
    def __init__(self, secrets: dict) -> None:
        self._secrets = secrets

    async def get_webhook_secret(self, account_id):
        return self._secrets.get(account_id)


class TestVerifyCloudflareWebhookSecret:
    async def test_missing_header_rejects(self) -> None:
        from app.modules.observability.dependencies import verify_cloudflare_webhook_secret
        account_id = uuid4()
        with pytest.raises(InvalidWebhookSecret):
            await verify_cloudflare_webhook_secret(
                cloudflare_account_id=account_id, cf_webhook_auth=None,
                cloudflare_api=FakeCloudflareApiForWebhook({account_id: "real-secret"}),
            )

    async def test_wrong_secret_rejects(self) -> None:
        from app.modules.observability.dependencies import verify_cloudflare_webhook_secret
        account_id = uuid4()
        with pytest.raises(InvalidWebhookSecret):
            await verify_cloudflare_webhook_secret(
                cloudflare_account_id=account_id, cf_webhook_auth="wrong",
                cloudflare_api=FakeCloudflareApiForWebhook({account_id: "real-secret"}),
            )

    async def test_correct_secret_passes(self) -> None:
        from app.modules.observability.dependencies import verify_cloudflare_webhook_secret
        account_id = uuid4()
        await verify_cloudflare_webhook_secret(
            cloudflare_account_id=account_id, cf_webhook_auth="real-secret",
            cloudflare_api=FakeCloudflareApiForWebhook({account_id: "real-secret"}),
        )  # no raise


class TestVerifyLokiWebhookSecret:
    async def test_wrong_bearer_rejects(self, monkeypatch) -> None:
        from app.modules.observability.dependencies import verify_loki_webhook_secret
        monkeypatch.setattr(observability_settings, "LOKI_WEBHOOK_SECRET", "real-secret")
        with pytest.raises(InvalidWebhookSecret):
            await verify_loki_webhook_secret(authorization="Bearer wrong")

    async def test_correct_bearer_passes(self, monkeypatch) -> None:
        from app.modules.observability.dependencies import verify_loki_webhook_secret
        monkeypatch.setattr(observability_settings, "LOKI_WEBHOOK_SECRET", "real-secret")
        await verify_loki_webhook_secret(authorization="Bearer real-secret")  # no raise
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && uv run pytest tests/observability/test_dependencies.py -v`
Expected: `ImportError`.

- [ ] **Step 3: Implement**

```python
# backend/app/modules/observability/config.py — add field
    LOKI_WEBHOOK_SECRET: str = ""
```

```python
# backend/app/modules/observability/dependencies.py — add
import hmac
from fastapi import Header
from app.modules.cloudflare.public import CloudflareApi, get_cloudflare_api
from app.modules.observability.config import observability_settings
from app.modules.observability.exceptions import InvalidWebhookSecret


async def verify_cloudflare_webhook_secret(
    cloudflare_account_id: UUID,
    cf_webhook_auth: str | None = Header(default=None),
    cloudflare_api: CloudflareApi = Depends(get_cloudflare_api),
) -> None:
    """Reject unless cf-webhook-auth matches the secret stored for this
    account (Decision #5 — the path segment is what resolves WHICH secret
    to check, never a body/payload field). Uses CloudflareApi.get_webhook_secret
    (Task 5) — the read-only counterpart of ensure_webhook_destination."""
    stored_secret = await cloudflare_api.get_webhook_secret(cloudflare_account_id)
    if not stored_secret or not cf_webhook_auth or not hmac.compare_digest(cf_webhook_auth, stored_secret):
        raise InvalidWebhookSecret()


async def verify_loki_webhook_secret(authorization: str | None = Header(default=None)) -> None:
    """Bearer-token check against one app-wide shared secret (Decision #11) —
    Alertmanager's http_config.authorization sends this natively."""
    expected = f"Bearer {observability_settings.LOKI_WEBHOOK_SECRET}"
    if not authorization or not observability_settings.LOKI_WEBHOOK_SECRET or not hmac.compare_digest(authorization, expected):
        raise InvalidWebhookSecret()
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && uv run pytest tests/observability/test_dependencies.py tests/cloudflare/test_public.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/observability/{dependencies,config}.py backend/app/modules/cloudflare/public.py backend/tests/observability/test_dependencies.py backend/tests/cloudflare/test_public.py
git commit -m "feat(observability): add webhook secret verification dependencies"
```

---

## Task 10: `observability/services/` — alert-rule CRUD (`list_available_alerts`, `create/update/delete/list_alert_rules`)

**Files:**
- Create: `backend/app/modules/observability/services/{list_available_alerts,create_alert_rule,update_alert_rule,delete_alert_rule,list_alert_rules}.py`
- Test: `backend/tests/observability/test_services.py`

**Interfaces:**
- Produces: `ListAvailableAlerts.execute(environment_id) -> list[AvailableAlertOption]`, `CreateAlertRule.execute(environment_id, **AlertRuleCreate fields, actor) -> AlertRuleRead`, `UpdateAlertRule.execute(alert_rule_id, **fields, actor) -> AlertRuleRead`, `DeleteAlertRule.execute(alert_rule_id, actor) -> None`, `ListAlertRules.execute(environment_id) -> list[AlertRuleRead]`.
- Consumes: `AbstractObservabilityUnitOfWork`, `CloudflareApi.get_ready_client_for_environment`/`.ensure_webhook_destination`, `LokiClient.upsert_rule_group`, `ProjectsApi.get_environment_by_id`, `AuditApi`, `settings.BACKEND_BASE_URL`.

- [ ] **Step 1: Write the failing tests** (the CF-native creation path is the one genuinely multi-step flow worth full coverage; update/delete/list follow the established thin-CRUD pattern already used throughout this codebase)

```python
# backend/tests/observability/test_services.py — append
from app.config import settings as root_settings


class FakeReadyCloudflareClient:
    def __init__(self, client, cf_account_id="cf-1", api_token="tok", cloudflare_account_id=None) -> None:
        self.client, self.cf_account_id, self.api_token, self.cloudflare_account_id = (
            client, cf_account_id, api_token, cloudflare_account_id or uuid4()
        )


class FakeCloudflareApiForAlertRules:
    def __init__(self, ready=None, webhook_destination_id="wh-123") -> None:
        self._ready = ready
        self._webhook_destination_id = webhook_destination_id
        self.ensure_calls = []

    async def get_ready_client_for_environment(self, environment_id):
        return self._ready

    async def ensure_webhook_destination(self, cloudflare_account_id, *, webhook_url):
        self.ensure_calls.append((cloudflare_account_id, webhook_url))
        return self._webhook_destination_id


class FakeCloudflareClientForPolicy:
    def __init__(self, policy_id="policy-789") -> None:
        self.policy_id = policy_id
        self.created = []

    async def create_policy(self, **kwargs):
        self.created.append(kwargs)
        return self.policy_id


class TestCreateAlertRuleCloudflareNative:
    async def test_full_flow_persists_cf_policy_id(self) -> None:
        env_id = uuid4()
        cf_client = FakeCloudflareClientForPolicy()
        cloudflare_api = FakeCloudflareApiForAlertRules(ready=FakeReadyCloudflareClient(cf_client))
        uow = FakeObservabilityUnitOfWork()
        use_case = CreateAlertRule(uow, cloudflare_api=cloudflare_api, loki_client=None, projects_api=FakeProjectsApi(environments={env_id: SimpleNamespace(project_id=uuid4())}), audit_api=FakeAuditApi())

        result = await use_case.execute(
            environment_id=env_id, name="DDoS", source=AlertRuleSource.CLOUDFLARE_NATIVE,
            cf_alert_type="advanced_ddos_attack_l4_alert", condition=None, severity=AlertSeverity.HIGH,
            channel_ids=[], actor=_actor(),
        )
        assert result.cf_policy_id == "policy-789"
        assert cloudflare_api.ensure_calls  # webhook destination was ensured
        assert cf_client.created[0]["alert_type"] == "advanced_ddos_attack_l4_alert"

    async def test_unbound_environment_raises(self) -> None:
        env_id = uuid4()
        cloudflare_api = FakeCloudflareApiForAlertRules(ready=None)
        use_case = CreateAlertRule(FakeObservabilityUnitOfWork(), cloudflare_api=cloudflare_api, loki_client=None,
                                    projects_api=FakeProjectsApi(environments={env_id: SimpleNamespace(project_id=uuid4())}),
                                    audit_api=FakeAuditApi())
        with pytest.raises(ObservabilityEnvironmentNotFound):  # or a dedicated "cloudflare not bound" error — confirm naming during implementation
            await use_case.execute(environment_id=env_id, name="X", source=AlertRuleSource.CLOUDFLARE_NATIVE,
                                    cf_alert_type="x", condition=None, severity=AlertSeverity.LOW, channel_ids=[], actor=_actor())

    async def test_cloudflare_failure_persists_nothing(self) -> None:
        env_id = uuid4()

        class FailingCfClient:
            async def create_policy(self, **kwargs):
                raise CloudflareDnsOperationRejected()

        cloudflare_api = FakeCloudflareApiForAlertRules(ready=FakeReadyCloudflareClient(FailingCfClient()))
        uow = FakeObservabilityUnitOfWork()
        use_case = CreateAlertRule(uow, cloudflare_api=cloudflare_api, loki_client=None,
                                    projects_api=FakeProjectsApi(environments={env_id: SimpleNamespace(project_id=uuid4())}),
                                    audit_api=FakeAuditApi())
        with pytest.raises(CloudflareDnsOperationRejected):
            await use_case.execute(environment_id=env_id, name="X", source=AlertRuleSource.CLOUDFLARE_NATIVE,
                                    cf_alert_type="x", condition=None, severity=AlertSeverity.LOW, channel_ids=[], actor=_actor())
        assert uow.alert_rules._rows == {}  # nothing persisted


class TestCreateAlertRuleLokiQuery:
    async def test_calls_upsert_rule_group_with_join_label(self) -> None:
        class FakeLokiClient:
            def __init__(self) -> None:
                self.calls = []
            async def upsert_rule_group(self, **kwargs):
                self.calls.append(kwargs)

        loki_client = FakeLokiClient()
        env_id = uuid4()
        use_case = CreateAlertRule(
            FakeObservabilityUnitOfWork(), cloudflare_api=None, loki_client=loki_client,
            projects_api=FakeProjectsApi(environments={env_id: SimpleNamespace(project_id=uuid4())}),
            audit_api=FakeAuditApi(),
        )
        result = await use_case.execute(
            environment_id=env_id, name="Error rate", source=AlertRuleSource.LOKI_QUERY, cf_alert_type=None,
            condition={"query": '{app="x"} |= "error"', "for": "5m"}, severity=AlertSeverity.MEDIUM,
            channel_ids=[], actor=_actor(),
        )
        assert loki_client.calls[0]["labels"] == {"app_alert_rule_id": str(result.id)}
        assert loki_client.calls[0]["namespace"] == "itsm"
```

(`FakeObservabilityUnitOfWork`/`FakeProjectsApi`/`FakeAuditApi`/`_actor()` mirror the exact Fake shapes already established in `tests/notifications/test_services.py` — reuse that convention, don't reinvent field names.)

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && uv run pytest tests/observability/test_services.py -v -k CreateAlertRule`
Expected: `ImportError`.

- [ ] **Step 3: Implement**

```python
# backend/app/modules/observability/services/create_alert_rule.py (new)
"""Create an alert rule. CLOUDFLARE_NATIVE: resolve environment's bound
Cloudflare account -> ensure a webhook destination exists for it -> create
the Notification Policy -> persist with the real cf_policy_id (Decision #9).
LOKI_QUERY: push the rule into Loki's own Ruler so it actually gets
evaluated (Decision #10) — storing it in our DB alone would never cause
Loki to fire anything."""

from uuid import UUID

from app.config import settings as root_settings
from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.cloudflare.public import CloudflareApi
from app.modules.observability.constants import AlertingAuditActions, AlertRuleSource
from app.modules.observability.exceptions import ObservabilityEnvironmentNotFound
from app.modules.observability.schemas import AlertRuleRead
from app.modules.observability.uow import AbstractObservabilityUnitOfWork
from app.modules.projects.public import ProjectsApi
from app.modules.users.public import UserRead


class CreateAlertRule(AbstractUseCase):
    def __init__(
        self, uow: AbstractObservabilityUnitOfWork, *, cloudflare_api: CloudflareApi | None,
        loki_client, projects_api: ProjectsApi, audit_api: AuditApi,
    ) -> None:
        self._uow = uow
        self._cloudflare_api = cloudflare_api
        self._loki_client = loki_client
        self._projects_api = projects_api
        self._audit_api = audit_api

    @use_case
    async def execute(
        self, *, environment_id: UUID, name: str, source: AlertRuleSource, cf_alert_type: str | None,
        condition: dict | None, severity, channel_ids: list[UUID], actor: UserRead,
    ) -> AlertRuleRead:
        environment = await self._projects_api.get_environment_by_id(environment_id)
        if environment is None:
            raise ObservabilityEnvironmentNotFound()

        rule = await self._uow.alert_rules.create(
            environment_id=environment_id, name=name, source=source,
            cf_alert_type=cf_alert_type, condition=condition, severity=severity,
        )

        if source == AlertRuleSource.CLOUDFLARE_NATIVE:
            ready = await self._cloudflare_api.get_ready_client_for_environment(environment_id)
            if ready is None:
                raise ObservabilityEnvironmentNotFound()  # or a dedicated error — see plan note above
            webhook_url = f"{root_settings.BACKEND_BASE_URL}/api/v1/webhooks/cloudflare-alert/{ready.cloudflare_account_id}"
            webhook_destination_id = await self._cloudflare_api.ensure_webhook_destination(
                ready.cloudflare_account_id, webhook_url=webhook_url
            )
            policy_id = await ready.client.create_policy(
                cf_account_id=ready.cf_account_id, api_token=ready.api_token, name=name,
                alert_type=cf_alert_type, webhook_destination_id=webhook_destination_id,
            )
            await self._uow.alert_rules.set_cf_policy_id(rule.id, cf_policy_id=policy_id)
            rule = await self._uow.alert_rules.get_by_id(rule.id)
        elif source == AlertRuleSource.LOKI_QUERY:
            await self._loki_client.upsert_rule_group(
                endpoint_url=condition.get("endpoint_url", ""), namespace="itsm",
                group_name=f"alert-rule-{rule.id}", rule_name=f"alert-rule-{rule.id}",
                expr=condition["query"], for_duration=condition.get("for", "5m"),
                labels={"app_alert_rule_id": str(rule.id)}, auth_header=None,
            )

        if channel_ids:
            await self._uow.alert_rules.set_channels(rule.id, channel_ids)
            rule = await self._uow.alert_rules.get_by_id(rule.id)

        await self._uow.commit()
        await self._audit_api.log_event(
            type=AuditEventType.AUDIT, source=AuditSource.USER_ACTION,
            action=AlertingAuditActions.ALERT_RULE_CREATED, severity=AuditSeverity.INFO,
            message=f"Alert rule '{name}' created", actor=AuditActor(user_id=actor.id, email=actor.email),
            environment_id=environment_id,
        )
        return rule
```

(`update_alert_rule.py`/`delete_alert_rule.py`/`list_alert_rules.py`/`list_available_alerts.py` follow the same shape already established by every prior CRUD service in this codebase — `list_available_alerts.py` resolves a ready client for the environment then calls `client.list_available_alerts`, shaping the raw dicts into `AvailableAlertOption`; `delete_alert_rule.py` calls `client.delete_policy` first when `source == CLOUDFLARE_NATIVE` and `cf_policy_id` is set, mirroring the "external system first" convention.)

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && uv run pytest tests/observability/test_services.py -v`
Expected: PASS.

- [ ] **Step 5: Add the remaining CRUD service files + their tests** (update/delete/list/list-available-alerts — same pattern, no new decisions to make), run again, confirm green.

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/observability/services/{list_available_alerts,create_alert_rule,update_alert_rule,delete_alert_rule,list_alert_rules}.py backend/tests/observability/test_services.py
git commit -m "feat(observability): add alert-rule CRUD services (Cloudflare-native + Loki-query paths)"
```

---

## Task 11: `observability/services/` — `handle_cloudflare_webhook`, `handle_loki_webhook`

**Files:**
- Create: `backend/app/modules/observability/services/{handle_cloudflare_webhook,handle_loki_webhook}.py`
- Test: `backend/tests/observability/test_services.py`

**Interfaces:**
- Produces: `HandleCloudflareWebhook.execute(cloudflare_account_id, payload: dict) -> None`, `HandleLokiWebhook.execute(payload: dict) -> None`. Neither raises for "no matching rule found" — logs and returns.
- Consumes: `AbstractObservabilityUnitOfWork.{alert_rules,incidents}`, `ProjectsApi.get_environment_by_id`, `NotificationsApi.dispatch`, `AlertingRules.category_for_cloudflare_alert_type`.

- [ ] **Step 1: Write the failing tests** (this is the highest-value test coverage in the whole phase — every Decision #4/#6/#11 branch gets its own case)

```python
# backend/tests/observability/test_services.py — append
_CF_PAYLOAD_BASE = {
    "name": "n", "text": "DDoS attack detected on zone example.com", "data": {}, "ts": 1136214245,
    "account_id": "acc1", "policy_id": "policy-789", "policy_name": "n",
    "alert_type": "advanced_ddos_attack_l4_alert", "alert_correlation_id": "corr-1",
    "alert_event": "ALERT_STATE_EVENT_START",
}


class TestHandleCloudflareWebhook:
    async def test_creates_incident_for_matching_policy(self) -> None:
        env_id, project_id = uuid4(), uuid4()
        uow = FakeObservabilityUnitOfWork()
        rule = await uow.alert_rules.create(environment_id=env_id, name="n", source=AlertRuleSource.CLOUDFLARE_NATIVE,
                                             cf_alert_type="advanced_ddos_attack_l4_alert", severity=AlertSeverity.HIGH)
        await uow.alert_rules.set_cf_policy_id(rule.id, cf_policy_id="policy-789")
        notifications_api = FakeNotificationsApiForWebhook()
        use_case = HandleCloudflareWebhook(
            uow, notifications_api=notifications_api,
            projects_api=FakeProjectsApi(environments={env_id: SimpleNamespace(project_id=project_id)}),
            audit_api=FakeAuditApi(),
        )
        await use_case.execute(cloudflare_account_id=uuid4(), payload=_CF_PAYLOAD_BASE)

        incidents, _ = await uow.incidents.list_page_filtered(limit=10, offset=0)
        assert len(incidents) == 1
        assert incidents[0].category == IncidentCategory.DDOS
        assert incidents[0].severity == AlertSeverity.HIGH  # from the rule, not the payload — Decision #6
        assert incidents[0].title == "DDoS attack detected on zone example.com"

    async def test_ignores_end_event(self) -> None:
        uow = FakeObservabilityUnitOfWork()
        use_case = HandleCloudflareWebhook(uow, notifications_api=FakeNotificationsApiForWebhook(),
                                            projects_api=FakeProjectsApi(), audit_api=FakeAuditApi())
        payload = {**_CF_PAYLOAD_BASE, "alert_event": "ALERT_STATE_EVENT_END"}
        await use_case.execute(cloudflare_account_id=uuid4(), payload=payload)
        incidents, _ = await uow.incidents.list_page_filtered(limit=10, offset=0)
        assert incidents == []

    async def test_dedupes_by_correlation_id(self) -> None:
        env_id, project_id = uuid4(), uuid4()
        uow = FakeObservabilityUnitOfWork()
        rule = await uow.alert_rules.create(environment_id=env_id, name="n", source=AlertRuleSource.CLOUDFLARE_NATIVE,
                                             cf_alert_type="advanced_ddos_attack_l4_alert", severity=AlertSeverity.HIGH)
        await uow.alert_rules.set_cf_policy_id(rule.id, cf_policy_id="policy-789")
        use_case = HandleCloudflareWebhook(
            uow, notifications_api=FakeNotificationsApiForWebhook(),
            projects_api=FakeProjectsApi(environments={env_id: SimpleNamespace(project_id=project_id)}),
            audit_api=FakeAuditApi(),
        )
        await use_case.execute(cloudflare_account_id=uuid4(), payload=_CF_PAYLOAD_BASE)
        await use_case.execute(cloudflare_account_id=uuid4(), payload=_CF_PAYLOAD_BASE)  # same alert_correlation_id
        incidents, total = await uow.incidents.list_page_filtered(limit=10, offset=0)
        assert total == 1

    async def test_unmatched_policy_id_skips_without_raising(self) -> None:
        uow = FakeObservabilityUnitOfWork()
        use_case = HandleCloudflareWebhook(uow, notifications_api=FakeNotificationsApiForWebhook(),
                                            projects_api=FakeProjectsApi(), audit_api=FakeAuditApi())
        await use_case.execute(cloudflare_account_id=uuid4(), payload=_CF_PAYLOAD_BASE)  # no raise
        incidents, _ = await uow.incidents.list_page_filtered(limit=10, offset=0)
        assert incidents == []

    async def test_failed_notification_dispatch_does_not_block_incident_creation(self) -> None:
        env_id, project_id = uuid4(), uuid4()
        uow = FakeObservabilityUnitOfWork()
        rule = await uow.alert_rules.create(environment_id=env_id, name="n", source=AlertRuleSource.CLOUDFLARE_NATIVE,
                                             cf_alert_type="advanced_ddos_attack_l4_alert", severity=AlertSeverity.HIGH)
        await uow.alert_rules.set_cf_policy_id(rule.id, cf_policy_id="policy-789")
        await uow.alert_rules.set_channels(rule.id, [uuid4()])
        failing_notifications_api = FakeNotificationsApiForWebhook(raises=True)
        use_case = HandleCloudflareWebhook(
            uow, notifications_api=failing_notifications_api,
            projects_api=FakeProjectsApi(environments={env_id: SimpleNamespace(project_id=project_id)}),
            audit_api=FakeAuditApi(),
        )
        await use_case.execute(cloudflare_account_id=uuid4(), payload=_CF_PAYLOAD_BASE)  # no raise
        incidents, total = await uow.incidents.list_page_filtered(limit=10, offset=0)
        assert total == 1  # incident persisted despite the notification failure
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && uv run pytest tests/observability/test_services.py -v -k HandleCloudflareWebhook`
Expected: `ImportError`.

- [ ] **Step 3: Implement**

```python
# backend/app/modules/observability/services/handle_cloudflare_webhook.py (new)
"""Receives a real Cloudflare Notifications webhook call. Verified live
against developers.cloudflare.com/notifications/reference/webhook-payload-schema/
(Decision #4): policy_id is the deterministic join key to alert_rules.
Only ALERT_STATE_EVENT_START creates anything; resolution stays a human
action via the ack/resolve endpoints. Deduped by alert_correlation_id
against any non-RESOLVED incident."""

import logging
from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.notifications.public import NotificationsApi
from app.modules.observability.constants import AlertingAuditActions, AlertingLimits, IncidentSource
from app.modules.observability.rules import AlertingRules
from app.modules.observability.uow import AbstractObservabilityUnitOfWork
from app.modules.projects.public import ProjectsApi

logger = logging.getLogger(__name__)

_SYSTEM_ACTOR = AuditActor(user_id=None, email=None)


class HandleCloudflareWebhook(AbstractUseCase):
    def __init__(
        self, uow: AbstractObservabilityUnitOfWork, *, notifications_api: NotificationsApi,
        projects_api: ProjectsApi, audit_api: AuditApi,
    ) -> None:
        self._uow = uow
        self._notifications_api = notifications_api
        self._projects_api = projects_api
        self._audit_api = audit_api

    @use_case
    async def execute(self, *, cloudflare_account_id: UUID, payload: dict) -> None:
        if payload.get("alert_event") != "ALERT_STATE_EVENT_START":
            return

        policy_id = payload.get("policy_id")
        rule = await self._uow.alert_rules.get_by_cf_policy_id(policy_id) if policy_id else None
        if rule is None:
            logger.warning("cloudflare webhook: no alert_rules row for policy_id=%s", policy_id)
            return

        correlation_id = payload.get("alert_correlation_id")
        if correlation_id and await self._uow.incidents.get_open_by_correlation_id(correlation_id):
            return  # already tracking this ongoing alert

        environment = await self._projects_api.get_environment_by_id(rule.environment_id)
        category = AlertingRules.category_for_cloudflare_alert_type(payload.get("alert_type", ""))
        title = (payload.get("text") or "Cloudflare alert")[: AlertingLimits.MAX_TITLE_LENGTH]

        incident = await self._uow.incidents.create(
            project_id=environment.project_id, environment_id=rule.environment_id, alert_rule_id=rule.id,
            source=IncidentSource.CLOUDFLARE, category=category, severity=rule.severity, title=title,
            alert_correlation_id=correlation_id,
        )
        await self._uow.commit()
        await self._audit_api.log_event(
            type=AuditEventType.INCIDENT_DETECTION, source=AuditSource.CLOUDFLARE,
            action=AlertingAuditActions.INCIDENT_DETECTED, severity=AuditSeverity.HIGH,
            message=title, actor=_SYSTEM_ACTOR, project_id=incident.project_id,
            environment_id=incident.environment_id, incident_id=str(incident.id),
        )
        await self._fan_out(rule.id, incident.id, title)

    async def _fan_out(self, alert_rule_id: UUID, incident_id: UUID, message: str) -> None:
        channel_ids = await self._uow.alert_rules.list_channel_ids(alert_rule_id)
        for channel_id in channel_ids:
            try:
                await self._notifications_api.dispatch(channel_id, message)
                status = "sent"
            except Exception:  # noqa: BLE001 -- a broken channel must never block incident creation, Decision #7
                logger.warning("notification dispatch failed for channel %s", channel_id, exc_info=True)
                status = "failed"
            await self._audit_api.log_event(
                type=AuditEventType.NOTIFICATION_SENT, source=AuditSource.SYSTEM,
                action=AlertingAuditActions.INCIDENT_NOTIFICATION_SENT, severity=AuditSeverity.INFO,
                message=f"Notification {status} for channel {channel_id}", actor=_SYSTEM_ACTOR,
                incident_id=str(incident_id),
            )
```

```python
# backend/app/modules/observability/services/handle_loki_webhook.py (new)
"""Receives an Alertmanager webhook_config POST — the standard Prometheus
Alertmanager contract, not documented anywhere in this repo's own spec docs
(Decision #11). Joins back to alert_rules via labels.app_alert_rule_id
(set by upsert_rule_group at rule-creation time). Dedupes by Alertmanager's
own fingerprint. Only status=="firing" entries are processed — a batch may
contain several alerts, each handled independently; one bad entry never
aborts the rest."""

import logging

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.notifications.public import NotificationsApi
from app.modules.observability.constants import AlertingAuditActions, AlertingLimits, IncidentCategory, IncidentSource
from app.modules.observability.uow import AbstractObservabilityUnitOfWork
from app.modules.projects.public import ProjectsApi

logger = logging.getLogger(__name__)
_SYSTEM_ACTOR = AuditActor(user_id=None, email=None)


class HandleLokiWebhook(AbstractUseCase):
    def __init__(
        self, uow: AbstractObservabilityUnitOfWork, *, notifications_api: NotificationsApi,
        projects_api: ProjectsApi, audit_api: AuditApi,
    ) -> None:
        self._uow = uow
        self._notifications_api = notifications_api
        self._projects_api = projects_api
        self._audit_api = audit_api

    @use_case
    async def execute(self, payload: dict) -> None:
        for alert in payload.get("alerts", []):
            if alert.get("status") != "firing":
                continue
            await self._handle_one(alert)

    async def _handle_one(self, alert: dict) -> None:
        labels = alert.get("labels", {})
        rule_id = labels.get("app_alert_rule_id")
        rule = await self._uow.alert_rules.get_by_id(rule_id) if rule_id else None
        if rule is None:
            logger.warning("loki webhook: no alert_rules row for app_alert_rule_id=%s", rule_id)
            return

        fingerprint = alert.get("fingerprint")
        if fingerprint and await self._uow.incidents.get_open_by_correlation_id(fingerprint):
            return

        environment = await self._projects_api.get_environment_by_id(rule.environment_id)
        title = (alert.get("annotations", {}).get("summary") or labels.get("alertname") or "Loki alert")[
            : AlertingLimits.MAX_TITLE_LENGTH
        ]
        incident = await self._uow.incidents.create(
            project_id=environment.project_id, environment_id=rule.environment_id, alert_rule_id=rule.id,
            source=IncidentSource.LOKI, category=IncidentCategory.LOG_MATCH, severity=rule.severity,
            title=title, alert_correlation_id=fingerprint,
        )
        await self._uow.commit()
        await self._audit_api.log_event(
            type=AuditEventType.INCIDENT_DETECTION, source=AuditSource.LOKI,
            action=AlertingAuditActions.INCIDENT_DETECTED, severity=AuditSeverity.HIGH,
            message=title, actor=_SYSTEM_ACTOR, project_id=incident.project_id,
            environment_id=incident.environment_id, incident_id=str(incident.id),
        )
        for channel_id in await self._uow.alert_rules.list_channel_ids(rule.id):
            try:
                await self._notifications_api.dispatch(channel_id, title)
                status = "sent"
            except Exception:  # noqa: BLE001 -- same Decision #7 reasoning as the Cloudflare path
                logger.warning("notification dispatch failed for channel %s", channel_id, exc_info=True)
                status = "failed"
            await self._audit_api.log_event(
                type=AuditEventType.NOTIFICATION_SENT, source=AuditSource.SYSTEM,
                action=AlertingAuditActions.INCIDENT_NOTIFICATION_SENT, severity=AuditSeverity.INFO,
                message=f"Notification {status} for channel {channel_id}", actor=_SYSTEM_ACTOR,
                incident_id=str(incident.id),
            )
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && uv run pytest tests/observability/test_services.py -v -k "HandleCloudflareWebhook or HandleLokiWebhook"`
Expected: PASS, all cases including the two negative-path tests (END event, unmatched policy_id) and the dedup + notification-failure-isolation tests.

- [ ] **Step 5: Write the equivalent `TestHandleLokiWebhook` class** (firing/resolved filtering, fingerprint dedup, missing-label skip) mirroring the structure above — same shape, different join field.

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/observability/services/{handle_cloudflare_webhook,handle_loki_webhook}.py backend/tests/observability/test_services.py
git commit -m "feat(observability): add Cloudflare and Loki/Alertmanager webhook handlers"
```

---

## Task 12: `observability/services/` — manual incidents, acknowledge, resolve, list/get

**Files:**
- Create: `backend/app/modules/observability/services/{create_manual_incident,acknowledge_incident,resolve_incident,list_incidents,get_incident}.py`
- Test: `backend/tests/observability/test_services.py`

**Interfaces:**
- Produces: `CreateManualIncident.execute(**CreateManualIncidentRequest fields, actor) -> IncidentRead`, `AcknowledgeIncident.execute(incident_id, actor) -> IncidentRead`, `ResolveIncident.execute(incident_id, actor) -> IncidentRead`, `ListIncidents.execute(project_id=None, environment_id=None, status=None, limit, offset) -> tuple[list[IncidentRead], int]`, `GetIncident.execute(incident_id) -> IncidentRead`.
- Consumes: `IncidentRules.validate_transition`, `AbstractObservabilityUnitOfWork.incidents`, `ProjectsApi.get_environment_by_id`, `AuditApi`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/observability/test_services.py — append
class TestAcknowledgeIncident:
    async def test_open_to_acknowledged_succeeds(self) -> None:
        uow = FakeObservabilityUnitOfWork()
        incident = await uow.incidents.create(project_id=uuid4(), environment_id=uuid4(), alert_rule_id=None,
                                               source=IncidentSource.MANUAL, category=IncidentCategory.MANUAL,
                                               severity=AlertSeverity.LOW, title="t")
        use_case = AcknowledgeIncident(uow, audit_api=FakeAuditApi())
        result = await use_case.execute(incident.id, actor=_actor())
        assert result.status == IncidentStatus.ACKNOWLEDGED
        assert result.acknowledged_by == ACTOR_ID

    async def test_resolved_incident_rejects_reacknowledge(self) -> None:
        uow = FakeObservabilityUnitOfWork()
        incident = await uow.incidents.create(project_id=uuid4(), environment_id=uuid4(), alert_rule_id=None,
                                               source=IncidentSource.MANUAL, category=IncidentCategory.MANUAL,
                                               severity=AlertSeverity.LOW, title="t")
        await uow.incidents.update_status(incident.id, status=IncidentStatus.RESOLVED, actor_id=ACTOR_ID, at=...)
        use_case = AcknowledgeIncident(uow, audit_api=FakeAuditApi())
        with pytest.raises(InvalidIncidentTransition):
            await use_case.execute(incident.id, actor=_actor())


class TestResolveIncident:
    async def test_open_to_resolved_skips_acknowledge(self) -> None:
        uow = FakeObservabilityUnitOfWork()
        incident = await uow.incidents.create(project_id=uuid4(), environment_id=uuid4(), alert_rule_id=None,
                                               source=IncidentSource.MANUAL, category=IncidentCategory.MANUAL,
                                               severity=AlertSeverity.LOW, title="t")
        use_case = ResolveIncident(uow, audit_api=FakeAuditApi())
        result = await use_case.execute(incident.id, actor=_actor())
        assert result.status == IncidentStatus.RESOLVED
        assert result.resolved_by == ACTOR_ID


class TestCreateManualIncident:
    async def test_creates_with_source_manual_and_null_alert_rule(self) -> None:
        env_id, project_id = uuid4(), uuid4()
        use_case = CreateManualIncident(
            FakeObservabilityUnitOfWork(), projects_api=FakeProjectsApi(environments={env_id: SimpleNamespace(project_id=project_id)}),
            audit_api=FakeAuditApi(),
        )
        result = await use_case.execute(
            environment_id=env_id, category=IncidentCategory.TRAFFIC, severity=AlertSeverity.MEDIUM,
            title="Manually filed", actor=_actor(),
        )
        assert result.source == IncidentSource.MANUAL
        assert result.alert_rule_id is None
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && uv run pytest tests/observability/test_services.py -v -k "AcknowledgeIncident or ResolveIncident or CreateManualIncident"`
Expected: `ImportError`.

- [ ] **Step 3: Implement**

```python
# backend/app/modules/observability/services/acknowledge_incident.py (new)
from datetime import UTC, datetime
from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.observability.constants import AlertingAuditActions, IncidentStatus
from app.modules.observability.exceptions import IncidentNotFound
from app.modules.observability.rules import IncidentRules
from app.modules.observability.schemas import IncidentRead
from app.modules.observability.uow import AbstractObservabilityUnitOfWork
from app.modules.users.public import UserRead


class AcknowledgeIncident(AbstractUseCase):
    def __init__(self, uow: AbstractObservabilityUnitOfWork, *, audit_api: AuditApi) -> None:
        self._uow = uow
        self._audit_api = audit_api

    @use_case
    async def execute(self, incident_id: UUID, *, actor: UserRead) -> IncidentRead:
        incident = await self._uow.incidents.get_by_id(incident_id)
        if incident is None:
            raise IncidentNotFound()
        IncidentRules.validate_transition(incident.status, IncidentStatus.ACKNOWLEDGED)
        result = await self._uow.incidents.update_status(
            incident_id, status=IncidentStatus.ACKNOWLEDGED, actor_id=actor.id, at=datetime.now(UTC)
        )
        await self._uow.commit()
        await self._audit_api.log_event(
            type=AuditEventType.AUDIT, source=AuditSource.USER_ACTION,
            action=AlertingAuditActions.INCIDENT_ACKNOWLEDGED, severity=AuditSeverity.INFO,
            message=f"Incident '{incident.title}' acknowledged", actor=AuditActor(user_id=actor.id, email=actor.email),
            project_id=incident.project_id, environment_id=incident.environment_id, incident_id=str(incident_id),
        )
        return result
```

(`resolve_incident.py` is identical with `IncidentStatus.RESOLVED`/`INCIDENT_RESOLVED`; `create_manual_incident.py` mirrors `CreateAlertRule`'s environment-resolution + audit shape with `source=IncidentSource.MANUAL`, `alert_rule_id=None`; `list_incidents.py`/`get_incident.py` are thin pass-throughs to the repository, mirroring `ListDnsRecords`/`GetLokiConfig`'s existing shape exactly.)

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && uv run pytest tests/observability/test_services.py -v`
Expected: PASS — full file green.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/observability/services/{create_manual_incident,acknowledge_incident,resolve_incident,list_incidents,get_incident}.py backend/tests/observability/test_services.py
git commit -m "feat(observability): add manual incident creation, acknowledge, resolve services"
```

---

## Task 13: `observability/dependencies.py` provider wiring + `observability/router.py` — 12 routes

**Files:**
- Modify: `backend/app/modules/observability/dependencies.py`, `router.py`
- Test: `backend/tests/observability/test_router.py`

**Interfaces:**
- Produces: provider functions for every Task 10/11/12 use case; 12 new routes (exact final list confirmed against `router.routes` during implementation, per this session's own established counting-risk caution).

- [ ] **Step 1: Write the failing router tests** (the two webhook auth checks are the highest-value coverage — everything else follows the exact `_login_with_permissions` pattern already used by every prior phase's router tests)

```python
# backend/tests/observability/test_router.py — append
class TestCloudflareWebhookAuth:
    async def test_wrong_secret_returns_401_and_creates_nothing(self, client: AsyncClient, engine: AsyncEngine) -> None:
        account_id = uuid4()
        # seed a cloudflare_accounts row with a known webhook secret via direct DB insert or a real create-account flow
        response = await client.post(
            f"/api/v1/webhooks/cloudflare-alert/{account_id}",
            json={"policy_id": "p", "alert_event": "ALERT_STATE_EVENT_START"},
            headers={"cf-webhook-auth": "wrong-secret"},
        )
        assert response.status_code == 401

    async def test_correct_secret_returns_200(self, client: AsyncClient, engine: AsyncEngine) -> None:
        # full setup: create project/environment/cloudflare account bound to environment,
        # register a webhook secret (via ensure_webhook_destination through a real create_alert_rule
        # call, faked CloudflareClient), then POST the matching secret
        ...
        assert response.status_code == 200


class TestLokiWebhookAuth:
    async def test_wrong_bearer_returns_401(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/v1/webhooks/loki-alert", json={"alerts": []}, headers={"Authorization": "Bearer wrong"}
        )
        assert response.status_code == 401


class TestAcknowledgeIncidentRoute:
    async def test_requires_acknowledge_permission(self, client: AsyncClient, engine: AsyncEngine) -> None:
        await _login_with_permissions(client, engine, permissions=[])
        response = await client.post(f"/api/v1/incidents/{uuid4()}/acknowledge")
        assert response.status_code == 403
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && uv run pytest tests/observability/test_router.py -v -k "WebhookAuth or AcknowledgeIncidentRoute"`
Expected: 404s (routes don't exist yet), not the expected 401/403.

- [ ] **Step 3: Implement**

```python
# backend/app/modules/observability/dependencies.py — add providers for every new use case,
# following the exact Depends-chain shape already used for get_create_loki_config etc.:
async def get_list_available_alerts(...) -> ListAvailableAlerts: ...
async def get_create_alert_rule(
    uow: AbstractObservabilityUnitOfWork = Depends(get_uow),
    cloudflare_api: CloudflareApi = Depends(get_cloudflare_api),
    loki_client: LokiClient = Depends(get_loki_client),
    projects_api: ProjectsApi = Depends(get_projects_api),
    audit_api: AuditApi = Depends(get_audit_api),
) -> CreateAlertRule:
    return CreateAlertRule(uow, cloudflare_api=cloudflare_api, loki_client=loki_client, projects_api=projects_api, audit_api=audit_api)
# ... update/delete/list_alert_rules follow the same shape
async def get_handle_cloudflare_webhook(
    uow: AbstractObservabilityUnitOfWork = Depends(get_uow),
    notifications_api: NotificationsApi = Depends(get_notifications_api),
    projects_api: ProjectsApi = Depends(get_projects_api),
    audit_api: AuditApi = Depends(get_audit_api),
) -> HandleCloudflareWebhook:
    return HandleCloudflareWebhook(uow, notifications_api=notifications_api, projects_api=projects_api, audit_api=audit_api)
# ... handle_loki_webhook, create_manual_incident, acknowledge/resolve/list/get_incident follow the same shape
```

```python
# backend/app/modules/observability/router.py — add
from app.modules.observability.dependencies import verify_cloudflare_webhook_secret, verify_loki_webhook_secret

@router.get("/cloudflare-accounts/{account_id}/available-alerts")
async def list_available_alerts(
    account_id: UUID, use_case: ListAvailableAlerts = Depends(get_list_available_alerts),
    _grant=Depends(require_account_access(AccessLevel.VIEWER)),  # reuses cloudflare's 2-layer dependency directly
    _user: UserRead = Depends(require_permission(RbacResources.ALERT_RULE, RbacActions.READ)),
) -> ApiResponse[list[AvailableAlertOption]]:
    return ApiResponse(success=True, data=await use_case.execute(account_id))


@router.post("/environments/{environment_id}/alert-rules")
async def create_alert_rule(
    environment_id: UUID, body: AlertRuleCreate, use_case: CreateAlertRule = Depends(get_create_alert_rule),
    user: UserRead = Depends(require_permission(RbacResources.ALERT_RULE, RbacActions.CREATE)),
) -> ApiResponse[AlertRuleRead]:
    result = await use_case.execute(environment_id=environment_id, **body.model_dump(), actor=user)
    return ApiResponse(success=True, data=result)


@router.get("/environments/{environment_id}/alert-rules")
async def list_alert_rules(
    environment_id: UUID, use_case: ListAlertRules = Depends(get_list_alert_rules),
    _user: UserRead = Depends(require_permission(RbacResources.ALERT_RULE, RbacActions.READ)),
) -> ApiResponse[list[AlertRuleRead]]:
    return ApiResponse(success=True, data=await use_case.execute(environment_id))


@router.patch("/alert-rules/{alert_rule_id}")
async def update_alert_rule(
    alert_rule_id: UUID, body: AlertRuleUpdate, use_case: UpdateAlertRule = Depends(get_update_alert_rule),
    user: UserRead = Depends(require_permission(RbacResources.ALERT_RULE, RbacActions.UPDATE)),
) -> ApiResponse[AlertRuleRead]:
    result = await use_case.execute(alert_rule_id, **body.model_dump(exclude_unset=True), actor=user)
    return ApiResponse(success=True, data=result)


@router.delete("/alert-rules/{alert_rule_id}")
async def delete_alert_rule(
    alert_rule_id: UUID, use_case: DeleteAlertRule = Depends(get_delete_alert_rule),
    user: UserRead = Depends(require_permission(RbacResources.ALERT_RULE, RbacActions.DELETE)),
) -> ApiResponse[None]:
    await use_case.execute(alert_rule_id, actor=user)
    return ApiResponse(success=True, data=None)


@router.get("/incidents")
async def list_incidents(
    project_id: UUID | None = Query(default=None, alias="projectId"),
    environment_id: UUID | None = Query(default=None, alias="environmentId"),
    status: IncidentStatus | None = Query(default=None),
    use_case: ListIncidents = Depends(get_list_incidents),
    _user: UserRead = Depends(require_permission(RbacResources.INCIDENT, RbacActions.READ)),
) -> ApiResponse[list[IncidentRead]]:
    items, _total = await use_case.execute(project_id=project_id, environment_id=environment_id, status=status, limit=50, offset=0)
    return ApiResponse(success=True, data=items)


@router.get("/incidents/{incident_id}")
async def get_incident(
    incident_id: UUID, use_case: GetIncident = Depends(get_get_incident),
    _user: UserRead = Depends(require_permission(RbacResources.INCIDENT, RbacActions.READ)),
) -> ApiResponse[IncidentRead]:
    return ApiResponse(success=True, data=await use_case.execute(incident_id))


@router.post("/incidents")
async def create_manual_incident(
    body: CreateManualIncidentRequest, use_case: CreateManualIncident = Depends(get_create_manual_incident),
    user: UserRead = Depends(require_permission(RbacResources.INCIDENT, RbacActions.CREATE)),
) -> ApiResponse[IncidentRead]:
    result = await use_case.execute(**body.model_dump(), actor=user)
    return ApiResponse(success=True, data=result)


@router.post("/incidents/{incident_id}/acknowledge")
async def acknowledge_incident(
    incident_id: UUID, use_case: AcknowledgeIncident = Depends(get_acknowledge_incident),
    user: UserRead = Depends(require_permission(RbacResources.INCIDENT, RbacActions.ACKNOWLEDGE)),
) -> ApiResponse[IncidentRead]:
    return ApiResponse(success=True, data=await use_case.execute(incident_id, actor=user))


@router.post("/incidents/{incident_id}/resolve")
async def resolve_incident(
    incident_id: UUID, use_case: ResolveIncident = Depends(get_resolve_incident),
    user: UserRead = Depends(require_permission(RbacResources.INCIDENT, RbacActions.RESOLVE)),
) -> ApiResponse[IncidentRead]:
    return ApiResponse(success=True, data=await use_case.execute(incident_id, actor=user))


@router.post("/webhooks/cloudflare-alert/{cloudflare_account_id}")
async def cloudflare_alert_webhook(
    cloudflare_account_id: UUID, payload: dict,
    use_case: HandleCloudflareWebhook = Depends(get_handle_cloudflare_webhook),
    _verified=Depends(verify_cloudflare_webhook_secret),
) -> ApiResponse[None]:
    await use_case.execute(cloudflare_account_id=cloudflare_account_id, payload=payload)
    return ApiResponse(success=True, data=None)


@router.post("/webhooks/loki-alert")
async def loki_alert_webhook(
    payload: dict, use_case: HandleLokiWebhook = Depends(get_handle_loki_webhook),
    _verified=Depends(verify_loki_webhook_secret),
) -> ApiResponse[None]:
    await use_case.execute(payload=payload)
    return ApiResponse(success=True, data=None)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && uv run pytest tests/observability/test_router.py -v`
Expected: PASS, including both webhook 401 checks and the full Phase 9 demo script as an integration test (create CF-native rule → simulate a matching webhook payload → incident OPEN → acknowledge → resolve).

- [ ] **Step 5: Write the remaining router integration tests** (permission-gating for every route, the full create→ack→resolve happy path, a sub-permission 403 on each write route) — same `_login_with_permissions` pattern as every prior phase.

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/observability/{dependencies,router}.py backend/tests/observability/test_router.py
git commit -m "feat(observability): add alert-rule and incident router endpoints, wire webhook routes"
```

---

## Task 14: Full backend verification pass

**Files:** none (verification only)

- [ ] **Step 1: Run the full backend gate**

```bash
cd backend
ruff check
ruff format --check
python scripts/check_module_boundaries.py --strict
uv run lint-imports
uv run pytest -q
```

Expected: all green. `lint-imports` should report **11/11 contracts kept** (same count as before — this phase only widens two existing contracts' `source_modules`, adds no new contract, since Phase 9's code lives inside `observability`, not a new module). Confirm the pytest count grew by roughly 60-80 new tests (Tasks 1, 3, 4, 5, 6, 8, 9, 10, 11, 12, 13 each added several) with zero regressions in the pre-existing suite.

- [ ] **Step 2: Confirm no unexpected diff**

```bash
git diff develop...HEAD --stat -- backend | tail -5
```

Expected: every touched file traces back to a Decision in the Detailed Plan; no accidental edits to files outside `observability`, `cloudflare`, `notifications`, `rbac`, `.importlinter`, alembic, or the two new integration client files.

- [ ] **Step 3: Commit** (only if Step 1/2 required fixes; otherwise this task is a pure gate, nothing to commit)

---

## Task 15: Frontend — `shared/constants/{permissions,api,routes}.ts` additions

**Files:**
- Modify: `frontend/src/shared/constants/permissions.ts`, `api.ts`, `routes.ts`

**Interfaces:**
- Produces: `RESOURCES.ALERT_RULE`/`.INCIDENT`, `ACTIONS.ACKNOWLEDGE`/`.RESOLVE`, `PERMISSIONS.ALERT_RULE`/`.INCIDENT`, `API_CONFIG.ENDPOINTS.ALERT_RULES`/`.INCIDENTS`, `ROUTES.adminIncidents`.

- [ ] **Step 1: Implement** (mechanical additions, mirroring `NOTIFICATION_CHANNEL`'s exact shape from Phase 8 — no new test needed, covered by the tsc/lint gate in Task 20)

```typescript
// frontend/src/shared/constants/permissions.ts
export const RESOURCES = {
  // ...existing entries
  ALERT_RULE: "alert_rule",
  INCIDENT: "incident",
} as const;

export const ACTIONS = {
  // ...existing entries
  ACKNOWLEDGE: "acknowledge",
  RESOLVE: "resolve",
} as const;

export const PERMISSIONS = {
  // ...existing entries
  ALERT_RULE: {
    RESOURCE: RESOURCES.ALERT_RULE,
    CREATE: `${RESOURCES.ALERT_RULE}.${ACTIONS.CREATE}` as const,
    READ: `${RESOURCES.ALERT_RULE}.${ACTIONS.READ}` as const,
    UPDATE: `${RESOURCES.ALERT_RULE}.${ACTIONS.UPDATE}` as const,
    DELETE: `${RESOURCES.ALERT_RULE}.${ACTIONS.DELETE}` as const,
  },
  INCIDENT: {
    RESOURCE: RESOURCES.INCIDENT,
    CREATE: `${RESOURCES.INCIDENT}.${ACTIONS.CREATE}` as const,
    READ: `${RESOURCES.INCIDENT}.${ACTIONS.READ}` as const,
    ACKNOWLEDGE: `${RESOURCES.INCIDENT}.${ACTIONS.ACKNOWLEDGE}` as const,
    RESOLVE: `${RESOURCES.INCIDENT}.${ACTIONS.RESOLVE}` as const,
  },
} as const;
```

```typescript
// frontend/src/shared/constants/api.ts — add to API_CONFIG.ENDPOINTS
  ALERT_RULES: {
    AVAILABLE_ALERTS: (accountId: string) => `/cloudflare-accounts/${accountId}/available-alerts`,
    ROOT: (environmentId: string) => `/environments/${environmentId}/alert-rules`,
    DETAIL: (alertRuleId: string) => `/alert-rules/${alertRuleId}`,
  },
  INCIDENTS: {
    ROOT: "/incidents",
    DETAIL: (id: string) => `/incidents/${id}`,
    ACKNOWLEDGE: (id: string) => `/incidents/${id}/acknowledge`,
    RESOLVE: (id: string) => `/incidents/${id}/resolve`,
  },
```

```typescript
// frontend/src/shared/constants/routes.ts
export const ROUTES = {
  // ...existing entries
  adminIncidents: "/admin/incidents",
} as const;
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/shared/constants/{permissions,api,routes}.ts
git commit -m "feat(alerting): add ALERT_RULE/INCIDENT permission, endpoint, and route constants"
```

---

## Task 16: Frontend — `entities/incident/`

**Files:**
- Create: `frontend/src/entities/incident/model/schema.ts`, `api/fetchers.ts`, `api/query-keys.ts`, `hooks/use-incidents.ts`, `index.ts`

**Interfaces:**
- Produces: `INCIDENT_STATUS`, `INCIDENT_SOURCE`, `INCIDENT_CATEGORY` (typed constant objects, per this session's own system-wide refactor convention — no raw string literals from day one), `incidentSchema`, `fetchIncidents`, `fetchIncident`, `incidentsKeys`, `useIncidentsQuery`, `useIncidentQuery`.

- [ ] **Step 1: Implement**

```typescript
// frontend/src/entities/incident/model/schema.ts
import { z } from "zod";

export const INCIDENT_SOURCE = { CLOUDFLARE: "CLOUDFLARE", LOKI: "LOKI", MANUAL: "MANUAL" } as const;
export type IncidentSource = (typeof INCIDENT_SOURCE)[keyof typeof INCIDENT_SOURCE];

export const INCIDENT_CATEGORY = {
  TRAFFIC: "TRAFFIC", DDOS: "DDOS", ORIGIN_ERROR: "ORIGIN_ERROR", DNS_DRIFT: "DNS_DRIFT",
  TUNNEL_DRIFT: "TUNNEL_DRIFT", LOG_MATCH: "LOG_MATCH", MANUAL: "MANUAL",
} as const;
export type IncidentCategory = (typeof INCIDENT_CATEGORY)[keyof typeof INCIDENT_CATEGORY];

export const ALERT_SEVERITY = { LOW: "LOW", MEDIUM: "MEDIUM", HIGH: "HIGH", CRITICAL: "CRITICAL" } as const;
export type AlertSeverity = (typeof ALERT_SEVERITY)[keyof typeof ALERT_SEVERITY];

export const INCIDENT_STATUS = { OPEN: "OPEN", ACKNOWLEDGED: "ACKNOWLEDGED", RESOLVED: "RESOLVED" } as const;
export type IncidentStatus = (typeof INCIDENT_STATUS)[keyof typeof INCIDENT_STATUS];

export const incidentSchema = z.object({
  id: z.uuid(),
  projectId: z.uuid(),
  environmentId: z.uuid(),
  alertRuleId: z.uuid().nullable(),
  source: z.enum([INCIDENT_SOURCE.CLOUDFLARE, INCIDENT_SOURCE.LOKI, INCIDENT_SOURCE.MANUAL]),
  category: z.enum([
    INCIDENT_CATEGORY.TRAFFIC, INCIDENT_CATEGORY.DDOS, INCIDENT_CATEGORY.ORIGIN_ERROR,
    INCIDENT_CATEGORY.DNS_DRIFT, INCIDENT_CATEGORY.TUNNEL_DRIFT, INCIDENT_CATEGORY.LOG_MATCH, INCIDENT_CATEGORY.MANUAL,
  ]),
  severity: z.enum([ALERT_SEVERITY.LOW, ALERT_SEVERITY.MEDIUM, ALERT_SEVERITY.HIGH, ALERT_SEVERITY.CRITICAL]),
  status: z.enum([INCIDENT_STATUS.OPEN, INCIDENT_STATUS.ACKNOWLEDGED, INCIDENT_STATUS.RESOLVED]),
  title: z.string(),
  logRefId: z.string().nullable(),
  detectedAt: z.string(),
  acknowledgedAt: z.string().nullable(),
  acknowledgedBy: z.uuid().nullable(),
  resolvedAt: z.string().nullable(),
  resolvedBy: z.uuid().nullable(),
  createdAt: z.string(),
  updatedAt: z.string(),
});
export type Incident = z.infer<typeof incidentSchema>;
```

```typescript
// frontend/src/entities/incident/api/query-keys.ts
export const incidentsKeys = {
  all: ["incidents"] as const,
  list: (filters: { projectId?: string; environmentId?: string; status?: string }) =>
    [...incidentsKeys.all, "list", filters] as const,
  detail: (id: string) => [...incidentsKeys.all, "detail", id] as const,
};
```

```typescript
// frontend/src/entities/incident/api/fetchers.ts
import { apiFetch } from "@/shared/lib/api-client";
import { API_CONFIG } from "@/shared/constants/api";
import { incidentSchema, type Incident } from "../model/schema";

export async function fetchIncidents(filters: {
  projectId?: string;
  environmentId?: string;
  status?: string;
}): Promise<Incident[]> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.INCIDENTS.ROOT, { params: filters });
  return incidentSchema.array().parse(raw);
}

export async function fetchIncident(id: string): Promise<Incident> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.INCIDENTS.DETAIL(id));
  return incidentSchema.parse(raw);
}
```

```typescript
// frontend/src/entities/incident/hooks/use-incidents.ts
"use client";
import { useQuery } from "@tanstack/react-query";
import { fetchIncident, fetchIncidents } from "../api/fetchers";
import { incidentsKeys } from "../api/query-keys";

export function useIncidentsQuery(filters: { projectId?: string; environmentId?: string; status?: string }) {
  return useQuery({ queryKey: incidentsKeys.list(filters), queryFn: () => fetchIncidents(filters) });
}

export function useIncidentQuery(id: string) {
  return useQuery({ queryKey: incidentsKeys.detail(id), queryFn: () => fetchIncident(id) });
}
```

```typescript
// frontend/src/entities/incident/index.ts
export { fetchIncidents, fetchIncident } from "./api/fetchers";
export { incidentsKeys } from "./api/query-keys";
export { useIncidentsQuery, useIncidentQuery } from "./hooks/use-incidents";
export { incidentSchema, INCIDENT_STATUS, INCIDENT_SOURCE, INCIDENT_CATEGORY, ALERT_SEVERITY } from "./model/schema";
export type { Incident, IncidentStatus, IncidentSource, IncidentCategory, AlertSeverity } from "./model/schema";
```

- [ ] **Step 2: Verify**

Run: `cd frontend && npx tsc --noEmit`
Expected: clean (no consumers wired yet, so this only checks the new files compile in isolation).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/entities/incident/
git commit -m "feat(incident): add entities layer with typed status/source/category constants"
```

---

## Task 17: Frontend — `modules/alerting/`

**Files:**
- Create: `frontend/src/modules/alerting/model/schema.ts`, `api/fetchers.ts`, `api/query-keys.ts`, `hooks/{use-alert-rules,use-create-alert-rule,use-update-alert-rule,use-delete-alert-rule}.ts`, `ui/{alert-rule-form-dialog,channel-multiselect,alerting-page-content}.tsx`, `index.ts`

**Interfaces:**
- Produces: `AlertRule`/`AvailableAlertOption` schemas; CRUD fetchers/hooks; `AlertingPageContent({ environmentId })`.
- Consumes: `@/entities/notification-channel` (channel multiselect data source), `ENVIRONMENT_TYPE` pattern precedent, `@/shared/constants/{api,permissions}`.

- [ ] **Step 1: Implement schema + fetchers + query-keys** (mirrors `modules/cloudflare-dns/model/schema.ts`'s exact shape)

```typescript
// frontend/src/modules/alerting/model/schema.ts
import { z } from "zod";

export const ALERT_RULE_SOURCE = { CLOUDFLARE_NATIVE: "CLOUDFLARE_NATIVE", LOKI_QUERY: "LOKI_QUERY" } as const;
export type AlertRuleSource = (typeof ALERT_RULE_SOURCE)[keyof typeof ALERT_RULE_SOURCE];

export const availableAlertOptionSchema = z.object({ alertType: z.string(), displayName: z.string() });
export type AvailableAlertOption = z.infer<typeof availableAlertOptionSchema>;

export const alertRuleSchema = z.object({
  id: z.uuid(),
  environmentId: z.uuid(),
  name: z.string(),
  source: z.enum([ALERT_RULE_SOURCE.CLOUDFLARE_NATIVE, ALERT_RULE_SOURCE.LOKI_QUERY]),
  cfAlertType: z.string().nullable(),
  cfPolicyId: z.string().nullable(),
  condition: z.record(z.string(), z.unknown()).nullable(),
  severity: z.enum(["LOW", "MEDIUM", "HIGH", "CRITICAL"]),
  isActive: z.boolean(),
  channelIds: z.array(z.uuid()),
  createdAt: z.string(),
  updatedAt: z.string(),
});
export type AlertRule = z.infer<typeof alertRuleSchema>;
```

```typescript
// frontend/src/modules/alerting/api/query-keys.ts
export const alertRulesKeys = {
  all: ["alert-rules"] as const,
  list: (environmentId: string) => [...alertRulesKeys.all, "list", environmentId] as const,
  availableAlerts: (accountId: string) => [...alertRulesKeys.all, "available-alerts", accountId] as const,
};
```

```typescript
// frontend/src/modules/alerting/api/fetchers.ts
import { apiFetch } from "@/shared/lib/api-client";
import { API_CONFIG } from "@/shared/constants/api";
import { alertRuleSchema, availableAlertOptionSchema, type AlertRule, type AlertRuleSource } from "./schema";

export interface AlertRuleFormValues {
  name: string;
  source: AlertRuleSource;
  cfAlertType?: string | null;
  condition?: Record<string, unknown> | null;
  severity: string;
  channelIds: string[];
}

export async function fetchAlertRules(environmentId: string): Promise<AlertRule[]> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.ALERT_RULES.ROOT(environmentId));
  return alertRuleSchema.array().parse(raw);
}

export async function fetchAvailableAlerts(accountId: string) {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.ALERT_RULES.AVAILABLE_ALERTS(accountId));
  return availableAlertOptionSchema.array().parse(raw);
}

export async function createAlertRule(environmentId: string, data: AlertRuleFormValues): Promise<AlertRule> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.ALERT_RULES.ROOT(environmentId), { method: "POST", data });
  return alertRuleSchema.parse(raw);
}

export async function updateAlertRule(
  id: string,
  data: Partial<Pick<AlertRuleFormValues, "name" | "severity" | "channelIds">> & { isActive?: boolean },
): Promise<AlertRule> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.ALERT_RULES.DETAIL(id), { method: "PATCH", data });
  return alertRuleSchema.parse(raw);
}

export async function deleteAlertRule(id: string): Promise<void> {
  await apiFetch<unknown>(API_CONFIG.ENDPOINTS.ALERT_RULES.DETAIL(id), { method: "DELETE" });
}
```

(Fix the `./schema` import path to `../model/schema` when actually placing this file — written inline here for brevity.)

- [ ] **Step 2: Implement hooks** — 4 files, exact `useMutation` + `invalidateQueries(alertRulesKeys.list(environmentId))` pattern already used by every mutation hook in `modules/cloudflare-tunnels/hooks/use-tunnels.ts` (Task's own Interfaces section above), plus one `useQuery`-based `useAlertRulesQuery`/`useAvailableAlertsQuery`.

- [ ] **Step 3: Implement `channel-multiselect.tsx`** (new UI pattern — **`ui-ux-pro-max` MUST be invoked here** per the mandatory Phase 3 rule; query it for a checkbox-list multiselect pattern before writing this file, no existing precedent in this codebase to copy)

```typescript
// frontend/src/modules/alerting/ui/channel-multiselect.tsx
"use client";
import { useTranslations } from "next-intl";
import { useNotificationChannelsQuery } from "@/entities/notification-channel";

export function ChannelMultiselect({
  projectId, selectedIds, onChange,
}: { projectId: string; selectedIds: string[]; onChange: (ids: string[]) => void }) {
  const t = useTranslations("alerting");
  const { data: channels } = useNotificationChannelsQuery(projectId);

  function toggle(id: string) {
    onChange(selectedIds.includes(id) ? selectedIds.filter((x) => x !== id) : [...selectedIds, id]);
  }

  return (
    <fieldset className="space-y-1.5">
      <legend className="text-sm font-medium text-foreground">{t("fields.channels")}</legend>
      <div className="flex flex-col gap-2 rounded-md border border-input p-3">
        {channels.length === 0 && <p className="text-sm text-muted-foreground">{t("fields.noChannels")}</p>}
        {channels.map((channel) => (
          <label key={channel.id} className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={selectedIds.includes(channel.id)}
              onChange={() => toggle(channel.id)}
              className="size-4 rounded border-input focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
            />
            <span>{channel.name}</span>
            <span className="text-xs text-muted-foreground">({channel.type})</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}
```

- [ ] **Step 4: Implement `alert-rule-form-dialog.tsx`** — source-conditional (CLOUDFLARE_NATIVE shows an `<select>` populated from `useAvailableAlertsQuery`, gated on an account being resolvable for the environment — reuse `useCloudflareConfigQuery` from `modules/cloudflare-dns` the same cross-tab-reuse way `modules/log-viewer` already does; LOKI_QUERY shows a LogQL textarea + `for` duration input), mirrors `notification-channel-form-dialog.tsx`'s `ChannelTypeFields`-style extraction to keep complexity under the ESLint max-15 rule from the start (extract `CloudflareNativeFields`/`LokiQueryFields` sub-components immediately, don't wait for a lint failure like Phase 7/8 did).

- [ ] **Step 5: Implement `alerting-page-content.tsx`** — list + create/edit/delete, mirrors `modules/cloudflare-dns/ui/cloudflare-dns-page-content.tsx`'s section+table shape.

- [ ] **Step 6: `index.ts`** — export only `AlertingPageContent`, same minimal-surface convention as every other module.

- [ ] **Step 7: Verify**

Run: `cd frontend && npx tsc --noEmit && npm run lint`
Expected: clean.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/modules/alerting/
git commit -m "feat(alerting): add alert-rule CRUD module with channel multiselect"
```

---

## Task 18: Frontend — `modules/incidents/`

**Files:**
- Create: `frontend/src/modules/incidents/api/{fetchers,query-keys}.ts`, `hooks/{use-acknowledge-incident,use-resolve-incident,use-create-manual-incident}.ts`, `ui/{incident-status-badge,incidents-page-content,incident-detail-panel}.tsx`, `index.ts`

**Interfaces:**
- Produces: `IncidentsPageContent({ projectId })`, `IncidentStatusBadge({ status })`.
- Consumes: `@/entities/incident` (schema, `useIncidentsQuery`).

- [ ] **Step 1: Implement `incident-status-badge.tsx`** — direct structural copy of `cloudflare-tunnels/ui/tunnel-status-badge.tsx` (already read in full during Phase 9's research pass), 3 states instead of 4:

```typescript
// frontend/src/modules/incidents/ui/incident-status-badge.tsx
import { AlertCircle, Eye, CheckCircle2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { INCIDENT_STATUS, type IncidentStatus } from "@/entities/incident";

const STATUS_STYLES: Record<IncidentStatus, { icon: typeof AlertCircle; className: string }> = {
  [INCIDENT_STATUS.OPEN]: { icon: AlertCircle, className: "bg-red-50 text-red-700 dark:bg-red-950/60 dark:text-red-300" },
  [INCIDENT_STATUS.ACKNOWLEDGED]: { icon: Eye, className: "bg-amber-50 text-amber-700 dark:bg-amber-950/60 dark:text-amber-300" },
  [INCIDENT_STATUS.RESOLVED]: { icon: CheckCircle2, className: "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300" },
};

export function IncidentStatusBadge({ status }: { status: IncidentStatus }) {
  const t = useTranslations("incidents");
  const { icon: Icon, className } = STATUS_STYLES[status];
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ${className}`}>
      <Icon className="size-3" aria-hidden="true" />
      {t(`status.${status}`)}
    </span>
  );
}
```

- [ ] **Step 2: Implement fetchers/query-keys/hooks** — `fetchAlertAcknowledge`/`fetchAlertResolve` POST fetchers, mutation hooks invalidating `incidentsKeys.list`/`incidentsKeys.detail`, same shape as `use-tunnels.ts`.

- [ ] **Step 3: Implement `incidents-page-content.tsx`** — **`ui-ux-pro-max` MUST be invoked here** (dashboard list + filter + select-row-to-see-detail pattern) before writing; mirrors `cloudflare-tunnels-page-content.tsx`'s selected-row-highlights-then-shows-detail-panel-below shape, filter controls for `status`/`environmentId` mirroring `audit-log-page-content.tsx`'s filter-bar pattern.

- [ ] **Step 4: Implement `incident-detail-panel.tsx`** — acknowledge/resolve buttons gated `<Can I={ACTIONS.ACKNOWLEDGE} a={PERMISSIONS.INCIDENT.RESOURCE}>`/`<Can I={ACTIONS.RESOLVE} ...>`, disabled once already RESOLVED. Resolve is a positive terminal action, not `ConfirmDialog`'s `variant="destructive"` — **query `ui-ux-pro-max` for the right visual treatment** (Decision from the Detailed Plan's Skills Applied section) rather than defaulting to a destructive-red button for a "closing out an incident" action.

- [ ] **Step 5: `index.ts`** — export only `IncidentsPageContent`.

- [ ] **Step 6: Verify**

Run: `cd frontend && npx tsc --noEmit && npm run lint`

- [ ] **Step 7: Commit**

```bash
git add frontend/src/modules/incidents/
git commit -m "feat(incidents): add incidents dashboard module with status badge and ack/resolve actions"
```

---

## Task 19: Frontend — routes, sidebar, i18n wiring

**Files:**
- Create: `frontend/src/app/[locale]/(dashboard)/admin/environments/[environmentId]/alerting/{page,loading}.tsx`
- Create: `frontend/src/app/[locale]/(dashboard)/admin/incidents/{page,loading}.tsx`
- Modify: `frontend/src/modules/projects/ui/project-detail-view.tsx` (new "Alerting" chip icon-button, mirrors the existing DNS/Tunnels/Logs chip affordances exactly)
- Modify: `frontend/src/app/[locale]/(dashboard)/dashboard-sidebar.tsx` (new "Incidents" top-level nav item, gated `incident:read` — incidents span environments the same way audit-log does)
- Create: `frontend/locales/{en,vi}/modules/{alerting,incidents}.json`
- Modify: `frontend/src/shared/lib/i18n/request.ts`

**Interfaces:**
- Consumes: the exact SSR-prefetch-environment-only route pattern already used by `admin/environments/[environmentId]/dns/page.tsx`.

- [ ] **Step 1: Alert-rule route** — Server Component, SSR-prefetches only the environment read, guarded `hasPermission(session, RESOURCES.ALERT_RULE, ACTIONS.READ)`, same shape as the DNS/logs routes exactly.

- [ ] **Step 2: Incidents dashboard route** — project-scoped (reads `?projectId=` search param or is nested under `admin/projects/[projectId]/incidents` — decide during implementation by checking whether the existing audit-log page is project-scoped-via-filter or its own flat route; mirror whichever precedent that page actually uses, since incidents' "list open incidents for project X" query shape is functionally identical to audit-log's own filtering need).

- [ ] **Step 3: `project-detail-view.tsx`** — add one new environment-chip icon-button (`Siren` or `Bell`-adjacent `lucide-react` icon, distinct from the existing `Globe`/`Waypoints`/`ScrollText`), gated `<Can I={ACTIONS.READ} a={RESOURCES.ALERT_RULE}>`, linking to the new alerting route — same pattern as every prior phase's chip addition.

- [ ] **Step 4: `dashboard-sidebar.tsx`** — add one `navItems` entry (`href: ROUTES.adminIncidents, icon: Siren, permission: {action: ACTIONS.READ, resource: RESOURCES.INCIDENT}`), same shape as the existing 6 entries.

- [ ] **Step 5: i18n** — `alerting.json`/`incidents.json` (en+vi) covering every `t(...)` key referenced in Tasks 17/18's components (`section.title`, `fields.*`, `status.{OPEN,ACKNOWLEDGED,RESOLVED}`, `actions.{acknowledge,resolve,create,edit,delete}`, `errors.*` mirroring the backend `ErrorCode` members from Task 1 exactly, same `useApiErrorMessage(moduleNamespace)` convention as every prior phase). Register both in `request.ts`'s `Promise.all` + destructuring, following the exact pattern already used for `notifications.json`.

- [ ] **Step 6: Verify**

Run: `cd frontend && npx tsc --noEmit && npm run lint && npx vitest run && npm run build`
Expected: clean; `npm run build`'s route list includes the 2 new routes.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app frontend/src/modules/projects/ui/project-detail-view.tsx frontend/src/app/'[locale]'/'(dashboard)'/dashboard-sidebar.tsx frontend/locales frontend/src/shared/lib/i18n/request.ts
git commit -m "feat(alerting): wire alerting and incidents routes, sidebar nav, and i18n"
```

---

## Task 20: Full frontend verification pass

**Files:** none (verification only)

- [ ] **Step 1: Run the full frontend gate**

```bash
cd frontend
npx tsc --noEmit
npm run lint
npx vitest run
npm run build
```

Expected: all green — tsc clean, lint clean (only the pre-existing `[boundaries]` plugin deprecation warnings), vitest passing with the same count as before (no new unit tests added this phase beyond what Task 16/17/18 explicitly wrote, if any — consistent with every prior UI-only task in this session), build succeeds with both new routes registered in the printed route table.

- [ ] **Step 2: Manual UI smoke test** (start the dev server, exercise the golden path per the "For UI or frontend changes" rule in this repo's own AGENTS.md)

Run: `cd frontend && npm run dev`, then manually: open an environment's new Alerting chip → create a Cloudflare-native rule (requires a real bound Cloudflare account + a real token scoped with `Notifications Write`, same disclosed external-dependency limitation as every prior Cloudflare-touching phase) → open the Incidents dashboard → confirm the empty state renders cleanly with no bound data yet.

- [ ] **Step 3: Commit** (only if fixes were needed)

---

## Task 21: GitNexus reindex, skills review, finish branch

**Files:** none

- [ ] **Step 1: GitNexus**

```bash
node .gitnexus/run.cjs analyze
```
If FTS corruption recurs (seen twice earlier this session): `node .gitnexus/run.cjs clean --force && npx gitnexus analyze`.

- [ ] **Step 2: Manual diff review in place of `detect_changes`/`check` MCP tools** (not exposed this session, per every prior phase's own disclosure)

```bash
git diff develop...feature/alerting-incidents --stat
```
Confirm every touched file traces to a Decision in the Detailed Plan section; no stray files.

- [ ] **Step 3: `reviewing-code-against-skills` checklist** — walk the full Phase 4 checklist from AGENTS.md/CLAUDE.md (module boundaries, no proxy re-exports, no hardcoded literals, SSR prefetch guards, `ui-ux-pro-max` actually invoked for `channel-multiselect.tsx`/`incidents-page-content.tsx`/`incident-detail-panel.tsx`, class-scoped constants, router thinness, no hardcoded secrets, sufficient error handling, tests pass, no junk files in the diff). Fix loop (max 2 rounds) on anything that fails.

- [ ] **Step 4: `finishing-a-development-branch` skill** — verify the full test suite one more time on the branch tip, then present the standard 3-option menu (merge locally / push+PR / keep as-is) and wait for the user's choice before merging, exactly as every prior phase in this session.





