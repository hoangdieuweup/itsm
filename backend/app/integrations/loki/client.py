"""Loki HTTP API client. HTTP only — no database, no business logic. Lives
here (not app/modules/observability/) mirroring the same integration/module
split app/integrations/cloudflare/ already established in this repo."""

import json
from collections.abc import AsyncIterator
from datetime import datetime
from urllib.parse import quote

import httpx
import websockets
from websockets.exceptions import InvalidStatus, WebSocketException

from app.core.base.markers import integration
from app.integrations.loki.config import loki_settings
from app.integrations.loki.exceptions import InvalidLokiCredential, LokiApiUnavailable, LokiQueryRejected
from app.integrations.loki.schemas import LokiLogEntry, LokiQueryResult


class LokiClient:
    """Talks to a Loki HTTP API. One instance per request, built in
    dependencies.py. `transport` is injectable only for tests — production
    code always constructs LokiClient() with no arguments. Unlike
    CloudflareClient, endpoint_url is a per-call argument, not a settings
    base URL, since every environment can point at a different cluster."""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    @integration
    async def query_range(
        self,
        *,
        endpoint_url: str,
        query: str,
        start: datetime,
        end: datetime,
        tenant_id: str | None,
        auth_header: str | None,
        limit: int = 200,
    ) -> LokiQueryResult:
        """GET {endpoint_url}/loki/api/v1/query_range. start/end sent as Unix
        nanosecond timestamps (Loki's canonical format). auth_header is the
        fully-built header value ("Basic <b64>" / "Bearer <token>" / None) —
        built by the caller, keeping this client ignorant of auth_type as a
        concept. Flattens every stream's values into one chronologically
        sorted list — display-only data, unlike Cloudflare's tunnel-ingress
        writes, so flattening (not raw-JSON preservation) is correct here."""
        headers = {}
        if auth_header is not None:
            headers["Authorization"] = auth_header
        if tenant_id is not None:
            headers["X-Scope-OrgID"] = tenant_id

        params = {
            "query": query,
            "start": str(int(start.timestamp() * 1_000_000_000)),
            "end": str(int(end.timestamp() * 1_000_000_000)),
            "limit": limit,
        }

        try:
            async with httpx.AsyncClient(base_url=endpoint_url, transport=self._transport) as client:
                response = await client.get(
                    "/loki/api/v1/query_range",
                    params=params,
                    headers=headers,
                    timeout=loki_settings.HTTP_TIMEOUT_SECONDS,
                )
        except httpx.HTTPError as exc:
            raise LokiApiUnavailable() from exc

        if response.status_code in (401, 403):
            raise InvalidLokiCredential()
        if response.status_code >= 500:
            raise LokiApiUnavailable(status_code=response.status_code)
        body = response.json()
        if response.is_error:
            raise LokiQueryRejected(message=body.get("error", "Loki rejected this query"))

        entries = [
            LokiLogEntry(timestamp=ts, line=line, labels=stream.get("stream", {}))
            for stream in body.get("data", {}).get("result", [])
            for ts, line in stream.get("values", [])
        ]
        entries.sort(key=lambda e: e.timestamp)
        return LokiQueryResult(entries=entries)

    @integration
    async def tail(
        self,
        *,
        endpoint_url: str,
        query: str,
        tenant_id: str | None,
        auth_header: str | None,
        limit: int = 100,
    ) -> AsyncIterator[LokiLogEntry]:
        """GET {endpoint_url}/loki/api/v1/tail — WebSocket, not HTTP; Loki's
        tail endpoint has no HTTP fallback. Converts the http(s) scheme to
        ws(s) before connecting. Starts from "now" — no start/delay_for
        params exposed. Yields entries as they arrive; never returns until
        the connection closes or the caller stops iterating."""
        ws_url = endpoint_url.replace("https://", "wss://").replace("http://", "ws://")
        query_string = f"query={quote(query)}&limit={limit}"
        uri = f"{ws_url}/loki/api/v1/tail?{query_string}"

        headers: dict[str, str] = {}
        if auth_header is not None:
            headers["Authorization"] = auth_header
        if tenant_id is not None:
            headers["X-Scope-OrgID"] = tenant_id

        try:
            async with websockets.connect(uri, additional_headers=headers) as ws:
                async for message in ws:
                    body = json.loads(message)
                    for stream in body.get("streams", []):
                        labels = stream.get("stream", {})
                        for ts, line in stream.get("values", []):
                            yield LokiLogEntry(timestamp=ts, line=line, labels=labels)
        except InvalidStatus as exc:
            if exc.response.status_code in (401, 403):
                raise InvalidLokiCredential() from exc
            raise LokiQueryRejected() from exc
        except WebSocketException as exc:
            raise LokiApiUnavailable() from exc
        except OSError as exc:
            raise LokiApiUnavailable() from exc
