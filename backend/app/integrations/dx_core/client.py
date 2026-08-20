"""WeUpBook DX OAuth2 + PKCE client. HTTP only — no database, no Redis.

Implements docs/tasks/sso-login.md section 5.2 against this repo's own
conventions: httpx per call (no shared pool — DX is called at most twice per
login and once per refresh, so a pool bought nothing but connect() at
startup this integration doesn't otherwise need), state/PKCE generation with
stdlib `secrets`/`hashlib`, S256 challenge only (DX requires it).
"""

import base64
import hashlib
import secrets
from urllib.parse import urlencode

import httpx

from app.config import settings
from app.core.base.markers import helper, integration
from app.core.models import FrozenModel
from app.integrations.dx_core.config import dx_core_settings
from app.integrations.dx_core.constants import DxDefaults, DxEndpoints
from app.integrations.dx_core.exceptions import DxCoreUnavailable, TokenExchangeFailed

_CALLBACK_PATH = "/api/v1/auth/oauth/dx/callback"


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
    name: str


class DxUserProfile(FrozenModel):
    """Profile returned by DX's /oauth2/userinfo endpoint."""

    sub: str
    email: str
    name: str
    department: DxDepartment | None = None
    roles: list[str] = []
    employee_code: str | None = None
    email_verified: bool = False


class DxCoreClient:
    """Talks to the DX OAuth2 server. One instance per request, built in dependencies.py."""

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
        return DxTokenSet.model_validate(response.json())

    @integration
    async def fetch_userinfo(self, access_token: str) -> DxUserProfile:
        """Fetch the DX profile for the given access token."""
        try:
            async with httpx.AsyncClient(base_url=str(dx_core_settings.API_BASE_URL)) as client:
                response = await client.get(
                    DxEndpoints.USERINFO,
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=DxDefaults.CALLBACK_HTTP_TIMEOUT_SECONDS,
                )
        except httpx.HTTPError as exc:
            raise DxCoreUnavailable() from exc
        self._raise_for_upstream_error(response)
        return DxUserProfile.model_validate(response.json())

    @integration
    async def refresh(self, refresh_token: str) -> DxTokenSet:
        """Exchange a refresh token for a new DX token set. DX rotates the refresh token."""
        response = await self._post(
            DxEndpoints.TOKEN, json={"grant_type": "refresh_token", "refresh_token": refresh_token}
        )
        if response.status_code in (400, 401):
            raise TokenExchangeFailed()
        self._raise_for_upstream_error(response)
        return DxTokenSet.model_validate(response.json())

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
        return f"{settings.BACKEND_BASE_URL.rstrip('/')}{_CALLBACK_PATH}"

    @helper
    def _basic_auth_header(self) -> str:
        """HTTP Basic Auth header from the confidential client's id:secret."""
        raw = f"{dx_core_settings.CLIENT_ID}:{dx_core_settings.CLIENT_SECRET}".encode()
        return "Basic " + base64.b64encode(raw).decode()

    @helper
    async def _post(self, path: str, *, json: dict) -> httpx.Response:
        """POST to DX with Basic Auth, mapping a transport failure to DxCoreUnavailable."""
        try:
            async with httpx.AsyncClient(base_url=str(dx_core_settings.API_BASE_URL)) as client:
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
