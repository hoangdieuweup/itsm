"""Pure business rules owned by the observability module. No I/O."""

from app.core.base.markers import rule
from app.modules.observability.constants import (
    CloudflareAlertTypes,
    IncidentCategory,
    IncidentStatus,
    IncidentTransitions,
)
from app.modules.observability.exceptions import InvalidIncidentTransition


class IncidentRules:
    """Pure business decisions for incident lifecycle transitions."""

    @staticmethod
    @rule
    def validate_transition(current: IncidentStatus, target: IncidentStatus) -> None:
        """Only OPEN->ACKNOWLEDGED, OPEN->RESOLVED (skip-ack allowed), and
        ACKNOWLEDGED->RESOLVED are legal. RESOLVED is terminal — no reopen in
        this phase's scope."""
        if (current, target) not in IncidentTransitions.ALLOWED:
            raise InvalidIncidentTransition()


class AlertingRules:
    """Pure mapping rules for alert types to incident categories."""

    _CLOUDFLARE_ALERT_TYPE_CATEGORY: dict[str, IncidentCategory] = {
        CloudflareAlertTypes.ADVANCED_DDOS_L4: IncidentCategory.DDOS,
        CloudflareAlertTypes.ADVANCED_DDOS_L7: IncidentCategory.DDOS,
        CloudflareAlertTypes.HEALTH_CHECK_STATUS: IncidentCategory.ORIGIN_ERROR,
    }

    @staticmethod
    @rule
    def category_for_cloudflare_alert_type(alert_type: str) -> IncidentCategory:
        """Falls back to TRAFFIC for anything not explicitly mapped (SSL/Access
        cert expiry, Workers alerts, and any future alert_type Cloudflare
        adds) — the closest generic fit. DNS_DRIFT/TUNNEL_DRIFT are Phase
        10's reconciliation-job territory and are never set here."""
        return AlertingRules._CLOUDFLARE_ALERT_TYPE_CATEGORY.get(alert_type, IncidentCategory.TRAFFIC)

    @staticmethod
    @rule
    def supports_zone_filter(filter_options: list[dict] | None) -> bool:
        """True when Cloudflare's own filter_options for this alert type
        (from GET .../available_alerts) include a "zones" key — confirmed
        against Cloudflare's real API, not every alert type supports zone
        scoping (account-wide alerts like billing or BGP hijack
        notifications have no zone concept at all, and Cloudflare rejects
        an unsupported filter key)."""
        if not filter_options:
            return False
        return any(option.get("Key") == "zones" for option in filter_options)
