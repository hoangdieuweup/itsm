"""HTTP entry points of the auth module.

/oauth/dx/start and /oauth/dx/callback are top-level browser navigations
(the SPA never calls them via fetch/XHR), so they redirect rather than
return the ApiResponse envelope — the browser's own address bar is where a
JSON body would otherwise be dumped raw. /logout and /me are ordinary API
endpoints and use the envelope like every other module's routes. See
docs/tasks/sso-login.md sections 5.1 and 11 for the exact contract.
"""

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import RedirectResponse

from app.config import settings
from app.core.events import EventBus, get_event_bus
from app.core.models import ApiResponse
from app.core.pagination import Page, PaginationParams, pagination_params
from app.integrations.cache.client import CacheClient
from app.integrations.cache.dependencies import get_cache
from app.integrations.cache.keys import CacheKeyBuilder
from app.integrations.dx_core.client import DxCoreClient
from app.integrations.dx_core.constants import DxCacheNamespaces, DxDefaults
from app.integrations.dx_core.dependencies import get_dx_core_client
from app.integrations.dx_core.exceptions import DxCoreUnavailable, TokenExchangeFailed
from app.integrations.dx_core.repository import AbstractDxTokenRepository
from app.modules.auth.constants import AuthCookies
from app.modules.auth.dependencies import (
    get_dx_token_repository,
    get_issue_tokens,
    get_logout_user,
    get_sync_external_user,
    get_uow,
    require_auth,
)
from app.modules.auth.exceptions import UserBlocked
from app.modules.auth.schemas import MeResponse, UserRead, UserStatusUpdate
from app.modules.auth.services.authenticate import AuthenticateWithDx
from app.modules.auth.services.issue_tokens import IssueTokens
from app.modules.auth.services.logout import LogoutUser
from app.modules.auth.services.sync_external_user import SyncExternalUser
from app.modules.auth.services.update_user_status import UpdateUserStatus
from app.modules.auth.uow import AbstractAuthUnitOfWork
from app.modules.auth.utils import AuthSessionResponses
from app.modules.rbac.public import RbacApi, get_rbac_api, require_permission

router = APIRouter(prefix="/auth", tags=["auth"])


# The next two dependency-provider functions would normally live in
# dependencies.py alongside every other one, but they need RbacApi from
# rbac.public — and rbac.public needs auth.public, which needs
# auth.dependencies for get_current_user/get_uow. Keeping dependencies.py
# free of any rbac import breaks that cycle: router.py is never imported by
# anything (only main.py imports a router), so by the time either function
# below reaches into rbac.public, auth.dependencies has already finished
# loading in full. See rbac/public.py's docstring for the other half.
async def get_authenticate_with_dx(
    uow: AbstractAuthUnitOfWork = Depends(get_uow),
    dx_tokens: AbstractDxTokenRepository = Depends(get_dx_token_repository),
    dx_client: DxCoreClient = Depends(get_dx_core_client),
    sync_user: SyncExternalUser = Depends(get_sync_external_user),
    issue_tokens: IssueTokens = Depends(get_issue_tokens),
    events: EventBus = Depends(get_event_bus),
    rbac_api: RbacApi = Depends(get_rbac_api),
) -> AuthenticateWithDx:
    """Provide the DX OAuth2 callback use case."""
    return AuthenticateWithDx(uow, dx_tokens, dx_client, sync_user, issue_tokens, events, rbac_api)


async def get_update_user_status(
    uow: AbstractAuthUnitOfWork = Depends(get_uow),
    rbac_api: RbacApi = Depends(get_rbac_api),
) -> UpdateUserStatus:
    """Provide the block/unblock use case."""
    return UpdateUserStatus(uow, rbac_api)


