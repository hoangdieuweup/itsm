"""Composition that can't live in dependencies.py.

get_authenticate_with_dx needs RbacApi (rbac.public), and rbac.public needs
auth.public (for require_permission's current_user), which needs
get_current_user from auth/dependencies.py — so putting this factory there
would close that cycle at load time. It lives here instead: nothing in
auth.public or auth.dependencies imports utils/, so this file can safely
reach into rbac.public without closing the cycle. See auth/dependencies.py's
docstring and docs/superpowers/specs/2026-08-21-users-module-split-design.md.

Deliberately not in router.py either — a router function only translates
HTTP into a use-case call (rule #10); composing the use case itself is a
different job, even when it has to live outside dependencies.py.
"""

from fastapi import Depends

from app.core.events import EventBus, get_event_bus
from app.integrations.dx_core.client import DxCoreClient
from app.integrations.dx_core.dependencies import get_dx_core_client
from app.integrations.dx_core.repository import AbstractDxTokenRepository
from app.modules.auth.dependencies import (
    get_dx_token_repository,
    get_issue_tokens,
    get_sync_external_user,
    get_uow,
)
from app.modules.auth.services.authenticate import AuthenticateWithDx
from app.modules.auth.services.issue_tokens import IssueTokens
from app.modules.auth.services.sync_external_user import SyncExternalUser
from app.modules.auth.uow import AbstractAuthUnitOfWork
from app.modules.rbac.public import RbacApi, get_rbac_api
from app.modules.users.public import UsersApi, get_users_api


async def get_authenticate_with_dx(
    uow: AbstractAuthUnitOfWork = Depends(get_uow),
    dx_tokens: AbstractDxTokenRepository = Depends(get_dx_token_repository),
    dx_client: DxCoreClient = Depends(get_dx_core_client),
    sync_user: SyncExternalUser = Depends(get_sync_external_user),
    issue_tokens: IssueTokens = Depends(get_issue_tokens),
    events: EventBus = Depends(get_event_bus),
    rbac_api: RbacApi = Depends(get_rbac_api),
    users_api: UsersApi = Depends(get_users_api),
) -> AuthenticateWithDx:
    """Provide the DX OAuth2 callback use case."""
    return AuthenticateWithDx(uow, dx_tokens, dx_client, sync_user, issue_tokens, events, rbac_api, users_api)
