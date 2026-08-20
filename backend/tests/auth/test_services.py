"""Unit tests for the auth module's use cases.

No database, no Redis, no HTTP — every collaborator is a fake implementing
the module's own Abstract* contract, per docs/tasks/sso-login.md's own
"service tests with fake repos + fake DX HTTP client" acceptance criterion.
Router-level behavior (cookies, redirects, real Postgres/Redis) is covered
separately in tests/auth/test_router.py.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime

import jwt
import pytest

from app.core.events import DomainEvent
from app.integrations.cache.keys import CacheKeyBuilder
from app.integrations.dx_core.client import DxDepartment, DxUserProfile
from app.integrations.dx_core.repository import AbstractDxTokenRepository
from app.modules.auth.config import auth_settings
from app.modules.auth.constants import AuthCacheNamespaces, UserRole, UserStatus
from app.modules.auth.events import UserCreated, UserLoggedIn
from app.modules.auth.exceptions import UserBlocked
from app.modules.auth.repository import AbstractDepartmentRepository, AbstractUserRepository
from app.modules.auth.schemas import DepartmentRead, UserRead
from app.modules.auth.services.authenticate import AuthenticateWithDx
from app.modules.auth.services.issue_tokens import IssueTokens
from app.modules.auth.services.logout import LogoutUser
from app.modules.auth.services.sync_external_user import SyncExternalUser
from app.modules.auth.uow import AbstractAuthUnitOfWork


class FakeUserRepository(AbstractUserRepository):
    """In-memory stand-in for UserRepository. No SQLAlchemy, no session."""

    def __init__(self) -> None:
        self._rows: dict[int, UserRead] = {}
        self._next_id = 1
        self.last_login_calls: list[tuple[int, datetime]] = []

    async def get_by_id(self, entity_id: int) -> UserRead | None:
        return self._rows.get(entity_id)

    async def list_page(self, limit: int, offset: int) -> tuple[list[UserRead], int]:
        items = list(self._rows.values())[offset : offset + limit]
        return items, len(self._rows)

    async def find_by_email(self, email: str) -> UserRead | None:
        return next((u for u in self._rows.values() if u.email == email), None)

    async def find_by_external_id(self, external_user_id: str) -> UserRead | None:
        return next((u for u in self._rows.values() if u.external_user_id == external_user_id), None)

    async def create(
        self,
        *,
        email: str,
        name: str,
        role: UserRole,
        external_user_id: str,
        employee_code: str | None,
        email_confirmed: bool,
        department_id: int | None,
    ) -> UserRead:
        user = UserRead(
            id=self._next_id,
            email=email,
            name=name,
            role=role,
            status=UserStatus.ACTIVE,
            department_id=department_id,
            external_user_id=external_user_id,
            employee_code=employee_code,
            email_confirmed=email_confirmed,
            last_login_at=None,
            created_at=datetime.now(UTC),
        )
        self._rows[user.id] = user
        self._next_id += 1
        return user

    async def update_profile(
        self,
        user_id: int,
        *,
        email: str,
        name: str,
        external_user_id: str,
        employee_code: str | None,
        email_confirmed: bool,
        department_id: int | None,
    ) -> UserRead:
        existing = self._rows[user_id]
        updated = existing.model_copy(
            update={
                "email": email,
                "name": name,
                "external_user_id": external_user_id,
                "employee_code": employee_code,
                "email_confirmed": email_confirmed,
                "department_id": department_id,
            }
        )
        self._rows[user_id] = updated
        return updated

    async def set_last_login(self, user_id: int, at: datetime) -> None:
        self.last_login_calls.append((user_id, at))
        existing = self._rows.get(user_id)
        if existing is not None:
            self._rows[user_id] = existing.model_copy(update={"last_login_at": at})

    def seed_blocked(self, user: UserRead) -> None:
        """Test helper: insert a user directly (e.g. already BLOCKED)."""
        self._rows[user.id] = user
        self._next_id = max(self._next_id, user.id + 1)


class FakeDepartmentRepository(AbstractDepartmentRepository):
    """In-memory stand-in for DepartmentRepository."""

    def __init__(self) -> None:
        self._rows: dict[str, DepartmentRead] = {}
        self._next_id = 1

    async def get_by_id(self, entity_id: int) -> DepartmentRead | None:
        return next((d for d in self._rows.values() if d.id == entity_id), None)

    async def list_page(self, limit: int, offset: int) -> tuple[list[DepartmentRead], int]:
        items = list(self._rows.values())[offset : offset + limit]
        return items, len(self._rows)

    async def find_by_code(self, code: str) -> DepartmentRead | None:
        return self._rows.get(code)

    async def get_or_create_by_code(self, code: str, name: str) -> DepartmentRead:
        existing = self._rows.get(code)
        if existing is not None:
            return existing
        department = DepartmentRead(id=self._next_id, code=code, name=name)
        self._rows[code] = department
        self._next_id += 1
        return department


class FakeAuthUnitOfWork(AbstractAuthUnitOfWork):
    """In-memory unit of work. commit/rollback are no-ops that just count calls."""

    def __init__(self) -> None:
        self.users = FakeUserRepository()
        self.departments = FakeDepartmentRepository()
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


@dataclass
class FakeDxTokenRow:
    """Stand-in for app.integrations.dx_core.models.DxToken — plaintext, no encryption."""

    user_id: int
    access_token: str
    refresh_token: str
    expires_at: datetime


class FakeDxTokenRepository(AbstractDxTokenRepository):
    """In-memory stand-in for DxTokenRepository. Stores tokens as plaintext —
    encryption is DxTokenRepository's own concern, not this use case's."""

    def __init__(self) -> None:
        self._rows: dict[int, FakeDxTokenRow] = {}
        self.saved: list[tuple[int, str]] = []
        self.cleared: list[int] = []

    async def get_by_user_id(self, user_id: int) -> FakeDxTokenRow | None:
        return self._rows.get(user_id)

    async def save(self, user_id: int, token, *, expires_at: datetime) -> None:
        self._rows[user_id] = FakeDxTokenRow(
            user_id=user_id,
            access_token=token.access_token,
            refresh_token=token.refresh_token,
            expires_at=expires_at,
        )
        self.saved.append((user_id, token.access_token))

    async def clear(self, user_id: int) -> None:
        self._rows.pop(user_id, None)
        self.cleared.append(user_id)

    def decrypt_access_token(self, row: FakeDxTokenRow) -> str:
        return row.access_token


@dataclass
class FakeDxTokenSet:
    """Stand-in for app.integrations.dx_core.client.DxTokenSet."""

    access_token: str = "dx-access-token"
    refresh_token: str = "dx-refresh-token"
    expires_in: int = 3600
    scope: str = ""


class FakeDxCoreClient:
    """Fake DX HTTP client per the acceptance criterion — no real network I/O.

    Duck-typed rather than a DxCoreClient subclass: the two use cases under
    test only ever call exchange_code/fetch_userinfo/revoke on it.
    """

    def __init__(self, token: FakeDxTokenSet | None = None, profile: DxUserProfile | None = None) -> None:
        self.token = token or FakeDxTokenSet()
        self.profile = profile
        self.revoked: list[str] = []

    async def exchange_code(self, code: str, code_verifier: str) -> FakeDxTokenSet:
        return self.token

    async def fetch_userinfo(self, access_token: str) -> DxUserProfile:
        assert self.profile is not None
        return self.profile

    async def revoke(self, token: str) -> None:
        self.revoked.append(token)


@dataclass
class FakeEventBus:
    """Records every published event instead of dispatching to handlers."""

    published: list[DomainEvent] = field(default_factory=list)

    async def publish(self, event: DomainEvent) -> None:
        self.published.append(event)


def _dx_profile(**overrides) -> DxUserProfile:
    defaults = {
        "sub": "dx-sub-1",
        "email": "alice@example.com",
        "name": "Alice",
        "department": DxDepartment(code="mkt", name="Marketing"),
        "roles": ["manager"],
        "employee_code": "E001",
        "email_verified": True,
    }
    defaults.update(overrides)
    return DxUserProfile(**defaults)


class TestSyncExternalUser:
    """SyncExternalUser: upsert a local user/department from a DX profile."""

    async def test_creates_new_user_with_department_and_resolved_role(self) -> None:
        uow = FakeAuthUnitOfWork()
        use_case = SyncExternalUser(uow)

        user, is_new = await use_case.execute(_dx_profile())

        assert is_new is True
        assert user.email == "alice@example.com"
        assert user.role is UserRole.ADMIN  # "manager" -> ADMIN per RoleMapping
        assert user.status is UserStatus.ACTIVE
        department = await uow.departments.find_by_code("mkt")
        assert department is not None
        assert user.department_id == department.id

    async def test_creates_user_without_department_when_profile_has_none(self) -> None:
        uow = FakeAuthUnitOfWork()
        use_case = SyncExternalUser(uow)

        user, is_new = await use_case.execute(_dx_profile(department=None))

        assert is_new is True
        assert user.department_id is None

    async def test_second_login_updates_profile_without_touching_role_or_status(self) -> None:
        uow = FakeAuthUnitOfWork()
        use_case = SyncExternalUser(uow)
        first, _ = await use_case.execute(_dx_profile(roles=["manager"]))

        second, is_new = await use_case.execute(_dx_profile(name="Alice B.", roles=["director"]))

        assert is_new is False
        assert second.id == first.id
        assert second.name == "Alice B."
        assert second.role is UserRole.ADMIN  # unchanged despite roles now saying "director"

    async def test_matches_existing_user_by_email_when_external_id_unseen(self) -> None:
        """A user created before this DX link existed (or under a different sub)
        is matched by email so login doesn't create a duplicate account."""
        uow = FakeAuthUnitOfWork()
        existing = await uow.users.create(
            email="alice@example.com",
            name="Alice (legacy)",
            role=UserRole.OWNER,
            external_user_id="stale-sub",
            employee_code=None,
            email_confirmed=False,
            department_id=None,
        )
        use_case = SyncExternalUser(uow)

        user, is_new = await use_case.execute(_dx_profile(sub="dx-sub-new"))

        assert is_new is False
        assert user.id == existing.id
        assert user.external_user_id == "dx-sub-new"
        assert user.role is UserRole.OWNER  # role never overwritten by a profile sync


