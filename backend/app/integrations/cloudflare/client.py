"""Cloudflare REST API client. HTTP only — no database, no business logic.

Lives here (not app/modules/cloudflare/) per the Netflix Dispatch convention
this repo already follows for dx_core/cache/queue/storage/mongo: any
third-party API adapter is a leaf under app/integrations/, imported by
whichever module needs it via dependency injection. app/modules/cloudflare/
owns the business domain (accounts, 2-layer ACL, DNS records, configs) and
reaches this client only through modules/cloudflare/dependencies.py.
"""

import logging
from datetime import datetime

import httpx

from app.core.base.markers import helper, integration
from app.integrations.cloudflare.config import cloudflare_settings
from app.integrations.cloudflare.exceptions import (
    CloudflareAnalyticsQueryRejected,
    CloudflareApiUnavailable,
    CloudflareDnsOperationRejected,
    InvalidCloudflareToken,
)
from app.integrations.cloudflare.schemas import (
    CloudflareTrafficBucket,
    CloudflareTrafficStats,
    CloudflareTrafficStatusCount,
    ZoneOption,
)

logger = logging.getLogger(__name__)


class CloudflareClient:
    """Talks to the Cloudflare REST API. One instance per request, built in
    dependencies.py. `transport` is injectable only for tests — production
    code always constructs CloudflareClient() with no arguments."""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    @integration
    async def test_connection(self, *, cf_account_id: str, api_token: str) -> None:
        """GET /zones?account.id=<cf_account_id>. Raises InvalidCloudflareToken
        when Cloudflare rejects the token — either via HTTP 4xx, or via an
        HTTP 200 whose v4 envelope has success=false (Cloudflare wraps every
        response in {success, errors, result} and does not always signal a
        bad/under-scoped token through HTTP status alone). Raises
        CloudflareApiUnavailable on transport failure or a 5xx response."""
        try:
            async with httpx.AsyncClient(
                base_url=str(cloudflare_settings.API_BASE_URL), transport=self._transport
            ) as client:
                response = await client.get(
                    "/zones",
                    params={"account.id": cf_account_id},
                    headers={"Authorization": f"Bearer {api_token}"},
                    timeout=cloudflare_settings.HTTP_TIMEOUT_SECONDS,
                )
        except httpx.HTTPError as exc:
            raise CloudflareApiUnavailable() from exc

        if response.status_code in (400, 401, 403):
            raise InvalidCloudflareToken()
        if response.is_error:
            raise CloudflareApiUnavailable(status_code=response.status_code)
        if not response.json().get("success", False):
            raise InvalidCloudflareToken()

    @integration
    async def list_zones(self, *, cf_account_id: str, api_token: str) -> list[ZoneOption]:
        """GET /zones?account.id=<cf_account_id>, walking every page via
        result_info.total_pages — a truncated first page would silently
        reject a valid zone during bind-time ownership verification."""
        zones: list[ZoneOption] = []
        page = 1
        async with httpx.AsyncClient(
            base_url=str(cloudflare_settings.API_BASE_URL), transport=self._transport
        ) as client:
            while True:
                try:
                    response = await client.get(
                        "/zones",
                        params={"account.id": cf_account_id, "page": page, "per_page": 50},
                        headers={"Authorization": f"Bearer {api_token}"},
                        timeout=cloudflare_settings.HTTP_TIMEOUT_SECONDS,
                    )
                except httpx.HTTPError as exc:
                    raise CloudflareApiUnavailable() from exc

                if response.status_code in (400, 401, 403):
                    raise InvalidCloudflareToken()
                if response.is_error:
                    raise CloudflareApiUnavailable(status_code=response.status_code)
                body = response.json()
                if not body.get("success", False):
                    raise InvalidCloudflareToken()

                zones.extend(ZoneOption(id=z["id"], name=z["name"]) for z in body.get("result", []))
                result_info = body.get("result_info", {})
                if page >= result_info.get("total_pages", 1):
                    break
                page += 1
        return zones

    @helper
    async def _write(
        self,
        path: str,
        method: str,
        api_token: str,
        *,
        json: dict | None = None,
        params: dict | None = None,
    ) -> dict:
        """Shared envelope-check for every write/authenticated-GET method
        below — a rejected call here means Cloudflare itself rejected the
        request (bad payload, name conflict, insufficient scope), which is a
        DIFFERENT failure mode than InvalidCloudflareToken (an auth problem
        detected before this helper is even reached, in test_connection/
        list_zones)."""
        try:
            async with httpx.AsyncClient(
                base_url=str(cloudflare_settings.API_BASE_URL), transport=self._transport
            ) as client:
                response = await client.request(
                    method,
                    path,
                    json=json,
                    params=params,
                    headers={"Authorization": f"Bearer {api_token}"},
                    timeout=cloudflare_settings.HTTP_TIMEOUT_SECONDS,
                )
        except httpx.HTTPError as exc:
            raise CloudflareApiUnavailable() from exc

        if response.status_code >= 500:
            raise CloudflareApiUnavailable(status_code=response.status_code)
        body = response.json()
        if response.is_error or not body.get("success", False):
            logger.warning(
                "Cloudflare rejected %s %s (status=%s): %s",
                method,
                path,
                response.status_code,
                body.get("errors"),
            )
            raise CloudflareDnsOperationRejected()
        return body

    @integration
    async def create_dns_record(
        self,
        *,
        zone_id: str,
        api_token: str,
        record_type: str,
        name: str,
        content: str,
        priority: int | None,
        proxied: bool,
        ttl: int,
    ) -> str:
        """POST /zones/{zone_id}/dns_records. Returns the real cf_record_id."""
        payload = {"type": record_type, "name": name, "content": content, "proxied": proxied, "ttl": ttl}
        if priority is not None:
            payload["priority"] = priority
        body = await self._write(f"/zones/{zone_id}/dns_records", "POST", api_token, json=payload)
        return body["result"]["id"]

    @integration
    async def update_dns_record(
        self,
        *,
        zone_id: str,
        cf_record_id: str,
        api_token: str,
        record_type: str,
        name: str,
        content: str,
        priority: int | None,
        proxied: bool,
        ttl: int,
    ) -> None:
        """PATCH /zones/{zone_id}/dns_records/{cf_record_id}."""
        payload = {"type": record_type, "name": name, "content": content, "proxied": proxied, "ttl": ttl}
        if priority is not None:
            payload["priority"] = priority
        await self._write(f"/zones/{zone_id}/dns_records/{cf_record_id}", "PATCH", api_token, json=payload)

    @integration
    async def delete_dns_record(self, *, zone_id: str, cf_record_id: str, api_token: str) -> None:
        """DELETE /zones/{zone_id}/dns_records/{cf_record_id}."""
        await self._write(f"/zones/{zone_id}/dns_records/{cf_record_id}", "DELETE", api_token)

    @integration
    async def create_tunnel(self, *, cf_account_id: str, api_token: str, name: str) -> str:
        """POST /accounts/{cf_account_id}/cfd_tunnel. config_src is hardcoded
        to "cloudflare" (Decision #9) — never a caller-supplied field, since
        this app must control ingress via the API, and Cloudflare's own
        reference calls "cloudflare" mandatory for that. Returns cf_tunnel_id."""
        body = await self._write(
            f"/accounts/{cf_account_id}/cfd_tunnel",
            "POST",
            api_token,
            json={"name": name, "config_src": "cloudflare"},
        )
        return body["result"]["id"]

    @integration
    async def get_tunnel_token(self, *, cf_account_id: str, cf_tunnel_id: str, api_token: str) -> str:
        """GET /accounts/{cf_account_id}/cfd_tunnel/{cf_tunnel_id}/token. Never
        cached or persisted by any caller (Decision #8) — fetched live every time."""
        body = await self._write(
            f"/accounts/{cf_account_id}/cfd_tunnel/{cf_tunnel_id}/token", "GET", api_token
        )
        return body["result"]

    @integration
    async def list_tunnel_connections(
        self, *, cf_account_id: str, cf_tunnel_id: str, api_token: str
    ) -> list[dict]:
        """GET /accounts/{cf_account_id}/cfd_tunnel/{cf_tunnel_id}/connections.
        Caller only needs len() of the result — 0 connections means DOWN."""
        body = await self._write(
            f"/accounts/{cf_account_id}/cfd_tunnel/{cf_tunnel_id}/connections", "GET", api_token
        )
        return body["result"]

    @integration
    async def get_tunnel_configuration(
        self, *, cf_account_id: str, cf_tunnel_id: str, api_token: str
    ) -> list[dict]:
        """GET /accounts/{cf_account_id}/cfd_tunnel/{cf_tunnel_id}/configurations.
        Returns the raw ingress array — Decision #2: this is the only source
        of truth for fields this app doesn't model (path, originRequest).

        Cloudflare returns "config": null (not a missing key) for a tunnel
        that has never had its remote configuration set — dict.get's default
        only kicks in for a MISSING key, not one present with a null value,
        so a bare `.get("config", {})` still crashes on that response."""
        body = await self._write(
            f"/accounts/{cf_account_id}/cfd_tunnel/{cf_tunnel_id}/configurations", "GET", api_token
        )
        config = body["result"].get("config") or {}
        return config.get("ingress") or []

    @integration
    async def put_tunnel_configuration(
        self, *, cf_account_id: str, cf_tunnel_id: str, api_token: str, ingress: list[dict]
    ) -> None:
        """PUT /accounts/{cf_account_id}/cfd_tunnel/{cf_tunnel_id}/configurations.
        Overwrites the ENTIRE ingress array — no per-rule endpoint exists.
        Caller must have already reconstructed the full array (Decision #2)."""
        await self._write(
            f"/accounts/{cf_account_id}/cfd_tunnel/{cf_tunnel_id}/configurations",
            "PUT",
            api_token,
            json={"config": {"ingress": ingress}},
        )

    @integration
    async def delete_tunnel(self, *, cf_account_id: str, cf_tunnel_id: str, api_token: str) -> None:
        """DELETE /accounts/{cf_account_id}/cfd_tunnel/{cf_tunnel_id}."""
        await self._write(f"/accounts/{cf_account_id}/cfd_tunnel/{cf_tunnel_id}", "DELETE", api_token)

    @integration
    async def list_tunnels(self, *, cf_account_id: str, api_token: str) -> list[dict]:
        """GET /accounts/{cf_account_id}/cfd_tunnel — paginated. Returns the
        raw result list; the sync service maps each tunnel's status field to
        TunnelStatus. Follows the same pagination pattern as list_zones."""
        tunnels: list[dict] = []
        page = 1
        while True:
            body = await self._write(
                f"/accounts/{cf_account_id}/cfd_tunnel",
                "GET",
                api_token,
                params={"page": page, "per_page": 50, "is_deleted": "false"},
            )
            tunnels.extend(body.get("result", []))
            info = body.get("result_info", {})
            if page >= info.get("total_pages", 1):
                break
            page += 1
        return tunnels

    @integration
    async def list_dns_records(self, *, zone_id: str, api_token: str) -> list[dict]:
        """GET /zones/{zone_id}/dns_records — paginated. Returns the raw
        result list; the sync service maps each record's type/fields into
        local schema. Follows the same pagination pattern as list_tunnels."""
        records: list[dict] = []
        page = 1
        while True:
            body = await self._write(
                f"/zones/{zone_id}/dns_records",
                "GET",
                api_token,
                params={"page": page, "per_page": 100},
            )
            records.extend(body.get("result", []))
            info = body.get("result_info", {})
            if page >= info.get("total_pages", 1):
                break
            page += 1
        return records

    @helper
    async def _graphql(self, query: str, variables: dict, api_token: str) -> dict:
        """POST /graphql. A different envelope than _write's REST v4 shape —
        no `success` key; the response is {"data": ..., "errors": null|[...]}.
        A body-level non-null `errors` array is Cloudflare's own signal of
        rejection (bad query, or a permission the token lacks, e.g.
        Zone:Analytics:Read for httpRequestsAdaptiveGroups)."""
        try:
            async with httpx.AsyncClient(
                base_url=str(cloudflare_settings.API_BASE_URL), transport=self._transport
            ) as client:
                response = await client.post(
                    "/graphql",
                    json={"query": query, "variables": variables},
                    headers={"Authorization": f"Bearer {api_token}"},
                    timeout=cloudflare_settings.HTTP_TIMEOUT_SECONDS,
                )
        except httpx.HTTPError as exc:
            raise CloudflareApiUnavailable() from exc

        if response.status_code in (401, 403):
            raise InvalidCloudflareToken()
        if response.status_code >= 500:
            raise CloudflareApiUnavailable(status_code=response.status_code)
        body = response.json()
        errors = body.get("errors")
        if errors:
            logger.warning("Cloudflare GraphQL query rejected: %s", errors)
            raise CloudflareAnalyticsQueryRejected(message="; ".join(e.get("message", "") for e in errors))
        return body["data"]

    @integration
    async def get_zone_traffic_stats(
        self, *, zone_id: str, api_token: str, hostname: str, since: datetime, until: datetime
    ) -> CloudflareTrafficStats:
        """GraphQL Analytics httpRequestsAdaptiveGroups, filtered to one
        hostname — never the whole shared zone (a zone can host many
        unrelated environments). Free-plan compatible, unlike Logpull/
        Logpush (Enterprise-only). Combines totals + hourly buckets + status
        breakdown into one request (3 aliased groups) to minimize the
        GraphQL API's account-wide 300-queries/5-minutes rate limit."""
        query = """
        query TrafficStats($zoneTag: string, $filter: filter) {
          viewer {
            zones(filter: { zoneTag: $zoneTag }) {
              totals: httpRequestsAdaptiveGroups(filter: $filter, limit: 1) {
                count
                sum { edgeResponseBytes }
              }
              timeseries: httpRequestsAdaptiveGroups(
                filter: $filter, limit: 500, orderBy: [datetimeHour_ASC]
              ) {
                count
                sum { edgeResponseBytes }
                dimensions { datetimeHour }
              }
              byStatus: httpRequestsAdaptiveGroups(
                filter: $filter, limit: 50, orderBy: [count_DESC]
              ) {
                count
                dimensions { edgeResponseStatus }
              }
            }
          }
        }
        """
        variables = {
            "zoneTag": zone_id,
            "filter": {
                "datetime_geq": since.isoformat(),
                "datetime_lt": until.isoformat(),
                "clientRequestHTTPHost": hostname,
                "requestSource": "eyeball",
            },
        }
        data = await self._graphql(query, variables, api_token)
        zones = data["viewer"]["zones"]
        if not zones:
            return CloudflareTrafficStats(
                hostname=hostname, total_requests=0, total_bytes=0, buckets=[], status_codes=[]
            )
        zone = zones[0]
        if zone["totals"]:
            total_requests: int = zone["totals"][0]["count"]
            total_bytes: int = zone["totals"][0]["sum"]["edgeResponseBytes"]
        else:
            total_requests = 0
            total_bytes = 0
        return CloudflareTrafficStats(
            hostname=hostname,
            total_requests=total_requests,
            total_bytes=total_bytes,
            buckets=[
                CloudflareTrafficBucket(
                    bucket_start=row["dimensions"]["datetimeHour"],
                    requests=row["count"],
                    bytes=row["sum"]["edgeResponseBytes"],
                )
                for row in zone["timeseries"]
            ],
            status_codes=[
                CloudflareTrafficStatusCount(
                    status=row["dimensions"]["edgeResponseStatus"], requests=row["count"]
                )
                for row in zone["byStatus"]
            ],
        )

    @integration
    async def list_available_alerts(self, *, cf_account_id: str, api_token: str) -> list[dict]:
        """GET /accounts/{cf_account_id}/alerting/v3/available_alerts.
        Cloudflare returns `result` as a map keyed by category name (e.g.
        "Origin Monitoring"), each value a list of alert-type dicts —
        confirmed against Cloudflare's live API reference, not the flat list
        this previously assumed. Flattened here so the observability service
        layer never needs to know categories exist. No pagination — not
        documented for this endpoint."""
        body = await self._write(f"/accounts/{cf_account_id}/alerting/v3/available_alerts", "GET", api_token)
        result = body.get("result") or {}
        return [item for category_items in result.values() for item in category_items]

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
        self,
        *,
        cf_account_id: str,
        api_token: str,
        name: str,
        alert_type: str,
        webhook_destination_id: str,
        zone_id: str | None = None,
    ) -> str:
        """POST /accounts/{cf_account_id}/alerting/v3/policies. mechanisms.webhooks
        points at the already-registered destination id. Returns the real
        policy_id — persisted as alert_rules.cf_policy_id for 2-way sync.
        zone_id, when given, scopes the policy to that one zone via
        filters.zones — without it, Cloudflare fires this policy for every
        zone under the account, not just the one this alert rule was
        created for. The caller decides whether zone_id is appropriate for
        this alert_type (not every type supports zone filtering)."""
        payload: dict = {
            "name": name,
            "alert_type": alert_type,
            "enabled": True,
            "mechanisms": {"webhooks": [{"id": webhook_destination_id}]},
        }
        if zone_id is not None:
            payload["filters"] = {"zones": [zone_id]}
        body = await self._write(
            f"/accounts/{cf_account_id}/alerting/v3/policies", "POST", api_token, json=payload
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
        await self._write(
            f"/accounts/{cf_account_id}/alerting/v3/policies/{policy_id}/test", "POST", api_token
        )
