"""Pure business rules owned by the observability module. No I/O."""

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
        """Only OPEN->ACKNOWLEDGED, OPEN->RESOLVED (skip-ack allowed), and
        ACKNOWLEDGED->RESOLVED are legal. RESOLVED is terminal — no reopen in
        this phase's scope."""
        if (current, target) not in _ALLOWED_TRANSITIONS:
            raise InvalidIncidentTransition()


class AlertingRules:
    @staticmethod
    @rule
    def category_for_cloudflare_alert_type(alert_type: str) -> IncidentCategory:
        """Falls back to TRAFFIC for anything not explicitly mapped (SSL/Access
        cert expiry, Workers alerts, and any future alert_type Cloudflare
        adds) — the closest generic fit. DNS_DRIFT/TUNNEL_DRIFT are Phase
        10's reconciliation-job territory and are never set here."""
        return _CLOUDFLARE_ALERT_TYPE_CATEGORY.get(alert_type, IncidentCategory.TRAFFIC)