class TestIssueTokens:
    """IssueTokens: mint this app's own session JWTs, independent of DX's own tokens."""

    async def test_issues_access_and_refresh_tokens_with_expected_claims(self) -> None:
        user = UserRead(
            id=42,
            email="bob@example.com",
            name="Bob",
            role=UserRole.MEMBER,
            status=UserStatus.ACTIVE,
            department_id=None,
            external_user_id="sub",
            employee_code=None,
            email_confirmed=True,
            last_login_at=None,
            created_at=datetime.now(UTC),
        )

        tokens = await IssueTokens().execute(user)

        access_claims = jwt.decode(tokens.access_token, auth_settings.JWT_SECRET, algorithms=["HS256"])
        refresh_claims = jwt.decode(tokens.refresh_token, auth_settings.JWT_SECRET, algorithms=["HS256"])
        assert access_claims["sub"] == "42"
        assert access_claims["role"] == "member"
        assert access_claims["type"] == "access"
        assert refresh_claims["sub"] == "42"
        assert refresh_claims["type"] == "refresh"
        assert access_claims["jti"] != refresh_claims["jti"]
        assert (access_claims["exp"] - access_claims["iat"]) == auth_settings.ACCESS_TOKEN_TTL_SECONDS
        assert (refresh_claims["exp"] - refresh_claims["iat"]) == auth_settings.REFRESH_TOKEN_TTL_SECONDS


