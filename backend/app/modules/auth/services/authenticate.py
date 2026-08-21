"""Use case: complete the DX OAuth2 callback (docs/tasks/sso-login.md #4 Step 4)."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.core.events import EventBus
from app.integrations.dx_core.client import DxCoreClient
from app.integrations.dx_core.repository import AbstractDxTokenRepository
from app.modules.auth.events import UserLoggedIn
from app.modules.auth.exceptions import UserBlocked
from app.modules.auth.rules import AuthRules
from app.modules.auth.services.issue_tokens import AppTokenSet, IssueTokens
from app.modules.auth.services.sync_external_user import SyncExternalUser
from app.modules.auth.uow import AbstractAuthUnitOfWork
from app.modules.rbac.public import RbacApi
from app.modules.users.public import UserCreated, UserRead, UsersApi


@dataclass(frozen=True)
class DxLoginResult:
    """What the callback route needs to finish the HTTP response."""

    user: UserRead
    tokens: AppTokenSet


class AuthenticateWithDx(AbstractUseCase):
    """Exchange code -> profile -> sync user -> policy check -> store DX tokens -> issue session.

    One class, one operation, per core/base/use_case.py rule #9 — the
    callback endpoint's entire business logic lives here so router.py stays
    a thin HTTP adapter that only translates the result into a redirect.
    The caller (router) is responsible for validating/consuming the PKCE
    state before calling this — that is transport-level (cache lookup), not
    a business decision this use case needs to own.

    For a brand new user, also grants the seeded default rbac role via
    rbac's public facade (never rbac's internal dependencies.py/services/ —
    see fastapi-modular-scaffold rule #1) in the same transaction this use
    case commits. users_api.invalidate_user runs right after that commit
    succeeds: the write to the users table happened through UsersApi, but
    the commit that makes it durable is this use case's own uow, not
    users' — so users' usual mark_stale-then-commit dance doesn't apply
    here. See docs/superpowers/specs/2026-08-21-users-module-split-design.md.
    """

    def __init__(
        self,
        uow: AbstractAuthUnitOfWork,
        dx_tokens: AbstractDxTokenRepository,
        dx_client: DxCoreClient,
        sync_user: SyncExternalUser,
        issue_tokens: IssueTokens,
        events: EventBus,
        rbac_api: RbacApi,
        users_api: UsersApi,
    ) -> None:
        self._uow = uow
        self._dx_tokens = dx_tokens
        self._dx_client = dx_client
        self._sync_user = sync_user
        self._issue_tokens = issue_tokens
        self._events = events
        self._rbac_api = rbac_api
        self._users_api = users_api

    @use_case
    async def execute(self, code: str, code_verifier: str) -> DxLoginResult:
        token = await self._dx_client.exchange_code(code, code_verifier)
        profile = await self._dx_client.fetch_userinfo(token.access_token)

        user, is_new = await self._sync_user.execute(profile)
        if not AuthRules.can_login(user.status):
            raise UserBlocked()

        if is_new:
            await self._rbac_api.assign_default_role(user.id)

        expires_at = datetime.now(UTC) + timedelta(seconds=token.expires_in)
        await self._dx_tokens.save(user.id, token, expires_at=expires_at)
        await self._users_api.set_last_login(user.id, datetime.now(UTC))
        await self._uow.commit()
        await self._users_api.invalidate_user(user.id)

        tokens = await self._issue_tokens.execute(user)

        if is_new:
            await self._events.publish(UserCreated(user_id=user.id, email=user.email))
        await self._events.publish(UserLoggedIn(user_id=user.id))

        return DxLoginResult(user=user, tokens=tokens)
