"""Unit tests for observability's pure rules — no I/O."""

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
        assert (
            AlertingRules.category_for_cloudflare_alert_type("advanced_ddos_attack_l4_alert")
            == IncidentCategory.DDOS
        )

    def test_ddos_l7(self) -> None:
        assert (
            AlertingRules.category_for_cloudflare_alert_type("advanced_ddos_attack_l7_alert")
            == IncidentCategory.DDOS
        )

    def test_health_check(self) -> None:
        assert (
            AlertingRules.category_for_cloudflare_alert_type("health_check_status_notification")
            == IncidentCategory.ORIGIN_ERROR
        )

    def test_unmapped_falls_back_to_traffic(self) -> None:
        assert (
            AlertingRules.category_for_cloudflare_alert_type("dedicated_ssl_certificate_event_type")
            == IncidentCategory.TRAFFIC
        )


class TestSupportsZoneFilter:
    def test_true_when_zones_key_present(self) -> None:
        filter_options = [{"Key": "zones", "ComparisonOperator": "==", "Range": "1-n"}]
        assert AlertingRules.supports_zone_filter(filter_options) is True

    def test_true_when_zones_is_one_of_several_keys(self) -> None:
        filter_options = [{"Key": "slo"}, {"Key": "zones"}]
        assert AlertingRules.supports_zone_filter(filter_options) is True

    def test_false_when_no_zones_key(self) -> None:
        assert AlertingRules.supports_zone_filter([{"Key": "slo"}]) is False

    def test_false_when_empty(self) -> None:
        assert AlertingRules.supports_zone_filter([]) is False

    def test_false_when_none(self) -> None:
        assert AlertingRules.supports_zone_filter(None) is False
