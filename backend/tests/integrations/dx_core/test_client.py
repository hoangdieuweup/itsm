"""Unit tests for app.integrations.dx_core.client — no real network calls,
a fake httpx transport stands in for the DX OAuth2 server. Response bodies
mirror dx-core-service's /oauth2 controller (userinfo keys are camelCase)."""

import base64
import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from pydantic import HttpUrl

from app.integrations.dx_core.client import DxCoreClient
from app.integrations.dx_core.config import dx_core_settings
from app.integrations.dx_core.constants import DxEndpoints
from app.integrations.dx_core.exceptions import DxCoreUnavailable, TokenExchangeFailed

DX_BASE_URL = "https://dx.test"
EXPECTED_BASIC_AUTH = "Basic " + base64.b64encode(b"itsm:itsm-secret").decode()


@pytest.fixture(autouse=True)
def _dx_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dx_core_settings, "API_BASE_URL", HttpUrl(DX_BASE_URL))
    monkeypatch.setattr(dx_core_settings, "CLIENT_ID", "itsm")
    monkeypatch.setattr(dx_core_settings, "CLIENT_SECRET", "itsm-secret")
    monkeypatch.setattr(dx_core_settings, "POST_LOGOUT_REDIRECT_URI", "")


def _userinfo(*, without: tuple[str, ...] = (), **overrides) -> dict:
    body = {
        "sub": "dx-user-1",
        "email": "alice@example.com",
        "name": "Alice",
        "employeeCode": "E001",
        "emailVerified": True,
        "roles": [{"id": "r1", "code": "employee", "name": "Employee", "level": 3}],
        "department": {"id": "d1", "code": "IT", "name": "IT"},
        "scope": "",
        "permissions": [{"code": "users:view", "scope": "all"}],
    }
    body.update(overrides)
    for key in without:
        body.pop(key)
    return body


def _token_body(**overrides) -> dict:
    body = {"access_token": "dx-at", "refresh_token": "dx-rt", "token_type": "Bearer", "expires_in": 900}
    body.update(overrides)
    return body


class TestFetchUserinfo:
    async def test_maps_the_camel_case_profile(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == DxEndpoints.USERINFO
            assert request.headers["authorization"] == "Bearer dx-at"
            return httpx.Response(200, json=_userinfo())

        profile = await DxCoreClient(transport=httpx.MockTransport(handler)).fetch_userinfo("dx-at")

        assert profile.sub == "dx-user-1"
        assert profile.name == "Alice"
        assert profile.employee_code == "E001"
        assert profile.email_verified is True
        assert profile.department is not None and profile.department.code == "IT"

    async def test_accepts_a_profile_without_a_name(self) -> None:
        """DX builds name from user.info.fullName and drops the key when it is unset."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_userinfo(without=("name",)))

        profile = await DxCoreClient(transport=httpx.MockTransport(handler)).fetch_userinfo("dx-at")

        assert profile.name is None

    async def test_raises_unavailable_when_the_profile_is_malformed(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_userinfo(without=("sub",)))

        with pytest.raises(DxCoreUnavailable):
            await DxCoreClient(transport=httpx.MockTransport(handler)).fetch_userinfo("dx-at")

    async def test_raises_unavailable_on_an_upstream_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, json={"error": "server_error"})

        with pytest.raises(DxCoreUnavailable):
            await DxCoreClient(transport=httpx.MockTransport(handler)).fetch_userinfo("dx-at")


class TestExchangeCode:
    async def test_posts_the_code_and_verifier_with_basic_auth(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "POST"
            assert request.url.path == DxEndpoints.TOKEN
            assert request.headers["authorization"] == EXPECTED_BASIC_AUTH
            body = json.loads(request.content)
            assert body["grant_type"] == "authorization_code"
            assert body["code"] == "auth-code"
            assert body["code_verifier"] == "verifier"
            assert body["redirect_uri"].endswith(DxCoreClient.CALLBACK_PATH)
            return httpx.Response(200, json=_token_body(scope="users:view"))

        token = await DxCoreClient(transport=httpx.MockTransport(handler)).exchange_code(
            "auth-code", "verifier"
        )

        assert token.access_token == "dx-at"
        assert token.refresh_token == "dx-rt"
        assert token.expires_in == 900
        assert token.scope == "users:view"

    async def test_raises_token_exchange_failed_on_invalid_grant(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"error": "invalid_grant"})

        with pytest.raises(TokenExchangeFailed):
            await DxCoreClient(transport=httpx.MockTransport(handler)).exchange_code("used-code", "verifier")

    async def test_raises_unavailable_when_the_token_response_is_malformed(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"access_token": "dx-at"})

        with pytest.raises(DxCoreUnavailable):
            await DxCoreClient(transport=httpx.MockTransport(handler)).exchange_code("auth-code", "verifier")


class TestRevoke:
    async def test_posts_the_token_with_basic_auth(self) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json={"success": True})

        await DxCoreClient(transport=httpx.MockTransport(handler)).revoke("dx-rt")

        assert len(seen) == 1
        assert seen[0].url.path == DxEndpoints.REVOKE
        assert seen[0].headers["authorization"] == EXPECTED_BASIC_AUTH
        assert json.loads(seen[0].content) == {"token": "dx-rt"}

    async def test_swallows_an_upstream_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"error": "server_error"})

        await DxCoreClient(transport=httpx.MockTransport(handler)).revoke("dx-rt")

    async def test_swallows_a_transport_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        await DxCoreClient(transport=httpx.MockTransport(handler)).revoke("dx-rt")


class TestBuildLogoutUrl:
    def test_carries_only_the_client_id_by_default(self) -> None:
        """Without a requested URI, DX redirects to the one registered for the client."""
        url = urlparse(DxCoreClient().build_logout_url())

        assert f"{url.scheme}://{url.netloc}" == DX_BASE_URL
        assert url.path == DxEndpoints.LOGOUT
        assert parse_qs(url.query) == {"client_id": ["itsm"]}

    def test_adds_the_configured_post_logout_redirect_uri(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(dx_core_settings, "POST_LOGOUT_REDIRECT_URI", "https://itsm.test/login")

        query = parse_qs(urlparse(DxCoreClient().build_logout_url()).query)

        assert query == {"client_id": ["itsm"], "post_logout_redirect_uri": ["https://itsm.test/login"]}
