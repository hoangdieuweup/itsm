"""WeUp DX OAuth2 + PKCE client. HTTP only — no database, no Redis.

Implements docs/tasks/sso-login.md section 5.2 against this repo's own
conventions and dx-core-service's /oauth2 controller: httpx per call (no
shared pool — DX is called twice per login and at most twice per logout, so
a pool bought nothing but connect() at startup this integration doesn't
otherwise need), state/PKCE generation with stdlib `secrets`/`hashlib`, S256
challenge only (DX requires it). A body DX sends in a shape this client can't
parse is treated like any other upstream failure.
"""

import base64
import hashlib
import json
import secrets
from typing import Any
from urllib.parse import urlencode

import httpx
from pydantic import ValidationError

from app.config import settings
from app.core.base.markers import helper, integration
from app.core.models import FrozenModel
from app.integrations.dx_core.config import dx_core_settings
from app.integrations.dx_core.constants import DxDefaults, DxEndpoints
from app.integrations.dx_core.exceptions import DxCoreUnavailable, TokenExchangeFailed


class DxPkcePair(FrozenModel):
    """A single-use authorization request's state and PKCE material."""

    state: str
    code_verifier: str
    code_challenge: str


class DxTokenSet(FrozenModel):
    """Tokens returned by DX's /oauth2/token endpoint."""

    access_token: str
    refresh_token: str
    expires_in: int
    scope: str = ""


class DxDepartment(FrozenModel):
    """The department object embedded in a DX /oauth2/userinfo response."""

    code: str
    name: str | None = None


class DxUserProfile(FrozenModel):
    """Profile returned by DX's /oauth2/userinfo endpoint.

    name is optional: DX builds it from the user's full name and leaves the
    key out when that is unset.
    """

    sub: str
    email: str
    name: str | None = None
    department: DxDepartment | None = None
    roles: list[Any] = []
    employee_code: str | None = None
    email_verified: bool = False


class DxCoreClient:
    """Talks to the DX OAuth2 server. One instance per request, built in dependencies.py."""

    CALLBACK_PATH: str = "/api/v1/auth/oauth/dx/callback"

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    @helper
    def generate_pkce_pair(self) -> DxPkcePair:
        """Generate a state + PKCE (S256) verifier/challenge pair for a new login attempt."""
        state = secrets.token_urlsafe(DxDefaults.STATE_BYTES)
        verifier = secrets.token_urlsafe(DxDefaults.CODE_VERIFIER_BYTES)
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
        return DxPkcePair(state=state, code_verifier=verifier, code_challenge=challenge)

    @helper
    def build_authorize_url(self, state: str, code_challenge: str) -> str:
        """Build the URL the browser is redirected to for user login + consent."""
        params = {
            "client_id": dx_core_settings.CLIENT_ID,
            "redirect_uri": self._redirect_uri(),
            "response_type": "code",
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        if dx_core_settings.SCOPES:
            params["scope"] = dx_core_settings.SCOPES
        base = str(dx_core_settings.API_BASE_URL).rstrip("/")
        return f"{base}{DxEndpoints.AUTHORIZE}?{urlencode(params)}"

    @helper
    def build_logout_url(self) -> str:
        """Build the RP-initiated logout URL that ends the browser's DX SSO session.

        post_logout_redirect_uri is sent only when configured: DX redirects to
        the URI registered for this client when the parameter is absent or
        equal to it, and to its own login page otherwise.
        """
        params = {"client_id": dx_core_settings.CLIENT_ID}
        if dx_core_settings.POST_LOGOUT_REDIRECT_URI:
            params["post_logout_redirect_uri"] = dx_core_settings.POST_LOGOUT_REDIRECT_URI
        base = str(dx_core_settings.API_BASE_URL).rstrip("/")
        return f"{base}{DxEndpoints.LOGOUT}?{urlencode(params)}"

    @integration
    async def exchange_code(self, code: str, code_verifier: str) -> DxTokenSet:
        """Exchange an authorization code for a DX token set (confidential client)."""
        response = await self._post(
            DxEndpoints.TOKEN,
            json={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self._redirect_uri(),
                "code_verifier": code_verifier,
            },
        )
        if response.status_code in (400, 401):
            raise TokenExchangeFailed()
        self._raise_for_upstream_error(response)
        try:
            return DxTokenSet.model_validate(response.json())
        except (ValidationError, json.JSONDecodeError) as exc:
            raise DxCoreUnavailable(status_code=response.status_code) from exc

    @integration
    async def fetch_userinfo(self, access_token: str) -> DxUserProfile:
        """Fetch the DX profile for the given access token."""
        try:
            async with self._http() as client:
                response = await client.get(
                    DxEndpoints.USERINFO,
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=DxDefaults.CALLBACK_HTTP_TIMEOUT_SECONDS,
                )
        except httpx.HTTPError as exc:
            raise DxCoreUnavailable() from exc
        self._raise_for_upstream_error(response)
        try:
            return DxUserProfile.model_validate(response.json())
        except (ValidationError, json.JSONDecodeError) as exc:
            raise DxCoreUnavailable(status_code=response.status_code) from exc

    @integration
    async def revoke(self, token: str) -> None:
        """Revoke a DX token per RFC 7009. Best-effort — an outage must not break logout."""
        try:
            await self._post(DxEndpoints.REVOKE, json={"token": token})
        except (DxCoreUnavailable, httpx.HTTPError):
            pass

    @helper
    def _redirect_uri(self) -> str:
        """The callback URL registered on DX — always this backend's own public URL."""
        return f"{settings.BACKEND_BASE_URL.rstrip('/')}{self.CALLBACK_PATH}"

    @helper
    def _basic_auth_header(self) -> str:
        """HTTP Basic Auth header from the confidential client's id:secret."""
        raw = f"{dx_core_settings.CLIENT_ID}:{dx_core_settings.CLIENT_SECRET}".encode()
        return "Basic " + base64.b64encode(raw).decode()

    @helper
    def _http(self) -> httpx.AsyncClient:
        """A short-lived httpx client bound to DX's base URL and the injected transport, if any."""
        return httpx.AsyncClient(base_url=str(dx_core_settings.API_BASE_URL), transport=self._transport)

    @helper
    async def _post(self, path: str, *, json: dict) -> httpx.Response:
        """POST to DX with Basic Auth, mapping a transport failure to DxCoreUnavailable."""
        try:
            async with self._http() as client:
                return await client.post(
                    path,
                    headers={"Authorization": self._basic_auth_header()},
                    json=json,
                    timeout=DxDefaults.CALLBACK_HTTP_TIMEOUT_SECONDS,
                )
        except httpx.HTTPError as exc:
            raise DxCoreUnavailable() from exc

    @helper
    def _raise_for_upstream_error(self, response: httpx.Response) -> None:
        """Map any other non-2xx DX response to DxCoreUnavailable."""
        if response.is_error:
            raise DxCoreUnavailable(status_code=response.status_code)
