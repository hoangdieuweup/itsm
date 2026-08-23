from pydantic import BaseModel


class LokiLogEntry(BaseModel):
    timestamp: str
    line: str
    labels: dict[str, str]


class LokiQueryResult(BaseModel):
    entries: list[LokiLogEntry]
