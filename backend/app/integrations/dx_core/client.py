"""WeUpBook DX OAuth2 + PKCE client.

Structural skeleton only: every method raises NotImplementedError. The real
HTTP calls (httpx against DxEndpoints), PKCE pair generation, and encrypted
token persistence belong to the SSO integration sub-issue — see
docs/tasks/sso-login.md section 4 for the exact flow this client will
implement (generate_pkce_pair → exchange_code → fetch_userinfo, refresh,
revoke).
"""

from app.core.models import FrozenModel


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
    scope: str


class DxUserProfile(FrozenModel):
    """Profile returned by DX's /oauth2/userinfo endpoint."""

    sub: str
    email: str
    name: str
    department: str | None
    roles: list[str]
    employee_code: str | None


class DxCoreClient:
    """Talks to the DX OAuth2 server. One instance per request, built in dependencies.py."""

    def generate_pkce_pair(self, next_path: str) -> DxPkcePair:
        """Generate a state + PKCE verifier/challenge pair for a new login attempt."""
        raise NotImplementedError

    async def exchange_code(self, code: str, code_verifier: str) -> DxTokenSet:
        """Exchange an authorization code for a DX token set."""
        raise NotImplementedError

    async def fetch_userinfo(self, access_token: str) -> DxUserProfile:
        """Fetch the DX profile for the given access token."""
        raise NotImplementedError

    async def refresh(self, refresh_token: str) -> DxTokenSet:
        """Exchange a refresh token for a new DX token set."""
        raise NotImplementedError

    async def revoke(self, token: str) -> None:
        """Revoke a DX token per RFC 7009."""
        raise NotImplementedError
