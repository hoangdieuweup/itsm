"""Cloudflare REST API client. HTTP only — no database, no business logic.

Lives here (not app/modules/cloudflare/) per the Netflix Dispatch convention
this repo already follows for dx_core/cache/queue/storage/mongo: any
third-party API adapter is a leaf under app/integrations/, imported by
whichever module needs it via dependency injection. app/modules/cloudflare/
owns the business domain (accounts, 2-layer ACL, DNS records, configs) and
reaches this client only through modules/cloudflare/dependencies.py.
"""

import httpx

from app.core.base.markers import helper, integration
from app.integrations.cloudflare.config import cloudflare_settings
from app.integrations.cloudflare.exceptions import (
    CloudflareApiUnavailable,
    CloudflareDnsOperationRejected,
    InvalidCloudflareToken,
)
from app.integrations.cloudflare.schemas import ZoneOption


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
    async def _write(self, path: str, method: str, api_token: str, *, json: dict | None = None) -> dict:
        """Shared envelope-check for the 3 DNS write methods below — a
        rejected write here means Cloudflare itself rejected the payload
        (bad record data, name conflict), which is a DIFFERENT failure mode
        than InvalidCloudflareToken (an auth problem)."""
        try:
            async with httpx.AsyncClient(
                base_url=str(cloudflare_settings.API_BASE_URL), transport=self._transport
            ) as client:
                response = await client.request(
                    method,
                    path,
                    json=json,
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