class TestAuthenticateWithDx:
    """AuthenticateWithDx: exchange code -> profile -> sync -> policy -> tokens -> session."""

    def _build(self, *, profile: DxUserProfile, token: FakeDxTokenSet | None = None):
        uow = FakeAuthUnitOfWork()
        dx_tokens = FakeDxTokenRepository()
        dx_client = FakeDxCoreClient(token=token, profile=profile)
        events = FakeEventBus()
        use_case = AuthenticateWithDx(uow, dx_tokens, dx_client, SyncExternalUser(uow), IssueTokens(), events)
        return use_case, uow, dx_tokens, events

    async def test_new_user_login_stores_dx_tokens_commits_and_publishes_both_events(self) -> None:
        use_case, uow, dx_tokens, events = self._build(profile=_dx_profile())

        result = await use_case.execute("auth-code", "verifier")

        assert result.user.email == "alice@example.com"
        assert result.tokens.access_token and result.tokens.refresh_token
        assert dx_tokens.saved == [(result.user.id, "dx-access-token")]
        assert uow.commits == 1
        assert uow.users.last_login_calls[0][0] == result.user.id
        published_types = [type(e) for e in events.published]
        assert published_types == [UserCreated, UserLoggedIn]

    async def test_returning_user_login_does_not_publish_user_created(self) -> None:
        use_case, uow, _dx_tokens, events = self._build(profile=_dx_profile())
        await use_case.execute("first-code", "first-verifier")
        events.published.clear()

        await use_case.execute("second-code", "second-verifier")

        assert [type(e) for e in events.published] == [UserLoggedIn]

    async def test_blocked_user_raises_before_storing_tokens_or_committing(self) -> None:
        uow = FakeAuthUnitOfWork()
        blocked = UserRead(
            id=7,
            email="blocked@example.com",
            name="Blocked",
            role=UserRole.MEMBER,
            status=UserStatus.BLOCKED,
            department_id=None,
            external_user_id="dx-sub-1",
            employee_code=None,
            email_confirmed=True,
            last_login_at=None,
            created_at=datetime.now(UTC),
        )
        uow.users.seed_blocked(blocked)
        dx_tokens = FakeDxTokenRepository()
        events = FakeEventBus()
        use_case = AuthenticateWithDx(
            uow,
            dx_tokens,
            FakeDxCoreClient(profile=_dx_profile(email="blocked@example.com")),
            SyncExternalUser(uow),
            IssueTokens(),
            events,
        )

        with pytest.raises(UserBlocked):
            await use_case.execute("code", "verifier")

        assert dx_tokens.saved == []
        assert uow.commits == 0
        assert events.published == []


