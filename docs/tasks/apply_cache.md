# Redis Cache-Aside Before Database

Add cache-aside reads to the auth and rbac repositories so that `get_by_id` and frequently-called lookups check Redis first, hitting PostgreSQL only on a cache miss. The infrastructure (`CacheClient.get_or_load`, versioned keys, singleflight, graceful degradation) already exists — this plan wires it into the domain modules.

## User Review Required

> [!IMPORTANT]
> **Which read paths to cache?** The plan caches `get_by_id` on user, role, and `get_role_for_user` (the per-request permission check). It does NOT cache `find_by_email`, `find_by_external_id`, `list_page`, or uniqueness checks — those must hit fresh data (per caching.md: "Uniqueness checks must read fresh"). Please confirm this scope is what you intend.

> [!IMPORTANT]
> **Separate entity caching (rule #7).** `get_role_for_user` currently returns a `RoleRead` (role + permissions). Per rule #7 ("cache entities, not join results"), this will be cached as a separate entry keyed by `user_role:{user_id}` (which user holds which role), invalidated when `assign()` writes. The role entity itself (with permissions) is separately cached under `role:{role_id}`. Is this acceptable, or do you prefer to cache the composed result as a single blob?

## Open Questions

1. **TTL values** — default 300s (5min) from `CacheDefaults.DEFAULT_TTL_SECONDS`. Is this acceptable for user/role data, or should we use a module-specific TTL (e.g. shorter for RBAC permission checks)?

## Proposed Changes

### Current State

| Module | Repository | `get_by_id` | Cache | Invalidation |
|--------|-----------|-------------|-------|-------------|
| auth | `UserRepository` | direct DB query | ❌ | N/A |
| rbac | `RoleRepository` | direct DB query | ❌ | N/A |
| rbac | `UserRoleRepository` | direct DB query | ❌ | N/A |

### Target State

| Module | Repository | `get_by_id` | Cache | Invalidation |
|--------|-----------|-------------|-------|-------------|
| auth | `UserRepository` | `cache.get_or_load` → DB fallback | ✅ versioned | UoW bumps on write |
| rbac | `RoleRepository` | `cache.get_or_load` → DB fallback | ✅ versioned | UoW bumps on write |
| rbac | `UserRoleRepository` | `cache.get_or_load` → DB fallback | ✅ versioned | UoW bumps on assign |

---

### Auth Module

#### [MODIFY] [constants.py](file:///Users/hoangdieu/PycharmProjects/itsm/backend/app/modules/auth/constants.py)

Add `AuthCacheKeys` class with entity name for versioned caching:

```python
class AuthCacheKeys:
    """Cache identity owned by the auth module. See references/caching.md."""
    ENTITY = "user"
    TTL_SECONDS = 300
```

#### [MODIFY] [repository.py](file:///Users/hoangdieu/PycharmProjects/itsm/backend/app/modules/auth/repository.py)

- Accept `CacheClient` in `UserRepository.__init__`
- Change `get_by_id` to use `cache.get_or_load(AuthCacheKeys.ENTITY, entity_id, UserRead, loader)`
- Add private `_load_by_id` that does the current direct DB query
- All other methods (`find_by_email`, `find_by_external_id`, `list_page`) stay uncached (fresh data required)

```python
class UserRepository(AbstractUserRepository):
    def __init__(self, session: AsyncSession, cache: CacheClient) -> None:
        self._session = session
        self._cache = cache

    @database
    async def get_by_id(self, entity_id: int) -> UserRead | None:
        return await self._cache.get_or_load(
            AuthCacheKeys.ENTITY, entity_id, UserRead, lambda: self._load_by_id(entity_id)
        )

    @helper
    async def _load_by_id(self, entity_id: int) -> UserRead | None:
        row = await self._session.scalar(select(User).where(User.id == entity_id))
        return UserRead.model_validate(row) if row else None
```

#### [MODIFY] [uow.py](file:///Users/hoangdieu/PycharmProjects/itsm/backend/app/modules/auth/uow.py)

- Accept `CacheClient` in `AuthUnitOfWork.__init__`, pass to `UserRepository`
- Add `mark_stale(entity, entity_id)` — queues for post-commit invalidation
- `commit()`: after `session.commit()`, bumps version for every queued entity
- `rollback()`: clears the stale queue

```python
class AuthUnitOfWork(AbstractAuthUnitOfWork):
    def __init__(self, session: AsyncSession, cache: CacheClient) -> None:
        self._session = session
        self._cache = cache
        self._stale: list[tuple[str, int]] = []
        self.users = UserRepository(session, cache)

    def mark_stale(self, entity: str, entity_id: int) -> None:
        self._stale.append((entity, entity_id))

    async def commit(self) -> None:
        await self._session.commit()
        for entity, entity_id in self._stale:
            await self._cache.bump_version(entity, entity_id)
        self._stale.clear()

    async def rollback(self) -> None:
        await self._session.rollback()
        self._stale.clear()
```

#### [MODIFY] [dependencies.py](file:///Users/hoangdieu/PycharmProjects/itsm/backend/app/modules/auth/dependencies.py)

- `get_uow` accepts `cache: CacheClient = Depends(get_cache)` and passes to `AuthUnitOfWork`

#### [MODIFY] Write services that mutate users

Services that call `create`, `update_profile`, `set_status`, `set_last_login` must call `uow.mark_stale(AuthCacheKeys.ENTITY, user_id)` before `uow.commit()`.

Files affected:
- [sync_external_user.py](file:///Users/hoangdieu/PycharmProjects/itsm/backend/app/modules/auth/services/sync_external_user.py) — after create/update_profile
- [update_user_status.py](file:///Users/hoangdieu/PycharmProjects/itsm/backend/app/modules/auth/services/update_user_status.py) — after set_status

---

### RBAC Module

#### [MODIFY] [constants.py](file:///Users/hoangdieu/PycharmProjects/itsm/backend/app/modules/rbac/constants.py)

Add cache key classes:

```python
class RbacCacheKeys:
    """Cache identity owned by the rbac module. See references/caching.md."""
    ROLE_ENTITY = "role"
    USER_ROLE_ENTITY = "user_role"
    TTL_SECONDS = 300
```

#### [MODIFY] [repository.py](file:///Users/hoangdieu/PycharmProjects/itsm/backend/app/modules/rbac/repository.py)

**RoleRepository:**
- Accept `CacheClient`, cache `get_by_id` via `get_or_load`
- `find_by_name`, `list_page` stay uncached

**UserRoleRepository:**
- Accept `CacheClient`, cache `get_role_for_user` via `get_or_load` (keyed by `user_role:{user_id}`)
- `user_has_permission` stays uncached (derived from get_role_for_user anyway — see design note below)

**PermissionRepository:**
- Stays uncached. The permission catalog is small, fixed, and seeded — caching adds complexity without meaningful gain.

> [!NOTE]
> **Design note on `user_has_permission`:** Currently this does a 4-table JOIN per request. An alternative is to rewrite it to use the cached `get_role_for_user` (which already includes the role's permissions), then check in Python. This avoids the JOIN entirely on a cache hit. This is a potential follow-up optimization, not part of this initial plan.

#### [MODIFY] [uow.py](file:///Users/hoangdieu/PycharmProjects/itsm/backend/app/modules/rbac/uow.py)

Same pattern as auth: accept `CacheClient`, `mark_stale` + post-commit invalidation.

```python
class RbacUnitOfWork(AbstractRbacUnitOfWork):
    def __init__(self, session: AsyncSession, cache: CacheClient) -> None:
        self._session = session
        self._cache = cache
        self._stale: list[tuple[str, int]] = []
        self.roles = RoleRepository(session, cache)
        self.permissions = PermissionRepository(session)  # no cache needed
        self.user_roles = UserRoleRepository(session, cache)
```

#### [MODIFY] [dependencies.py](file:///Users/hoangdieu/PycharmProjects/itsm/backend/app/modules/rbac/dependencies.py)

- `get_uow` accepts `cache: CacheClient = Depends(get_cache)` and passes to `RbacUnitOfWork`

#### [MODIFY] Write services that mutate roles/assignments

- [create_role.py](file:///Users/hoangdieu/PycharmProjects/itsm/backend/app/modules/rbac/services/create_role.py) — `mark_stale(ROLE_ENTITY, role_id)` after create
- [update_role.py](file:///Users/hoangdieu/PycharmProjects/itsm/backend/app/modules/rbac/services/update_role.py) — `mark_stale(ROLE_ENTITY, role_id)` after update
- [delete_role.py](file:///Users/hoangdieu/PycharmProjects/itsm/backend/app/modules/rbac/services/delete_role.py) — `mark_stale(ROLE_ENTITY, role_id)` after delete
- [assign_role.py](file:///Users/hoangdieu/PycharmProjects/itsm/backend/app/modules/rbac/services/assign_role.py) — `mark_stale(USER_ROLE_ENTITY, user_id)` after assign
- [assign_default_role.py](file:///Users/hoangdieu/PycharmProjects/itsm/backend/app/modules/rbac/services/assign_default_role.py) — `mark_stale(USER_ROLE_ENTITY, user_id)` after assign

---

### Summary of Changes

| File | Change |
|------|--------|
| `auth/constants.py` | Add `AuthCacheKeys` |
| `auth/repository.py` | Accept `CacheClient`, cache `get_by_id` |
| `auth/uow.py` | Accept `CacheClient`, `mark_stale` + post-commit invalidation |
| `auth/dependencies.py` | Pass `CacheClient` to UoW |
| `auth/services/sync_external_user.py` | `mark_stale` after write |
| `auth/services/update_user_status.py` | `mark_stale` after write |
| `rbac/constants.py` | Add `RbacCacheKeys` |
| `rbac/repository.py` | Accept `CacheClient`, cache `get_by_id` + `get_role_for_user` |
| `rbac/uow.py` | Accept `CacheClient`, `mark_stale` + post-commit invalidation |
| `rbac/dependencies.py` | Pass `CacheClient` to UoW |
| `rbac/services/create_role.py` | `mark_stale` after write |
| `rbac/services/update_role.py` | `mark_stale` after write |
| `rbac/services/delete_role.py` | `mark_stale` after write |
| `rbac/services/assign_role.py` | `mark_stale` after write |
| `rbac/services/assign_default_role.py` | `mark_stale` after write |

### Not Changed (by design)

| What | Why |
|------|-----|
| `find_by_email`, `find_by_external_id` | Uniqueness checks — must read fresh |
| `list_page` (all modules) | Paginated lists change too often, hard to invalidate |
| `PermissionRepository` | Small, fixed catalog — no benefit from caching |
| `user_has_permission` | Stays as DB JOIN for now (follow-up: rewrite to use cached role) |
| `CacheClient` / `keys.py` | Already has everything needed — no changes required |

## Verification Plan

### Automated Tests

```bash
uv run pytest tests/ -x -v
uv run ruff check app && uv run ruff format --check app
python scripts/check_module_boundaries.py --strict
```

### Manual Verification

1. Start the app, login via DX, verify `/auth/me` works (cache MISS → DB → cache SET)
2. Hit `/auth/me` again, verify Redis has the versioned key (cache HIT)
3. Block/unblock a user, verify the cache version bumps (stale data evicted)
4. Stop Redis, verify the app degrades gracefully (slower, not broken)
