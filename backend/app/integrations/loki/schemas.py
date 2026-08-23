from app.core.models import FrozenModel


class LokiLogEntry(FrozenModel):
    timestamp: str
    line: str
    labels: dict[str, str]


class LokiQueryResult(FrozenModel):
    entries: list[LokiLogEntry]
