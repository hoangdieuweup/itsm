"""Cloudflare REST API client. HTTP only — no database, no business logic.

Lives here (not app/modules/cloudflare/) per the Netflix Dispatch convention
this repo already follows for dx_core/cache/queue/storage/mongo: any
third-party API adapter is a leaf under app/integrations/, imported by
whichever module needs it via dependency injection. app/modules/cloudflare/
owns the business domain (accounts, 2-layer ACL, DNS records, configs) and
reaches this client only through modules/cloudflare/dependencies.py.
"""

from datetime import datetime

import httpx

from app.core.base.markers import helper, integration
from app.integrations.cloudflare.config import cloudflare_settings
from app.integrations.cloudflare.exceptions import (
    CloudflareApiUnavailable,
    CloudflareDnsOperationRejected,
    InvalidCloudflareToken,
)
from app.integrations.cloudflare.schemas import CloudflareAuditLogEntry, ZoneOption


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
        of truth for fields this app doesn't model (path, originRequest)."""
        body = await self._write(
            f"/accounts/{cf_account_id}/cfd_tunnel/{cf_tunnel_id}/configurations", "GET", api_token
        )
        return body["result"].get("config", {}).get("ingress", [])

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


    @integration
    async def get_account_audit_logs(
        self,
        *,
        cf_account_id: str,
        api_token: str,
        zone_name: str,
        since: datetime | None,
        before: datetime | None,
    ) -> list[CloudflareAuditLogEntry]:
        """GET /accounts/{cf_account_id}/audit_logs?zone.name=<zone_name>.
        zone.name filters to just this environment's bound zone per the
        reference doc's own recommendation — never returns account-wide
        entries for other zones this environment doesn't own. Reuses _write
        (the de-facto generic "authenticated call + envelope check" helper —
        3 existing Tunnel GET methods already reuse it too) rather than a
        new helper; failures surface as CloudflareDnsOperationRejected,
        consistent with that existing precedent, not a scope-creeping rename."""
        params: dict[str, str] = {"zone.name": zone_name}
        if since is not None:
            params["since"] = since.isoformat()
        if before is not None:
            params["before"] = before.isoformat()
        body = await self._write(f"/accounts/{cf_account_id}/audit_logs", "GET", api_token, params=params)
        return [
            CloudflareAuditLogEntry(
                id=entry["id"],
                when=entry["when"],
                actor_email=entry.get("actor", {}).get("email"),
                actor_ip=entry.get("actor", {}).get("ip"),
                action_type=entry.get("action", {}).get("type", ""),
                resource_type=entry.get("resource", {}).get("type"),
                resource_product=entry.get("resource", {}).get("product"),
                new_value=entry.get("newValue"),
            )
            for entry in body.get("result", [])
        ]

    @integration
    async def list_available_alerts(self, *, cf_account_id: str, api_token: str) -> list[dict]:
        """GET /accounts/{cf_account_id}/alerting/v3/available_alerts. Returns
        the raw result list — the observability service layer shapes it into
        AvailableAlertOption."""
        body = await self._write(f"/accounts/{cf_account_id}/alerting/v3/available_alerts", "GET", api_token)
        return body.get("result", [])

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
        self, *, cf_account_id: str, api_token: str, name: str, alert_type: str, webhook_destination_id: str
    ) -> str:
        """POST /accounts/{cf_account_id}/alerting/v3/policies. mechanisms.webhooks
        points at the already-registered destination id. Returns the real
        policy_id — persisted as alert_rules.cf_policy_id for 2-way sync."""
        body = await self._write(
            f"/accounts/{cf_account_id}/alerting/v3/policies",
            "POST",
            api_token,
            json={
                "name": name,
                "alert_type": alert_type,
                "enabled": True,
                "mechanisms": {"webhooks": [{"id": webhook_destination_id}]},
            },
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
