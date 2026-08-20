"""HTTP entry points of the auth module.

Every handler below returns 501 Not Implemented: the OAuth2+PKCE flow
(docs/tasks/sso-login.md) that would back these endpoints is out of scope
for this issue (see issue #3's "Owns" section) and belongs to the SSO
integration sub-issue. The route surface and prefix are fixed here so the
frontend and the SSO issue can be built against a stable contract.
"""

from fastapi import APIRouter, HTTPException, status

router = APIRouter(prefix="/auth", tags=["auth"])

_NOT_IMPLEMENTED = "SSO flow not implemented yet — see docs/tasks/sso-login.md"


@router.get("/oauth/dx/start")
async def start_dx_oauth() -> None:
    """Begin the WeUpBook DX OAuth2 + PKCE flow. Stub."""
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=_NOT_IMPLEMENTED)


@router.get("/oauth/dx/callback")
async def dx_oauth_callback() -> None:
    """Handle the DX OAuth2 callback: exchange code, sync user, issue session. Stub."""
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=_NOT_IMPLEMENTED)


@router.post("/logout")
async def logout() -> None:
    """Revoke the DX token and clear the app session. Stub."""
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=_NOT_IMPLEMENTED)


@router.get("/me")
async def me() -> None:
    """Return the signed in user's profile. Stub."""
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=_NOT_IMPLEMENTED)
