from app.integrations.loki.schemas import LokiLogEntry, LokiQueryResult


def test_loki_query_result_holds_entries_as_given():
    entries = [
        LokiLogEntry(timestamp="1700000002000000000", line="second", labels={"job": "api"}),
        LokiLogEntry(timestamp="1700000001000000000", line="first", labels={"job": "api"}),
    ]
    result = LokiQueryResult(entries=entries)
    assert [e.line for e in result.entries] == ["second", "first"]
    assert result.entries[0].labels == {"job": "api"}