class TestLogoutUser:
    """LogoutUser: best-effort DX revoke, always clear the DX link, blacklist app tokens."""

    def _valid_token(self, *, ttl: int = 3600) -> str:
        return jwt.encode(
            {
                "sub": "1",
                "type": "access",
                "jti": "jti-1",
                "iat": int(datetime.now(UTC).timestamp()),
                "exp": int(datetime.now(UTC).timestamp()) + ttl,
            },
            auth_settings.JWT_SECRET,
            algorithm="HS256",
        )

    async def test_revokes_dx_token_clears_link_and_blacklists_both_app_tokens(self, cache_client) -> None:
        dx_tokens = FakeDxTokenRepository()
        await dx_tokens.save(1, FakeDxTokenSet(access_token="plain-dx-token"), expires_at=datetime.now(UTC))
        dx_client = FakeDxCoreClient()
        use_case = LogoutUser(dx_tokens, dx_client, cache_client)
        access = self._valid_token()
        refresh = self._valid_token()

        await use_case.execute(1, access, refresh)

        assert dx_client.revoked == ["plain-dx-token"]
        assert dx_tokens.cleared == [1]
        assert await cache_client.get_json(_blacklist_key(access)) == {"revoked": True}
        assert await cache_client.get_json(_blacklist_key(refresh)) == {"revoked": True}

    async def test_skips_dx_revoke_when_user_never_linked(self, cache_client) -> None:
        dx_tokens = FakeDxTokenRepository()
        dx_client = FakeDxCoreClient()
        use_case = LogoutUser(dx_tokens, dx_client, cache_client)

        await use_case.execute(1, None, None)

        assert dx_client.revoked == []
        assert dx_tokens.cleared == [1]

    async def test_skips_blacklisting_an_unparsable_token(self, cache_client) -> None:
        dx_tokens = FakeDxTokenRepository()
        use_case = LogoutUser(dx_tokens, FakeDxCoreClient(), cache_client)

        await use_case.execute(1, "not-a-jwt", None)  # must not raise


def _blacklist_key(raw_token: str) -> str:
    claims = jwt.decode(raw_token, auth_settings.JWT_SECRET, algorithms=["HS256"])
    return CacheKeyBuilder.session_key(AuthCacheNamespaces.TOKEN_BLACKLIST, claims["jti"])
