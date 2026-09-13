"""Single access path to the observability module's tables, one file per aggregate. Every class
is re-exported here so callers keep importing from app.modules.observability.repository."""

from app.modules.observability.repository.alert_rules import (
    AbstractAlertRuleRepository,
    AlertRuleRepository,
)
from app.modules.observability.repository.incidents import (
    AbstractIncidentRepository,
    IncidentRepository,
)
from app.modules.observability.repository.loki_configs import (
    AbstractLokiConfigRepository,
    LokiConfigRepository,
)

__all__ = [
    "AbstractAlertRuleRepository",
    "AbstractIncidentRepository",
    "AbstractLokiConfigRepository",
    "AlertRuleRepository",
    "IncidentRepository",
    "LokiConfigRepository",
]
