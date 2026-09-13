"""Unit tests for observability's webhook-secret verification dependencies —
no I/O, pure hmac.compare_digest checks against a fake CloudflareApi / the
module's own settings singleton."""

from uuid import uuid4

import pytest

from app.modules.observability.config import observability_settings
from app.modules.observability.constants import (
    AlertRuleSource,
    AlertSeverity,
    IncidentCategory,
    IncidentSource,
)
from app.modules.observability.dependencies import (
    require_project_permission_for_alert_rule,
    require_project_permission_for_environment,
    require_project_permission_for_incident,
    verify_cloudflare_webhook_secret,
    verify_loki_webhook_secret,
)
from app.modules.observability.exceptions import InvalidWebhookSecret, ObservabilityPermissionDenied
from app.modules.users.public import UserRead
from tests.observability.test_services import FakeObservabilityUnitOfWork


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


class _FakeAuthApi:
    def __init__(self, user) -> None:
        self._user = user

    def current_user(self):
        return self._user


class _FakeEnvironment:
    def __init__(self, id, project_id) -> None:
        self.id = id
        self.project_id = project_id


class FakeProjectsApi:
    def __init__(self, environment=None, permissions: frozenset = frozenset()) -> None:
        self._environment = environment
        self._permissions = permissions

    async def get_environment_by_id(self, environment_id):
        return self._environment

    async def resolve_effective_permissions(self, project_id, user, rbac_api):
        return self._permissions


class TestRequireProjectPermissionForEnvironment:
    async def test_allows_when_resource_action_is_in_the_effective_grant(self) -> None:
        environment_id = uuid4()
        user = UserRead.model_construct(id=uuid4(), email="a@b.com", name="A")
        projects_api = FakeProjectsApi(
            environment=_FakeEnvironment(id=environment_id, project_id=uuid4()),
            permissions=frozenset({"loki_config.manage"}),
        )

        check = require_project_permission_for_environment("loki_config", "manage")
        result = await check(
            environment_id=environment_id,
            auth_api=_FakeAuthApi(user),
            rbac_api=object(),
            projects_api=projects_api,
        )

        assert result == user

    async def test_raises_when_resource_action_is_missing(self) -> None:
        environment_id = uuid4()
        user = UserRead.model_construct(id=uuid4(), email="a@b.com", name="A")
        projects_api = FakeProjectsApi(
            environment=_FakeEnvironment(id=environment_id, project_id=uuid4()), permissions=frozenset()
        )

        check = require_project_permission_for_environment("loki_config", "manage")
        with pytest.raises(ObservabilityPermissionDenied):
            await check(
                environment_id=environment_id,
                auth_api=_FakeAuthApi(user),
                rbac_api=object(),
                projects_api=projects_api,
            )


class TestRequireProjectPermissionForAlertRule:
    async def test_resolves_via_the_alert_rules_environment_then_project(self) -> None:
        uow = FakeObservabilityUnitOfWork()
        environment_id = uuid4()
        alert_rule = await uow.alert_rules.create(
            environment_id=environment_id,
            name="r1",
            source=AlertRuleSource.CLOUDFLARE_NATIVE,
            cf_alert_type="advanced_ddos_attack_l7_alert",
            condition=None,
            severity=AlertSeverity.HIGH,
        )
        user = UserRead.model_construct(id=uuid4(), email="a@b.com", name="A")
        projects_api = FakeProjectsApi(
            environment=_FakeEnvironment(id=environment_id, project_id=uuid4()),
            permissions=frozenset({"alert_rule.update"}),
        )

        check = require_project_permission_for_alert_rule("alert_rule", "update")
        result = await check(
            alert_rule_id=alert_rule.id,
            auth_api=_FakeAuthApi(user),
            rbac_api=object(),
            uow=uow,
            projects_api=projects_api,
        )

        assert result == user


class TestRequireProjectPermissionForIncident:
    async def test_resolves_via_the_incidents_own_project_id_column(self) -> None:
        uow = FakeObservabilityUnitOfWork()
        project_id = uuid4()
        incident = await uow.incidents.create(
            project_id=project_id,
            environment_id=uuid4(),
            alert_rule_id=None,
            source=IncidentSource.MANUAL,
            category=IncidentCategory.MANUAL,
            severity=AlertSeverity.LOW,
            title="t",
        )
        user = UserRead.model_construct(id=uuid4(), email="a@b.com", name="A")
        projects_api = FakeProjectsApi(permissions=frozenset({"project_incident.acknowledge"}))

        check = require_project_permission_for_incident("project_incident", "acknowledge")
        result = await check(
            incident_id=incident.id,
            auth_api=_FakeAuthApi(user),
            rbac_api=object(),
            uow=uow,
            projects_api=projects_api,
        )

        assert result == user


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