@router.get("/oauth/dx/start")
async def start_dx_oauth(
    cache: CacheClient = Depends(get_cache),
    dx_client: DxCoreClient = Depends(get_dx_core_client),
) -> RedirectResponse:
    """Begin the WeUpBook DX OAuth2 + PKCE flow."""
    pair = dx_client.generate_pkce_pair()
    key = CacheKeyBuilder.session_key(DxCacheNamespaces.PKCE_STATE, pair.state)
    await cache.set_json(key, {"code_verifier": pair.code_verifier}, ttl=DxDefaults.PKCE_STATE_TTL_SECONDS)
    url = dx_client.build_authorize_url(pair.state, pair.code_challenge)
    return RedirectResponse(url, status_code=status.HTTP_302_FOUND)


@router.get("/oauth/dx/callback")
async def dx_oauth_callback(
    code: str | None = Query(None),
    state: str | None = Query(None),
    error: str | None = Query(None),
    cache: CacheClient = Depends(get_cache),
    authenticate: AuthenticateWithDx = Depends(get_authenticate_with_dx),
) -> RedirectResponse:
    """Handle the DX OAuth2 callback: exchange code, sync user, issue session.

    Every failure mode redirects to the SPA's login page with a stable
    ?error= code instead of raising — a mid-flow JSON error would show raw
    text in the user's browser instead of a page it controls.
    """
    if error or not code or not state:
        return AuthSessionResponses.login_error_redirect("sso_denied")

    key = CacheKeyBuilder.session_key(DxCacheNamespaces.PKCE_STATE, state)
    stored = await cache.get_json(key)
    if stored is None:
        return AuthSessionResponses.login_error_redirect("sso_state")
    await cache.delete(key)  # single-use, whether or not the exchange below succeeds

    try:
        result = await authenticate.execute(code, stored["code_verifier"])
    except (TokenExchangeFailed, DxCoreUnavailable):
        return AuthSessionResponses.login_error_redirect("sso_failed")
    except UserBlocked:
        return AuthSessionResponses.login_error_redirect("suspended")

    response = RedirectResponse(settings.FRONTEND_BASE_URL, status_code=status.HTTP_302_FOUND)
    AuthSessionResponses.set_session_cookies(response, result.tokens)
    return response


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    user: UserRead = Depends(require_auth),
    logout_user: LogoutUser = Depends(get_logout_user),
) -> ApiResponse[None]:
    """Revoke the DX token and clear the app session."""
    await logout_user.execute(
        user.id,
        request.cookies.get(AuthCookies.ACCESS_TOKEN),
        request.cookies.get(AuthCookies.REFRESH_TOKEN),
    )
    AuthSessionResponses.clear_session_cookies(response)
    return ApiResponse[None](success=True)


@router.get("/me")
async def me(
    user: UserRead = Depends(require_auth), rbac: RbacApi = Depends(get_rbac_api)
) -> ApiResponse[MeResponse]:
    """Return the signed in user's profile plus their role and permissions —
    what the frontend's PermissionProvider seeds from."""
    summary = await rbac.role_summary_for_user(user.id)
    body = MeResponse(user=user, role_name=summary.role_name, permissions=summary.permissions)
    return ApiResponse[MeResponse](success=True, data=body)


@router.get("/users")
async def list_users(
    pagination: PaginationParams = Depends(pagination_params),
    uow: AbstractAuthUnitOfWork = Depends(get_uow),
    _user: UserRead = Depends(require_permission("user", "read")),
) -> ApiResponse[Page[UserRead]]:
    """List users for the admin user-management page."""
    items, total = await uow.users.list_page(pagination.limit, pagination.offset)
    page = Page[UserRead](items=items, total=total, limit=pagination.limit, offset=pagination.offset)
    return ApiResponse[Page[UserRead]](success=True, data=page)


@router.patch("/users/{user_id}/status")
async def update_user_status(
    user_id: int,
    body: UserStatusUpdate,
    use_case: UpdateUserStatus = Depends(get_update_user_status),
    _user: UserRead = Depends(require_permission("user", "update_status")),
) -> ApiResponse[UserRead]:
    """Block or unblock a user. Blocking the last owner is rejected — see rbac's bus-factor rule."""
    updated = await use_case.execute(user_id, body.status)
    return ApiResponse[UserRead](success=True, data=updated)
