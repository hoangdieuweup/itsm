# DevOps Panel — Phase 2: Audit Log Infrastructure (MongoDB) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up MongoDB as the audit/incident-log store, retrofit Phase 1's project/environment mutations to write audit events, and give admins a filtered log viewer — the shared infrastructure every later phase (Cloudflare, observability, notifications, alerting) will log into.

**Architecture:** A new generic `app/integrations/mongo/` (Motor client, no domain knowledge — same tier as `integrations/cache/`) plus a domain `app/modules/audit/` module that owns the `logs` collection's shape. `log_event()` is fire-and-forget (logs a warning and returns on Mongo failure, never raises into the caller) — extends the existing "cache outage degrades to slow, not broken" philosophy from `caching.md:68`. `list_logs()` is NOT fire-and-forget — a broken log viewer should show an error, not silently return empty. Frontend: a minimal `modules/audit-log/` filtered list screen.

**Tech Stack:** `motor` (async Mongo driver, added this phase), MongoDB 7 (already running locally as a shared container named `mongo` on `chatbot_network`, port 27017 — reused across the user's projects, not itsm-specific). `testcontainers[mongodb]` for repository/router tests.

**Spec:** `docs/tasks/devops-control-panel-schema.md` section 4 (`logs` collection design, indexes, retention) is the source spec. `/Users/hoangdieu/.claude/plans/rosy-juggling-pine.md` Phase 2 is the slice this implements — refined here against what Phase 1's actual code looks like (see "Deviations from the master plan" below).

## Global Constraints

- Same module-boundary rule as Phase 1: cross-module imports only via `public.py` or `<module>.constants` directly, enforced by `check_module_boundaries.py` (auto-covers `app/modules/audit/`) — `.importlinter` needs a new `audit-facade` stanza (doesn't auto-extend) and `mongo` needs to join `root-is-mechanism`'s and `integrations-are-leaves`'s lists alongside `cache`/`queue`/`storage`/`dx_core`.
- `log_event` must never raise — every call site in Phase 1's services already commits successfully before calling it; a Mongo outage must not turn a working project-creation into a 500.
- `list_logs` must propagate real failures — the router's exception handling (existing `AppError`/generic-500 machinery) already covers this correctly as long as the repository doesn't swallow errors.
- camelCase on the wire via `FrozenModel`, same as every other schema.

## Deviations from the master plan (found while reading the actual code — flagging per this skill's "no placeholders" self-review, not silently drifting)

1. **`MONGODB_URL` does NOT go in root `app/config.py`.** The master plan's Phase 2 line said it would, but the *actual* closest precedent (Redis) lives in `integrations/cache/config.py` as its own `CacheConfig(env_prefix="CACHE__")`, not in the root `Config`. Root `Config` only holds `DATABASE_URL` (Postgres, the app's primary transactional store, needed everywhere) — Mongo plays the same architectural role as Redis here (an integration), not a second primary store. Following `CacheConfig`'s exact shape: `app/integrations/mongo/config.py`'s `MongoConfig(env_prefix="MONGO__")` with `URL` and `DATABASE_NAME`.
2. **`AbstractAuditLogRepository` does NOT extend `AbstractRepository[EntityT, IdT]`.** Confirmed via the same reasoning `dx_core/repository.py` already uses to opt out (single-row-per-user store doesn't fit `get_by_id`/`list_page`'s generic shape) — an append-only, time-range-queried collection is an equally poor fit. Bespoke `insert()`/`list_page(*, filters...)` contract instead.
3. **Retrofitting Phase 1's services needs an `actor_id`/`actor_email` parameter that doesn't exist yet.** The spec's `logs.actor` field needs to know who acted; `CreateProject.execute()` etc. currently take no actor. Router already resolves the caller via `require_permission(...)` (bound to `_user: UserRead`) — Task 6 threads `_user.id`/`_user.email` from router into each service's `execute()` call.

## File Structure

```
backend/app/integrations/mongo/
  __init__.py, client.py, config.py, constants.py, exceptions.py, dependencies.py
backend/app/modules/audit/
  __init__.py, constants.py, schemas.py, repository.py, public.py, dependencies.py, router.py
backend/tests/audit/
  __init__.py, test_public.py, test_router.py
backend/tests/mongo_conftest.py  (MongoDbContainer fixture, imported by tests/conftest.py)
frontend/src/modules/audit-log/
  index.ts, api/fetchers.ts, api/query-keys.ts, hooks/use-audit-logs.ts, ui/audit-log-page-content.tsx
frontend/src/app/[locale]/(dashboard)/admin/audit-log/page.tsx, loading.tsx
frontend/locales/{en,vi}/modules/audit-log.json
```

**Modified:** `backend/pyproject.toml` (done — Task 0, already committed), `backend/docker-compose.yml` (add `mongo` service), `backend/app/lifespan.py`, `backend/app/main.py`, `backend/.importlinter`, `backend/tests/conftest.py`, `backend/app/modules/rbac/constants.py` (1 new permission), all 6 of Phase 1's `services/*.py` + `dependencies.py` + `router.py`, `frontend/src/shared/constants/{routes,permissions,api}.ts`, `dashboard-sidebar.tsx`, `i18n/request.ts`, `locales/{en,vi}/common.json`.

---

### Task 1: `app/integrations/mongo/` — Motor client + lifespan wiring

**Files:** Create `backend/app/integrations/mongo/{__init__.py,client.py,config.py,constants.py,exceptions.py,dependencies.py}`. Modify `backend/app/lifespan.py`, `backend/docker-compose.yml`, `backend/.importlinter`.

**Interfaces:** Produces `MongoConnectionFactory.create() -> AsyncIOMotorClient`, `get_mongo_database(request) -> AsyncIOMotorDatabase` — consumed by Task 3's repository.

- [ ] **Step 1: `config.py`**
```python
"""Settings owned by the mongo integration."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class MongoConfig(BaseSettings):
    """Environment driven settings for MongoDB."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="MONGO__", extra="ignore")

    URL: str = "mongodb://localhost:27017"
    DATABASE_NAME: str = "itsm"


mongo_settings = MongoConfig()
```

- [ ] **Step 2: `constants.py`**
```python
"""Constants owned by the mongo integration."""

from enum import StrEnum


class MongoErrorCode(StrEnum):
    """Stable error codes raised by this integration."""

    UNAVAILABLE = "mongo_unavailable"
```

- [ ] **Step 3: `exceptions.py`**
```python
"""Errors owned by the mongo integration."""

from app.core.exceptions import IntegrationError
from app.integrations.mongo.constants import MongoErrorCode


class MongoUnavailable(IntegrationError):
    """Raised when MongoDB cannot be reached for an operation that cannot degrade silently."""

    code = MongoErrorCode.UNAVAILABLE
    message = "Log store unavailable"
```

- [ ] **Step 4: `client.py`**
```python
"""Motor client factory. Called once, from lifespan.py — mirrors
RedisConnectionFactory in integrations/cache/client.py."""

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.base.markers import integration
from app.integrations.mongo.config import mongo_settings


class MongoConnectionFactory:
    """Builds the process wide Motor client backed by MongoDB's own connection pool."""

    @staticmethod
    @integration
    def create() -> AsyncIOMotorClient:
        """Build a Motor client. Motor/pymongo pool internally — no extra pool config needed here."""
        return AsyncIOMotorClient(mongo_settings.URL)

    @staticmethod
    @integration
    def database(client: AsyncIOMotorClient) -> AsyncIOMotorDatabase:
        """Return the app's database handle off a client built by create()."""
        return client[mongo_settings.DATABASE_NAME]
```

- [ ] **Step 5: `dependencies.py`**
```python
"""Dependency wiring for the mongo integration."""

from fastapi import Request
from motor.motor_asyncio import AsyncIOMotorDatabase


async def get_mongo_database(request: Request) -> AsyncIOMotorDatabase:
    """Provide the process wide database handle."""
    return request.app.state.mongo_db
```

- [ ] **Step 6: `__init__.py`** — empty.

- [ ] **Step 7: Wire into `lifespan.py`**
```python
# backend/app/lifespan.py — full replacement
"""Ownership of every shared resource, bound to the application lifecycle."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.integrations.cache.client import RedisConnectionFactory
from app.integrations.mongo.client import MongoConnectionFactory
from app.integrations.queue.client import Broker
from app.integrations.storage.client import StorageClient
from app.modules.audit.repository import MongoAuditLogRepository

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create pools on startup and release them on shutdown."""
    engine = create_async_engine(
        str(settings.DATABASE_URL),
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_pre_ping=True,
        connect_args={"server_settings": {"statement_timeout": str(settings.DB_STATEMENT_TIMEOUT_MS)}},
    )
    app.state.engine = engine
    app.state.session_factory = async_sessionmaker(engine, expire_on_commit=False)
    app.state.redis = RedisConnectionFactory.create()
    app.state.broker = Broker()
    await app.state.broker.connect()
    app.state.storage = StorageClient()
    app.state.mongo_client = MongoConnectionFactory.create()
    app.state.mongo_db = MongoConnectionFactory.database(app.state.mongo_client)
    await MongoAuditLogRepository(app.state.mongo_db).ensure_indexes()

    logger.info("application resources initialized")
    yield

    await app.state.redis.aclose()
    await app.state.broker.close()
    await app.state.storage.close()
    app.state.mongo_client.close()
    await engine.dispose()
    logger.info("application resources released")
```
(`MongoAuditLogRepository`/`ensure_indexes` don't exist yet — Task 3 adds them; this step's own verification runs after Task 3, not now. Note it here since it's the one lifespan touches once.)

- [ ] **Step 8: Add `mongo` service to `docker-compose.yml`** (for other environments/CI — this developer's own local Mongo is the already-running shared `mongo` container, not this compose stack)
```yaml
# backend/docker-compose.yml — new service, alongside postgres/redis/rabbitmq/minio
  mongo:
    image: mongo:7
    ports:
      - "27017:27017"
    volumes:
      - mongodata:/data/db
```
And add `mongodata:` to the `volumes:` block at the bottom.

- [ ] **Step 9: `.importlinter` — add `mongo` to the two integration contracts**
```ini
# backend/.importlinter — root-is-mechanism's forbidden_modules gains a line
    app.integrations.mongo
# integrations-are-leaves's source_modules gains a line
    app.integrations.mongo
```

- [ ] **Step 10: Sanity-check imports (Task 3 will complete the real lifespan verification)**
Run: `cd backend && uv run python -c "from app.integrations.mongo import client, config, constants, exceptions, dependencies"`
Expected: exits 0.

- [ ] **Step 11: Commit**
```bash
git add backend/app/integrations/mongo backend/app/lifespan.py backend/docker-compose.yml backend/.importlinter
git commit -m "feat(mongo): add Motor client integration and lifespan wiring"
```

---

### Task 2: `app/modules/audit/` scaffolding — constants, schemas

**Files:** Create `backend/app/modules/audit/{__init__.py,constants.py,schemas.py}`.

**Interfaces:** Produces `AuditEventType`, `AuditSource`, `AuditSeverity` (StrEnum), `AuditActor`/`AuditLogEntry` (FrozenModel) — consumed by Task 3's repository and Task 4's facade.

- [ ] **Step 1: `constants.py`**
```python
"""Constants and enums owned by the audit module."""

from enum import StrEnum


class AuditCollections:
    """Mongo collection names owned by this module."""

    LOGS = "logs"


class AuditEventType(StrEnum):
    """What kind of event a log entry records."""

    AUDIT = "AUDIT"
    INCIDENT_DETECTION = "INCIDENT_DETECTION"
    NOTIFICATION_SENT = "NOTIFICATION_SENT"


class AuditSource(StrEnum):
    """Which system produced the event."""

    CLOUDFLARE = "CLOUDFLARE"
    LOKI = "LOKI"
    SYSTEM = "SYSTEM"
    USER_ACTION = "USER_ACTION"


class AuditSeverity(StrEnum):
    """Severity of a log entry."""

    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AuditLimits:
    """Numeric limits owned by the audit module."""

    DEFAULT_PAGE_SIZE = 50


class AuditRetention:
    """TTL retention windows, per spec section 4 — AUDIT is shorter lived than
    incident/notification history. Applied via a per-document `expire_at`
    field (not a fixed TTL on created_at) since Mongo TTL indexes apply one
    duration per field, not per document value."""

    AUDIT_TTL_DAYS = 180
    OTHER_TTL_DAYS = 365
```

- [ ] **Step 2: `schemas.py`**
```python
"""Schemas for the audit module."""

from datetime import datetime
from uuid import UUID

from app.core.models import FrozenModel
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource


class AuditActor(FrozenModel):
    """Who performed the action, when known — absent for system-detected events."""

    user_id: UUID | None = None
    email: str | None = None


class AuditLogEntry(FrozenModel):
    """One row of the `logs` collection, as read back for the viewer."""

    id: str
    type: AuditEventType
    project_id: UUID | None = None
    environment_id: UUID | None = None
    source: AuditSource
    actor: AuditActor
    action: str
    severity: AuditSeverity
    incident_id: str | None = None
    message: str
    payload: dict = {}
    timestamp: datetime
    created_at: datetime
```

- [ ] **Step 3: `__init__.py`** — empty.

- [ ] **Step 4: Sanity-check imports**
Run: `cd backend && uv run python -c "from app.modules.audit import constants, schemas"`
Expected: exits 0.

- [ ] **Step 5: Commit**
```bash
git add backend/app/modules/audit/__init__.py backend/app/modules/audit/constants.py backend/app/modules/audit/schemas.py
git commit -m "feat(audit): scaffold constants and schemas"
```

---

### Task 3: `repository.py` — Mongo CRUD + indexes

No independent test cycle here (matches Phase 1's Task 4 precedent: SQL repositories aren't unit-tested standalone either) — exercised for real by Task 4/5's tests, which run against a real ephemeral MongoDB via `testcontainers[mongodb]` since Motor has no meaningful Fake.

**Files:** Create `backend/app/modules/audit/repository.py`.

**Interfaces:** Produces `AbstractAuditLogRepository` (bespoke contract — NOT `AbstractRepository[T,Id]`, see "Deviations" above) with `insert()`, `list_page()`, `ensure_indexes()` — consumed by Task 4's facade and Task 1 Step 7's lifespan startup.

- [ ] **Step 1: Write `repository.py`**
```python
"""Single access path to the logs collection."""

from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from uuid import UUID

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.base.markers import database
from app.modules.audit.constants import AuditCollections, AuditEventType, AuditRetention, AuditSeverity, AuditSource
from app.modules.audit.schemas import AuditActor, AuditLogEntry


class AbstractAuditLogRepository(ABC):
    """Contract a caller depends on instead of the concrete Motor class below.
    Not AbstractRepository[T, Id] — an append-only, time-range-queried
    collection has no single-id lookup use case here, see plan's
    'Deviations from the master plan'."""

    @abstractmethod
    async def insert(
        self,
        *,
        type: AuditEventType,
        source: AuditSource,
        action: str,
        severity: AuditSeverity,
        message: str,
        project_id: UUID | None,
        environment_id: UUID | None,
        actor: AuditActor,
        incident_id: str | None,
        payload: dict,
    ) -> None:
        """Insert one log entry."""
        raise NotImplementedError

    @abstractmethod
    async def list_page(
        self,
        *,
        project_id: UUID | None,
        environment_id: UUID | None,
        type: AuditEventType | None,
        since: datetime | None,
        until: datetime | None,
        limit: int,
        offset: int,
    ) -> tuple[list[AuditLogEntry], int]:
        """Return one page of log entries matching the given filters, newest first."""
        raise NotImplementedError

    @abstractmethod
    async def ensure_indexes(self) -> None:
        """Create indexes idempotently. Called once from lifespan.py on startup."""
        raise NotImplementedError


class MongoAuditLogRepository(AbstractAuditLogRepository):
    """Motor implementation. Every read/write of the logs collection goes through this class."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._collection = db[AuditCollections.LOGS]

    @database
    async def insert(
        self,
        *,
        type: AuditEventType,
        source: AuditSource,
        action: str,
        severity: AuditSeverity,
        message: str,
        project_id: UUID | None,
        environment_id: UUID | None,
        actor: AuditActor,
        incident_id: str | None,
        payload: dict,
    ) -> None:
        """Insert one log entry, with a computed expire_at for the TTL index."""
        now = datetime.now(UTC)
        ttl_days = (
            AuditRetention.AUDIT_TTL_DAYS if type == AuditEventType.AUDIT else AuditRetention.OTHER_TTL_DAYS
        )
        await self._collection.insert_one(
            {
                "type": type.value,
                "project_id": str(project_id) if project_id else None,
                "environment_id": str(environment_id) if environment_id else None,
                "source": source.value,
                "actor": {
                    "user_id": str(actor.user_id) if actor.user_id else None,
                    "email": actor.email,
                },
                "action": action,
                "severity": severity.value,
                "incident_id": incident_id,
                "message": message,
                "payload": payload,
                "timestamp": now,
                "created_at": now,
                "expire_at": now + timedelta(days=ttl_days),
            }
        )

    @database
    async def list_page(
        self,
        *,
        project_id: UUID | None,
        environment_id: UUID | None,
        type: AuditEventType | None,
        since: datetime | None,
        until: datetime | None,
        limit: int,
        offset: int,
    ) -> tuple[list[AuditLogEntry], int]:
        """Return one page of log entries matching the given filters, newest first."""
        query: dict = {}
        if project_id is not None:
            query["project_id"] = str(project_id)
        if environment_id is not None:
            query["environment_id"] = str(environment_id)
        if type is not None:
            query["type"] = type.value
        if since is not None or until is not None:
            query["timestamp"] = {
                **({"$gte": since} if since is not None else {}),
                **({"$lte": until} if until is not None else {}),
            }

        total = await self._collection.count_documents(query)
        cursor = self._collection.find(query).sort("timestamp", -1).skip(offset).limit(limit)
        items = [self._to_entry(doc) async for doc in cursor]
        return items, total

    @database
    async def ensure_indexes(self) -> None:
        """Create indexes idempotently. Safe to call on every startup."""
        await self._collection.create_index([("project_id", 1), ("environment_id", 1), ("timestamp", -1)])
        await self._collection.create_index([("type", 1), ("timestamp", -1)])
        await self._collection.create_index("incident_id")
        await self._collection.create_index("expire_at", expireAfterSeconds=0)

    @staticmethod
    def _to_entry(doc: dict) -> AuditLogEntry:
        """Map a raw Mongo document to the wire schema."""
        actor_doc = doc["actor"]
        return AuditLogEntry(
            id=str(doc["_id"]),
            type=AuditEventType(doc["type"]),
            project_id=UUID(doc["project_id"]) if doc.get("project_id") else None,
            environment_id=UUID(doc["environment_id"]) if doc.get("environment_id") else None,
            source=AuditSource(doc["source"]),
            actor=AuditActor(
                user_id=UUID(actor_doc["user_id"]) if actor_doc.get("user_id") else None,
                email=actor_doc.get("email"),
            ),
            action=doc["action"],
            severity=AuditSeverity(doc["severity"]),
            incident_id=doc.get("incident_id"),
            message=doc["message"],
            payload=doc.get("payload", {}),
            timestamp=doc["timestamp"],
            created_at=doc["created_at"],
        )
```

- [ ] **Step 2: Sanity-check imports**
Run: `cd backend && uv run python -c "from app.modules.audit.repository import AbstractAuditLogRepository, MongoAuditLogRepository"`
Expected: exits 0.

- [ ] **Step 3: Commit**
```bash
git add backend/app/modules/audit/repository.py
git commit -m "feat(audit): add Mongo repository with indexes"
```

---

### Task 4: `public.py` facade — `log_event` (fire-and-forget) + `list_logs` (TDD, real MongoDB)

**Files:** Create `backend/app/modules/audit/dependencies.py`, `backend/app/modules/audit/public.py`, `backend/tests/audit/__init__.py`, `backend/tests/audit/test_public.py`. Modify `backend/tests/conftest.py` (add `mongo_url`/`mongo_db` fixtures).

**Interfaces:** Consumes `AbstractAuditLogRepository` (Task 3). Produces `AuditApi.log_event(...) -> None` (never raises), `AuditApi.list_logs(...) -> tuple[list[AuditLogEntry], int]` (raises `MongoUnavailable` on real failure), `get_audit_api` — consumed by Task 5's router and Task 6's Phase-1-service retrofit.

- [ ] **Step 1: Add Mongo fixtures to `conftest.py`**
```python
# backend/tests/conftest.py — add these imports at the top, alongside the existing ones
from motor.motor_asyncio import AsyncIOMotorClient
from testcontainers.mongodb import MongoDbContainer
```
```python
# backend/tests/conftest.py — add these fixtures, after the existing postgres_url/engine fixtures
@pytest.fixture(scope="session")
def mongo_url() -> AsyncIterator[str]:
    """Start one MongoDB container for the whole test session."""
    with MongoDbContainer("mongo:7") as container:
        yield container.get_connection_url()


@pytest.fixture
async def mongo_db(mongo_url: str) -> AsyncIterator[AsyncIOMotorDatabase]:
    """Provide a Motor database backed by the test container, dropped after each test."""
    client = AsyncIOMotorClient(mongo_url)
    db = client["itsm_test"]
    yield db
    await client.drop_database("itsm_test")
    client.close()
```
(`AsyncIOMotorDatabase` needs importing too: `from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase`.)

- [ ] **Step 2: Write the failing tests**
```python
"""Integration tests for app.modules.audit.public — real MongoDB via testcontainers."""

from uuid import uuid4

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditApi
from app.modules.audit.repository import MongoAuditLogRepository
from app.modules.audit.schemas import AuditActor


class TestLogEvent:
    async def test_writes_a_retrievable_entry(self, mongo_db: AsyncIOMotorDatabase) -> None:
        api = AuditApi(MongoAuditLogRepository(mongo_db))
        actor = AuditActor(user_id=uuid4(), email="actor@example.com")

        await api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action="PROJECT_CREATED",
            severity=AuditSeverity.INFO,
            message="Project Website A created",
            actor=actor,
        )

        items, total = await api.list_logs(limit=10, offset=0)
        assert total == 1
        assert items[0].action == "PROJECT_CREATED"
        assert items[0].actor.email == "actor@example.com"

    async def test_never_raises_when_mongo_unreachable(self) -> None:
        unreachable_client = AsyncIOMotorClient(
            "mongodb://localhost:1/", serverSelectionTimeoutMS=200
        )
        api = AuditApi(MongoAuditLogRepository(unreachable_client["itsm_test_unreachable"]))

        await api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action="PROJECT_CREATED",
            severity=AuditSeverity.INFO,
            message="should not raise",
            actor=AuditActor(),
        )  # no exception = pass

        unreachable_client.close()


class TestListLogs:
    async def test_filters_by_project_id(self, mongo_db: AsyncIOMotorDatabase) -> None:
        api = AuditApi(MongoAuditLogRepository(mongo_db))
        project_a, project_b = uuid4(), uuid4()
        for project_id, action in ((project_a, "A_EVENT"), (project_b, "B_EVENT")):
            await api.log_event(
                type=AuditEventType.AUDIT,
                source=AuditSource.USER_ACTION,
                action=action,
                severity=AuditSeverity.INFO,
                message="x",
                project_id=project_id,
                actor=AuditActor(),
            )

        items, total = await api.list_logs(project_id=project_a, limit=10, offset=0)

        assert total == 1
        assert items[0].action == "A_EVENT"

    async def test_raises_mongo_unavailable_when_unreachable(self) -> None:
        from app.integrations.mongo.exceptions import MongoUnavailable
        import pytest

        unreachable_client = AsyncIOMotorClient(
            "mongodb://localhost:1/", serverSelectionTimeoutMS=200
        )
        api = AuditApi(MongoAuditLogRepository(unreachable_client["itsm_test_unreachable"]))

        with pytest.raises(MongoUnavailable):
            await api.list_logs(limit=10, offset=0)

        unreachable_client.close()
```

- [ ] **Step 3: Run tests to verify they fail**
Run: `cd backend && uv run pytest tests/audit/test_public.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.modules.audit.public'`

- [ ] **Step 4: Write `dependencies.py`**
```python
"""Dependency wiring for the audit module."""

from fastapi import Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.integrations.mongo.dependencies import get_mongo_database
from app.modules.audit.repository import MongoAuditLogRepository


async def get_audit_repository(
    db: AsyncIOMotorDatabase = Depends(get_mongo_database),
) -> MongoAuditLogRepository:
    """Provide the repository. The one place the concrete class is named."""
    return MongoAuditLogRepository(db)
```

- [ ] **Step 5: Write `public.py`**
```python
"""Contract exposed to other modules. This is the ONLY file another module
may import from audit — enforced by scripts/check_module_boundaries.py.
"""

import logging
from datetime import datetime
from uuid import UUID

from fastapi import Depends
from pymongo.errors import PyMongoError

from app.core.base.markers import facade
from app.integrations.mongo.exceptions import MongoUnavailable
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.dependencies import get_audit_repository
from app.modules.audit.repository import AbstractAuditLogRepository, MongoAuditLogRepository
from app.modules.audit.schemas import AuditActor, AuditLogEntry

__all__ = ["AuditActor", "AuditLogEntry", "AuditApi", "get_audit_api"]

logger = logging.getLogger(__name__)


class AuditApi:
    """Facade over the logs collection for every other module."""

    def __init__(self, repository: AbstractAuditLogRepository) -> None:
        self._repository = repository

    @facade
    async def log_event(
        self,
        *,
        type: AuditEventType,
        source: AuditSource,
        action: str,
        severity: AuditSeverity,
        message: str,
        actor: AuditActor,
        project_id: UUID | None = None,
        environment_id: UUID | None = None,
        incident_id: str | None = None,
        payload: dict | None = None,
    ) -> None:
        """Record an event. Fire-and-forget: a Mongo outage degrades to a
        logged warning, never an exception into the caller — the caller's
        own database transaction already committed by the time this runs
        (see Task 6's retrofit), so there is nothing left to roll back."""
        try:
            await self._repository.insert(
                type=type,
                source=source,
                action=action,
                severity=severity,
                message=message,
                project_id=project_id,
                environment_id=environment_id,
                actor=actor,
                incident_id=incident_id,
                payload=payload or {},
            )
        except PyMongoError:
            logger.warning("audit log write failed, degrading silently", exc_info=True)

    @facade
    async def list_logs(
        self,
        *,
        project_id: UUID | None = None,
        environment_id: UUID | None = None,
        type: AuditEventType | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AuditLogEntry], int]:
        """Return one page of log entries. Unlike log_event, this must not
        swallow a Mongo outage — a broken log viewer should show an error,
        not silently claim there are no logs."""
        try:
            return await self._repository.list_page(
                project_id=project_id,
                environment_id=environment_id,
                type=type,
                since=since,
                until=until,
                limit=limit,
                offset=offset,
            )
        except PyMongoError as exc:
            raise MongoUnavailable() from exc


async def get_audit_api(
    repository: MongoAuditLogRepository = Depends(get_audit_repository),
) -> AuditApi:
    """Provide the facade to other modules."""
    return AuditApi(repository)
```

- [ ] **Step 6: Run tests to verify they pass**
Run: `cd backend && uv run pytest tests/audit/test_public.py -v`
Expected: 4 passed. (The unreachable-Mongo tests take up to ~200ms each due to `serverSelectionTimeoutMS`.)

- [ ] **Step 7: Commit**
```bash
git add backend/tests/conftest.py backend/app/modules/audit/dependencies.py backend/app/modules/audit/public.py backend/tests/audit/__init__.py backend/tests/audit/test_public.py
git commit -m "feat(audit): add log_event/list_logs facade with fire-and-forget writes"
```

---

### Task 5: `router.py` — `GET /audit-logs` + RBAC permission (TDD, real MongoDB + Postgres)

**Files:** Create `backend/app/modules/audit/router.py`, `backend/tests/audit/test_router.py`. Modify `backend/tests/conftest.py` (wire `mongo_db` into the shared `client` fixture's dependency overrides — every router test needs `get_mongo_database` pointed at the test container instead of the real dev Mongo, the same reason `client` already overrides `get_cache`), `backend/app/modules/rbac/constants.py` (1 new permission).

**Interfaces:** Consumes `AuditApi`/`get_audit_api` (Task 4). Produces `router` — consumed by Task 7's `main.py`.

- [ ] **Step 1: Wire `mongo_db` into the `client` fixture**
```python
# backend/tests/conftest.py — client fixture gains a `mongo_db` parameter and one more override
@pytest.fixture
async def client(engine, mongo_db: AsyncIOMotorDatabase) -> AsyncIterator[AsyncClient]:
    ...  # unchanged body up through the existing overrides, then add:
    from app.integrations.mongo.dependencies import get_mongo_database

    async def override_get_mongo_database() -> AsyncIOMotorDatabase:
        return mongo_db

    app.dependency_overrides[get_mongo_database] = override_get_mongo_database
    ...  # rest unchanged (transport/yield/cleanup)
```
Every existing test using `client` now also starts the (session-scoped, started-once) Mongo testcontainer — same cost model as the existing unconditional Redis flush in that fixture.

- [ ] **Step 2: Add the RBAC permission**
```python
# backend/app/modules/rbac/constants.py — append to RbacPermissionCatalog.CATALOG
        ("audit_log", "read", "permissions.audit_log.read"),
```

- [ ] **Step 3: Write the failing router tests**
```python
"""Integration tests for app.modules.audit.router — real Postgres + MongoDB via testcontainers."""

from uuid import UUID

from httpx import AsyncClient
from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.security import JwtCodec
from app.modules.auth.config import auth_settings
from app.modules.auth.constants import AuthCookies
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditApi
from app.modules.audit.repository import MongoAuditLogRepository
from app.modules.audit.schemas import AuditActor
from app.modules.rbac.models import Permission, Role, RolePermission, UserRole
from app.modules.users.models import User


async def _login_with_permissions(
    client: AsyncClient, engine: AsyncEngine, *, permissions: list[tuple[str, str]]
) -> UUID:
    async with engine.begin() as conn:
        user_result = await conn.execute(
            insert(User).values(
                email="actor@example.com",
                name="Actor",
                status="active",
                external_user_id="dx-actor",
                employee_code=None,
                email_confirmed=True,
            )
        )
        user_id = user_result.inserted_primary_key[0]
        role_result = await conn.execute(insert(Role).values(name="test-role", is_system=False))
        role_id = role_result.inserted_primary_key[0]
        for resource, action in permissions:
            perm_result = await conn.execute(
                insert(Permission).values(resource=resource, action=action, description_key="x")
            )
            permission_id = perm_result.inserted_primary_key[0]
            await conn.execute(insert(RolePermission).values(role_id=role_id, permission_id=permission_id))
        await conn.execute(insert(UserRole).values(user_id=user_id, role_id=role_id))

    token = JwtCodec.encode(
        {"sub": str(user_id), "type": "access", "jti": "test-jti"},
        secret=auth_settings.JWT_SECRET,
        ttl_seconds=3600,
    )
    client.cookies.set(AuthCookies.ACCESS_TOKEN, token)
    return user_id


class TestListAuditLogs:
    async def test_requires_audit_log_read_permission(
        self, client: AsyncClient, engine: AsyncEngine
    ) -> None:
        await _login_with_permissions(client, engine, permissions=[])

        response = await client.get("/api/v1/audit-logs")

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "rbac_permission_denied"

    async def test_lists_entries_with_permission(
        self, client: AsyncClient, engine: AsyncEngine, mongo_db: AsyncIOMotorDatabase
    ) -> None:
        await _login_with_permissions(client, engine, permissions=[("audit_log", "read")])
        api = AuditApi(MongoAuditLogRepository(mongo_db))
        await api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action="PROJECT_CREATED",
            severity=AuditSeverity.INFO,
            message="seeded for router test",
            actor=AuditActor(),
        )

        response = await client.get("/api/v1/audit-logs")

        body = response.json()
        assert response.status_code == 200
        assert body["data"]["total"] == 1
        assert body["data"]["items"][0]["action"] == "PROJECT_CREATED"
```

- [ ] **Step 4: Run tests to verify they fail**
Run: `cd backend && uv run pytest tests/audit/test_router.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.modules.audit.router'`

- [ ] **Step 5: Write `router.py`**
```python
"""HTTP entry points of the audit module. Router thinness (rule #10): every
function below only translates HTTP -> use-case call and wraps the result in
ApiResponse — no formatting/business logic lives here.
"""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.core.models import ApiResponse
from app.core.pagination import Page, PaginationParams, pagination_params
from app.modules.audit.constants import AuditEventType
from app.modules.audit.public import AuditApi, AuditLogEntry, get_audit_api
from app.modules.rbac.public import require_permission
from app.modules.users.public import UserRead

router = APIRouter(tags=["audit"])


@router.get("/audit-logs")
async def list_audit_logs(
    project_id: UUID | None = Query(None),
    environment_id: UUID | None = Query(None),
    type: AuditEventType | None = Query(None),
    since: datetime | None = Query(None),
    until: datetime | None = Query(None),
    pagination: PaginationParams = Depends(pagination_params),
    audit_api: AuditApi = Depends(get_audit_api),
    _user: UserRead = Depends(require_permission("audit_log", "read")),
) -> ApiResponse[Page[AuditLogEntry]]:
    """List audit log entries, newest first, optionally filtered."""
    items, total = await audit_api.list_logs(
        project_id=project_id,
        environment_id=environment_id,
        type=type,
        since=since,
        until=until,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    page = Page[AuditLogEntry](items=items, total=total, limit=pagination.limit, offset=pagination.offset)
    return ApiResponse[Page[AuditLogEntry]](success=True, data=page)
```

- [ ] **Step 6: Run tests to verify they pass**
Run: `cd backend && uv run pytest tests/audit/ -v`
Expected: 6 passed (2 from Task 4's `test_public.py` unreachable-mongo cases + 2 from its happy-path cases + 2 from this task).

- [ ] **Step 7: Commit**
```bash
git add backend/tests/conftest.py backend/app/modules/rbac/constants.py backend/app/modules/audit/router.py backend/tests/audit/test_router.py
git commit -m "feat(audit): add GET /audit-logs endpoint and permission"
```

---

### Task 6: Retrofit Phase 1's 6 mutations to log audit events (TDD, Fake-based)

**Files:** Modify all 6 of `backend/app/modules/projects/services/{create,update,delete}_{project,environment}.py`, `backend/app/modules/projects/dependencies.py`, `backend/app/modules/projects/router.py`, `backend/tests/projects/test_services.py`, `backend/tests/projects/test_router.py`.

**Interfaces:** Consumes `AuditApi`/`AuditActor`/`get_audit_api` (Task 4). Every mutation's `execute()` gains `*, actor_id: UUID, actor_email: str`.

- [ ] **Step 1: Update `test_services.py` — add `FakeAuditApi`, update every mutation test's call site**

Add near the top, after the other Fakes:
```python
class FakeAuditApi:
    """Duck-typed stand-in for app.modules.audit.public.AuditApi — records every
    call instead of writing to Mongo, so tests can assert an event was logged."""

    def __init__(self) -> None:
        self.events: list[dict] = []

    async def log_event(self, **kwargs) -> None:
        self.events.append(kwargs)

    async def list_logs(self, **kwargs) -> tuple[list, int]:
        return [], 0
```

Update every `CreateProject(uow)` / `UpdateProject(uow)` / ... call site to `CreateProject(uow, audit_api)` (etc.), and every `.execute(...)` call to add `actor_id=uuid4(), actor_email="actor@example.com"`. Concretely, `TestCreateProject` becomes:
```python
class TestCreateProject:
    async def test_creates_project_with_configured_default_links(self, monkeypatch) -> None:
        monkeypatch.setattr(projects_settings, "DEFAULT_JIRA_URL", "https://jira.weup.vn")
        monkeypatch.setattr(projects_settings, "DEFAULT_GIT_URL", "https://git.weup.vn")
        uow = FakeProjectsUnitOfWork()
        audit_api = FakeAuditApi()

        project = await CreateProject(uow, audit_api).execute(
            "Website A", "Marketing site", actor_id=uuid4(), actor_email="actor@example.com"
        )

        assert project.name == "Website A"
        links = await uow.project_links.list_for_project(project.id)
        assert {link.type for link in links} == {ProjectLinkType.JIRA, ProjectLinkType.GIT}
        assert all(link.is_default for link in links)
        assert uow.commits == 1
        assert audit_api.events[0]["action"] == "PROJECT_CREATED"

    async def test_creates_project_with_no_default_links_when_unconfigured(self, monkeypatch) -> None:
        monkeypatch.setattr(projects_settings, "DEFAULT_JIRA_URL", "")
        monkeypatch.setattr(projects_settings, "DEFAULT_GIT_URL", "")
        uow = FakeProjectsUnitOfWork()

        project = await CreateProject(uow, FakeAuditApi()).execute(
            "Website B", None, actor_id=uuid4(), actor_email="actor@example.com"
        )

        links = await uow.project_links.list_for_project(project.id)
        assert links == []
```
Apply the same two changes (constructor gains `audit_api`, `execute()` gains `actor_id=uuid4(), actor_email="actor@example.com"`) to every remaining test in `TestUpdateProject`, `TestDeleteProject`, `TestCreateEnvironment`, `TestUpdateEnvironment`, `TestDeleteEnvironment` — 15 call sites total across those 5 classes, each following the identical two-line change. (Link tests — `TestCreateProjectLink`/`TestUpdateProjectLink`/`TestDeleteProjectLink` — are unaffected; the master plan only retrofits project/environment mutations, not links.)

- [ ] **Step 2: Run tests to verify they fail**
Run: `cd backend && uv run pytest tests/projects/test_services.py -v`
Expected: FAIL — `TypeError: CreateProject.__init__() takes 2 positional arguments but 3 were given` (and similar for every other service).

- [ ] **Step 3: Update the 6 service files**
```python
# backend/app/modules/projects/services/create_project.py — full replacement
from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.projects.rules import ProjectsRules
from app.modules.projects.schemas import ProjectRead
from app.modules.projects.uow import AbstractProjectsUnitOfWork


class CreateProject(AbstractUseCase):
    """Create a project, then attach the configured default Jira/Git links
    (ProjectsRules.default_links) — see spec's project_links note: these are
    seeded values, not a template table, so nothing here is admin-editable."""

    def __init__(self, uow: AbstractProjectsUnitOfWork, audit_api: AuditApi) -> None:
        self._uow = uow
        self._audit_api = audit_api

    @use_case
    async def execute(
        self, name: str, description: str | None, *, actor_id: UUID, actor_email: str
    ) -> ProjectRead:
        project = await self._uow.projects.create(name=name, description=description, created_by=None)
        for link_type, link_name, url in ProjectsRules.default_links():
            await self._uow.project_links.create(
                project_id=project.id, type=link_type, name=link_name, url=url, is_default=True
            )
        await self._uow.commit()
        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action="PROJECT_CREATED",
            severity=AuditSeverity.INFO,
            message=f"Project '{project.name}' created",
            project_id=project.id,
            actor=AuditActor(user_id=actor_id, email=actor_email),
        )
        return project
```
```python
# backend/app/modules/projects/services/update_project.py — full replacement
from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.projects.exceptions import ProjectNotFound
from app.modules.projects.schemas import ProjectRead
from app.modules.projects.uow import AbstractProjectsUnitOfWork


class UpdateProject(AbstractUseCase):
    """Rename and/or redescribe a project."""

    def __init__(self, uow: AbstractProjectsUnitOfWork, audit_api: AuditApi) -> None:
        self._uow = uow
        self._audit_api = audit_api

    @use_case
    async def execute(
        self,
        project_id: UUID,
        *,
        name: str | None,
        description: str | None,
        actor_id: UUID,
        actor_email: str,
    ) -> ProjectRead:
        if await self._uow.projects.get_by_id(project_id) is None:
            raise ProjectNotFound()
        updated = await self._uow.projects.update(project_id, name=name, description=description)
        await self._uow.commit()
        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action="PROJECT_UPDATED",
            severity=AuditSeverity.INFO,
            message=f"Project '{updated.name}' updated",
            project_id=updated.id,
            actor=AuditActor(user_id=actor_id, email=actor_email),
        )
        return updated
```
```python
# backend/app/modules/projects/services/delete_project.py — full replacement
from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.projects.exceptions import ProjectNotFound
from app.modules.projects.uow import AbstractProjectsUnitOfWork


class DeleteProject(AbstractUseCase):
    """Delete a project. Its environments and links cascade at the DB level (ondelete=CASCADE)."""

    def __init__(self, uow: AbstractProjectsUnitOfWork, audit_api: AuditApi) -> None:
        self._uow = uow
        self._audit_api = audit_api

    @use_case
    async def execute(self, project_id: UUID, *, actor_id: UUID, actor_email: str) -> None:
        project = await self._uow.projects.get_by_id(project_id)
        if project is None:
            raise ProjectNotFound()
        await self._uow.projects.delete(project_id)
        await self._uow.commit()
        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action="PROJECT_DELETED",
            severity=AuditSeverity.MEDIUM,
            message=f"Project '{project.name}' deleted",
            project_id=project_id,
            actor=AuditActor(user_id=actor_id, email=actor_email),
        )
```
```python
# backend/app/modules/projects/services/create_environment.py — full replacement
from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.projects.constants import EnvironmentType
from app.modules.projects.exceptions import EnvironmentTypeAlreadyExists, ProjectNotFound
from app.modules.projects.schemas import EnvironmentRead
from app.modules.projects.uow import AbstractProjectsUnitOfWork


class CreateEnvironment(AbstractUseCase):
    """Create an environment. Rejected if the project doesn't exist, or already
    has an environment of the requested type (UNIQUE(project_id, type))."""

    def __init__(self, uow: AbstractProjectsUnitOfWork, audit_api: AuditApi) -> None:
        self._uow = uow
        self._audit_api = audit_api

    @use_case
    async def execute(
        self,
        project_id: UUID,
        type: EnvironmentType,
        name: str,
        base_url: str | None,
        *,
        actor_id: UUID,
        actor_email: str,
    ) -> EnvironmentRead:
        if await self._uow.projects.get_by_id(project_id) is None:
            raise ProjectNotFound()
        if await self._uow.environments.find_by_project_and_type(project_id, type) is not None:
            raise EnvironmentTypeAlreadyExists()
        env = await self._uow.environments.create(project_id=project_id, type=type, name=name, base_url=base_url)
        await self._uow.commit()
        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action="ENVIRONMENT_CREATED",
            severity=AuditSeverity.INFO,
            message=f"Environment '{env.name}' ({env.type.value}) created",
            project_id=project_id,
            environment_id=env.id,
            actor=AuditActor(user_id=actor_id, email=actor_email),
        )
        return env
```
```python
# backend/app/modules/projects/services/update_environment.py — full replacement
from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.projects.exceptions import EnvironmentNotFound
from app.modules.projects.schemas import EnvironmentRead
from app.modules.projects.uow import AbstractProjectsUnitOfWork


class UpdateEnvironment(AbstractUseCase):
    """Rename and/or re-point an environment. type is immutable — see schemas.EnvironmentUpdate."""

    def __init__(self, uow: AbstractProjectsUnitOfWork, audit_api: AuditApi) -> None:
        self._uow = uow
        self._audit_api = audit_api

    @use_case
    async def execute(
        self,
        environment_id: UUID,
        *,
        name: str | None,
        base_url: str | None,
        actor_id: UUID,
        actor_email: str,
    ) -> EnvironmentRead:
        existing = await self._uow.environments.get_by_id(environment_id)
        if existing is None:
            raise EnvironmentNotFound()
        updated = await self._uow.environments.update(environment_id, name=name, base_url=base_url)
        await self._uow.commit()
        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action="ENVIRONMENT_UPDATED",
            severity=AuditSeverity.INFO,
            message=f"Environment '{updated.name}' updated",
            project_id=existing.project_id,
            environment_id=updated.id,
            actor=AuditActor(user_id=actor_id, email=actor_email),
        )
        return updated
```
```python
# backend/app/modules/projects/services/delete_environment.py — full replacement
from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.projects.exceptions import EnvironmentNotFound
from app.modules.projects.uow import AbstractProjectsUnitOfWork


class DeleteEnvironment(AbstractUseCase):
    """Delete an environment."""

    def __init__(self, uow: AbstractProjectsUnitOfWork, audit_api: AuditApi) -> None:
        self._uow = uow
        self._audit_api = audit_api

    @use_case
    async def execute(self, environment_id: UUID, *, actor_id: UUID, actor_email: str) -> None:
        existing = await self._uow.environments.get_by_id(environment_id)
        if existing is None:
            raise EnvironmentNotFound()
        await self._uow.environments.delete(environment_id)
        await self._uow.commit()
        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action="ENVIRONMENT_DELETED",
            severity=AuditSeverity.MEDIUM,
            message=f"Environment '{existing.name}' deleted",
            project_id=existing.project_id,
            environment_id=environment_id,
            actor=AuditActor(user_id=actor_id, email=actor_email),
        )
```

- [ ] **Step 4: Wire `AuditApi` into `dependencies.py`'s 6 providers**
```python
# backend/app/modules/projects/dependencies.py — add this import alongside the others
from app.modules.audit.public import AuditApi, get_audit_api
```
Then change each of the 6 mutation providers to inject and pass it through, e.g.:
```python
async def get_create_project(
    uow: AbstractProjectsUnitOfWork = Depends(get_uow), audit_api: AuditApi = Depends(get_audit_api)
) -> CreateProject:
    """Provide the create-project use case."""
    return CreateProject(uow, audit_api)
```
Apply the identical `audit_api: AuditApi = Depends(get_audit_api)` parameter + second constructor argument to `get_update_project`, `get_delete_project`, `get_create_environment`, `get_update_environment`, `get_delete_environment`. `get_create_project_link`/`get_update_project_link`/`get_delete_project_link` are unchanged (links aren't retrofitted).

- [ ] **Step 5: Pass the actor through from `router.py`**

For each of the 6 mutation endpoints, rename `_user` to `user` (it's used now, not just for the permission side-effect) and add `actor_id=user.id, actor_email=user.email` to the `execute(...)` call. Example for `create_project`:
```python
@router.post("/projects")
async def create_project(
    body: ProjectCreate,
    use_case: CreateProject = Depends(get_create_project),
    user: UserRead = Depends(require_permission("project", "create")),
) -> ApiResponse[ProjectRead]:
    """Create a new project — auto-attaches the configured default Jira/Git links."""
    project = await use_case.execute(body.name, body.description, actor_id=user.id, actor_email=user.email)
    return ApiResponse[ProjectRead](success=True, data=project)
```
Apply the same `_user`→`user` rename + `actor_id=user.id, actor_email=user.email` addition to `update_project`, `delete_project`, `create_environment`, `update_environment`, `delete_environment`. The 7 read-only/link endpoints (`list_projects`, `get_project`, `list_environments`, `list_project_links`, `create_project_link`, `update_project_link`, `delete_project_link`) are unchanged.

- [ ] **Step 6: Run tests to verify they pass**
Run: `cd backend && uv run pytest tests/projects/ -v`
Expected: all pass (25 from Phase 1, same count — Task 6 changes signatures, not test count).

- [ ] **Step 7: Commit**
```bash
git add backend/app/modules/projects/services backend/app/modules/projects/dependencies.py backend/app/modules/projects/router.py backend/tests/projects/test_services.py
git commit -m "feat(audit): retrofit project/environment mutations to log audit events"
```

---

### Task 7: Wire audit router into the app + lock the module boundary

**Files:** Modify `backend/app/main.py`, `backend/.importlinter`.

**Interfaces:** Consumes `router` (Task 5). Produces `/api/v1/audit-logs` live on the running app.

- [ ] **Step 1: Register the router**
```python
# backend/app/main.py — add alongside the existing imports
from app.modules.audit.router import router as audit_router
```
```python
# backend/app/main.py — add alongside the existing include_router calls
app.include_router(audit_router, prefix="/api/v1")
```

- [ ] **Step 2: Add the `audit-facade` contract**
```ini
# backend/.importlinter — append after the projects-facade block
[importlinter:contract:audit-facade]
name = Other modules reach audit only through public.py
type = forbidden
source_modules =
    app.modules.auth
    app.modules.rbac
    app.modules.users
    app.modules.projects
    app.modules.common
forbidden_modules =
    app.modules.audit.repository
allow_indirect_imports = True
```

- [ ] **Step 3: Run boundary checks + full suite**
Run: `cd backend && python scripts/check_module_boundaries.py --strict && lint-imports && ruff check && ruff format --check && pytest`
Expected: all exit 0 / all pass (105 Phase-1-and-earlier + 6 audit = 111).

- [ ] **Step 4: Commit**
```bash
git add backend/app/main.py backend/.importlinter
git commit -m "feat(audit): wire router into the app and lock the module boundary"
```

---

### Task 8: Frontend `modules/audit-log` — fetchers, hook, filtered list UI

No automated test (no test runner in this repo); verified by Task 9's manual check. No `entities/` promotion — only one consumer, same bar Phase 1 used to keep `modules/roles`' link-adjacent concepts module-local.

**Files:** Create `frontend/src/modules/audit-log/{index.ts,api/fetchers.ts,api/query-keys.ts,hooks/use-audit-logs.ts,ui/audit-log-page-content.tsx}`. Modify `frontend/src/shared/constants/api.ts`.

**Interfaces:** Produces `AuditLogPageContent` — consumed by Task 9's `admin/audit-log/page.tsx`.

- [ ] **Step 1: `shared/constants/api.ts` addition**
```typescript
// frontend/src/shared/constants/api.ts — add inside ENDPOINTS, after PROJECTS
    AUDIT_LOGS: {
      ROOT: "/audit-logs",
    },
```

- [ ] **Step 2: `api/query-keys.ts`, `model/schema.ts` (inline in fetchers.ts — single consumer, no separate entity), `api/fetchers.ts`**
```typescript
// frontend/src/modules/audit-log/api/query-keys.ts
export const auditLogsKeys = {
  all: ["audit-logs"] as const,
  list: (filters?: Record<string, string | number | undefined>) =>
    [...auditLogsKeys.all, "list", filters] as const,
};
```
```typescript
// frontend/src/modules/audit-log/api/fetchers.ts
import { z } from "zod";
import { apiFetch } from "@/shared/lib/api-client";
import { API_CONFIG } from "@/shared/constants/api";

export const AUDIT_EVENT_TYPES = ["AUDIT", "INCIDENT_DETECTION", "NOTIFICATION_SENT"] as const;

export const auditLogEntrySchema = z.object({
  id: z.string(),
  type: z.enum(AUDIT_EVENT_TYPES),
  projectId: z.uuid().nullable(),
  environmentId: z.uuid().nullable(),
  source: z.string(),
  actor: z.object({ userId: z.uuid().nullable(), email: z.string().nullable() }),
  action: z.string(),
  severity: z.string(),
  incidentId: z.string().nullable(),
  message: z.string(),
  payload: z.record(z.string(), z.unknown()),
  timestamp: z.string(),
  createdAt: z.string(),
});

export type AuditLogEntry = z.infer<typeof auditLogEntrySchema>;

export const auditLogsPageSchema = z.object({
  items: z.array(auditLogEntrySchema),
  total: z.number(),
  limit: z.number(),
  offset: z.number(),
});

export type AuditLogsPage = z.infer<typeof auditLogsPageSchema>;

export interface AuditLogFilters {
  projectId?: string;
  environmentId?: string;
  type?: (typeof AUDIT_EVENT_TYPES)[number];
  since?: string;
  until?: string;
  limit?: number;
  offset?: number;
}

export async function fetchAuditLogs(filters: AuditLogFilters = {}): Promise<AuditLogsPage> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined) params.set(key, String(value));
  }
  const query = params.toString();
  const raw = await apiFetch<unknown>(
    `${API_CONFIG.ENDPOINTS.AUDIT_LOGS.ROOT}${query ? `?${query}` : ""}`,
  );
  return auditLogsPageSchema.parse(raw);
}
```

- [ ] **Step 3: `hooks/use-audit-logs.ts`**
```typescript
"use client";

import { useSuspenseQuery } from "@tanstack/react-query";
import { fetchAuditLogs, type AuditLogFilters } from "../api/fetchers";
import { auditLogsKeys } from "../api/query-keys";

export function useAuditLogsQuery(filters: AuditLogFilters = {}) {
  return useSuspenseQuery({
    queryKey: auditLogsKeys.list(filters as Record<string, string | number | undefined>),
    queryFn: () => fetchAuditLogs(filters),
  });
}
```

- [ ] **Step 4: `ui/audit-log-page-content.tsx`**
```typescript
"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { ScrollText } from "lucide-react";
import { Input } from "@/shared/ui/input";
import { Label } from "@/shared/ui/label";
import { useAuditLogsQuery } from "../hooks/use-audit-logs";
import { AUDIT_EVENT_TYPES, type AuditLogFilters } from "../api/fetchers";

export function AuditLogPageContent() {
  const t = useTranslations("auditLog");
  const [filters, setFilters] = useState<AuditLogFilters>({ limit: 50, offset: 0 });
  const { data } = useAuditLogsQuery(filters);

  return (
    <div className="flex flex-1 flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-xl font-bold text-foreground">{t("title")}</h1>
        <p className="text-sm text-muted-foreground">{t("description")}</p>
      </div>

      <div className="flex flex-wrap gap-4 rounded-xl border bg-card p-4">
        <div className="space-y-1.5">
          <Label htmlFor="filter-project">{t("filters.projectId")}</Label>
          <Input
            id="filter-project"
            value={filters.projectId ?? ""}
            onChange={(e) =>
              setFilters((f) => ({ ...f, projectId: e.target.value || undefined, offset: 0 }))
            }
            className="h-9 w-64"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="filter-type">{t("filters.type")}</Label>
          <select
            id="filter-type"
            value={filters.type ?? ""}
            onChange={(e) =>
              setFilters((f) => ({
                ...f,
                type: (e.target.value || undefined) as AuditLogFilters["type"],
                offset: 0,
              }))
            }
            className="h-9 rounded-md border bg-background px-3 text-sm"
          >
            <option value="">{t("filters.allTypes")}</option>
            {AUDIT_EVENT_TYPES.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>
        </div>
      </div>

      {data.items.length === 0 ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-3 rounded-xl border bg-card py-16 text-center">
          <div className="flex size-12 items-center justify-center rounded-xl bg-muted text-muted-foreground">
            <ScrollText className="size-6" aria-hidden />
          </div>
          <h2 className="text-lg font-semibold text-foreground">{t("empty.title")}</h2>
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border bg-card">
          <table className="w-full text-sm">
            <thead className="border-b bg-muted/40 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              <tr>
                <th className="px-4 py-3">{t("table.timestamp")}</th>
                <th className="px-4 py-3">{t("table.action")}</th>
                <th className="px-4 py-3">{t("table.actor")}</th>
                <th className="px-4 py-3">{t("table.message")}</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {data.items.map((entry) => (
                <tr key={entry.id} className="hover:bg-muted/30">
                  <td className="px-4 py-3 whitespace-nowrap text-muted-foreground">
                    {new Date(entry.timestamp).toLocaleString()}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs font-medium text-foreground">
                    {entry.action}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{entry.actor.email ?? "—"}</td>
                  <td className="px-4 py-3 text-foreground">{entry.message}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 5: `index.ts`**
```typescript
export { AuditLogPageContent } from "./ui/audit-log-page-content";
export { fetchAuditLogs } from "./api/fetchers";
export type { AuditLogEntry, AuditLogFilters } from "./api/fetchers";
```

- [ ] **Step 6: Manual verification + commit**
Run: `cd frontend && npx tsc --noEmit`
Expected: no errors (route wiring in Task 9 is what makes this fully resolve — same forward-reference pattern as Phase 1 Task 14/15).
```bash
git add frontend/src/shared/constants/api.ts frontend/src/modules/audit-log
git commit -m "feat(audit): add audit log list UI"
```

---

### Task 9: Route wiring — routes, permissions, sidebar, page, i18n

**Files:** Modify `frontend/src/shared/constants/{routes,permissions}.ts`, `dashboard-sidebar.tsx`, `shared/lib/i18n/request.ts`, `locales/{en,vi}/common.json`. Create `frontend/src/app/[locale]/(dashboard)/admin/audit-log/{page.tsx,loading.tsx}`, `frontend/locales/{en,vi}/modules/audit-log.json`.

- [ ] **Step 1: `routes.ts`**
```typescript
export const ROUTES = {
  login: "/login",
  dashboard: "/dashboard",
  adminUsers: "/admin/users",
  adminRoles: "/admin/roles",
  adminProjects: "/admin/projects",
  adminAuditLog: "/admin/audit-log",
} as const;
```

- [ ] **Step 2: `permissions.ts`** — add `AUDIT_LOG` to `RESOURCES` and `PERMISSIONS`
```typescript
// RESOURCES gains:
  AUDIT_LOG: "audit_log",
// PERMISSIONS gains:
  AUDIT_LOG: {
    RESOURCE: RESOURCES.AUDIT_LOG,
    READ: `${RESOURCES.AUDIT_LOG}.${ACTIONS.READ}` as const,
  },
```

- [ ] **Step 3: `admin/audit-log/page.tsx` + `loading.tsx`**
```typescript
// frontend/src/app/[locale]/(dashboard)/admin/audit-log/page.tsx
import { setRequestLocale } from "next-intl/server";
import { HydrationBoundary, dehydrate } from "@tanstack/react-query";
import { createQueryClient } from "@/shared/lib/query-client";
import { RequirePermission, NoPermission, hasPermission } from "@/entities/permission";
import { fetchAuthSession } from "@/modules/auth";
import { RESOURCES, ACTIONS } from "@/shared/constants/permissions";
import { fetchAuditLogs } from "@/modules/audit-log";
import { AuditLogPageContent } from "@/modules/audit-log";

export default async function AdminAuditLogPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);

  const session = await fetchAuthSession();
  const canRead = hasPermission(session, RESOURCES.AUDIT_LOG, ACTIONS.READ);

  const queryClient = createQueryClient();
  if (canRead) {
    await queryClient.prefetchQuery({
      queryKey: ["audit-logs", "list", { limit: 50, offset: 0 }],
      queryFn: () => fetchAuditLogs({ limit: 50, offset: 0 }),
    });
  }

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <RequirePermission
        resource={RESOURCES.AUDIT_LOG}
        action={ACTIONS.READ}
        fallback={<NoPermission />}
      >
        <AuditLogPageContent />
      </RequirePermission>
    </HydrationBoundary>
  );
}
```
```typescript
// frontend/src/app/[locale]/(dashboard)/admin/audit-log/loading.tsx
import { Skeleton } from "@/shared/ui/skeleton";

export default function AdminAuditLogLoading() {
  return (
    <div className="flex flex-1 flex-col gap-6">
      <div className="flex flex-col gap-2">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-4 w-72" />
      </div>
      <Skeleton className="h-16 w-full rounded-xl" />
      <div className="overflow-hidden rounded-xl border bg-card p-6">
        <div className="space-y-4">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-4 w-full" />
          ))}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Sidebar nav entry**
```typescript
// dashboard-sidebar.tsx — add ScrollText to the lucide-react import, add to navItems after adminProjects
    {
      href: ROUTES.adminAuditLog,
      label: t("auditLog"),
      icon: ScrollText,
      active: pathname === ROUTES.adminAuditLog,
      permission: { action: "read", resource: "audit_log" },
    },
```

- [ ] **Step 5: i18n**
```json
// frontend/locales/en/modules/audit-log.json
{
  "title": "Audit Log",
  "description": "System activity across projects and environments.",
  "filters": { "projectId": "Project ID", "type": "Type", "allTypes": "All types" },
  "table": { "timestamp": "Time", "action": "Action", "actor": "Actor", "message": "Message" },
  "empty": { "title": "No log entries yet" }
}
```
```json
// frontend/locales/vi/modules/audit-log.json
{
  "title": "Nhật ký hệ thống",
  "description": "Hoạt động hệ thống theo dự án và môi trường.",
  "filters": { "projectId": "Mã dự án", "type": "Loại", "allTypes": "Tất cả loại" },
  "table": { "timestamp": "Thời gian", "action": "Hành động", "actor": "Người thực hiện", "message": "Nội dung" },
  "empty": { "title": "Chưa có bản ghi nào" }
}
```
Add `"auditLog": "Audit Log"` / `"auditLog": "Nhật ký hệ thống"` to `nav` in both `common.json` files. Register `audit-log.json` in `request.ts` (6th `Promise.all` entry, `messages.auditLog`) same as Phase 1 Task 15 Step 6 registered `projects.json`.

- [ ] **Step 6: Verify + commit**
Run: `cd frontend && npx tsc --noEmit && npm run lint`
Expected: no errors.
```bash
git add frontend/src/shared/constants frontend/src/app/[locale]/\(dashboard\)/dashboard-sidebar.tsx "frontend/src/app/[locale]/(dashboard)/admin/audit-log" frontend/src/shared/lib/i18n/request.ts frontend/locales/en frontend/locales/vi
git commit -m "feat(audit): wire routes, permissions, sidebar, and i18n"
```

---

## Task 10: End-to-end verification

Run: `cd backend && uvicorn app.main:app --reload` + `cd frontend && npm run dev`, then:
1. Log in as a user with `project:*`/`environment:*`/`audit_log:read` permissions.
2. Create a project — open `/admin/audit-log`, confirm a `PROJECT_CREATED` entry appears with the correct actor email and timestamp.
3. Add an environment — confirm `ENVIRONMENT_CREATED` appears, filterable by the project's id.
4. Stop the `mongo` container (`docker stop mongo`), create another project — confirm it still succeeds (fire-and-forget), then `docker start mongo` and confirm the audit log for that specific action never appears (expected — it was dropped, not queued) while a project created *after* Mongo is back up does appear.
5. Log in as a user without `audit_log:read` — confirm `/admin/audit-log` shows the no-permission fallback while `/admin/projects` still works normally.

## Self-Review

**1. Spec coverage** (`docs/tasks/devops-control-panel-schema.md` §4 + master plan Phase 2 line): collection design → Task 3's document shape. Indexes (3 compound + TTL) → Task 3 `ensure_indexes`. Fire-and-forget writes → Task 4. Retention split by `expire_at` not fixed TTL → Task 3's `insert()`. Retrofit into Phase 1 → Task 6. ✅ all covered.

**2. Placeholder scan:** none found — every code block is complete.

**3. Type consistency:** verified `AuditApi.log_event`'s keyword args match every Task 6 call site exactly (`type`, `source`, `action`, `severity`, `message`, `actor`, `project_id`, `environment_id`, `incident_id`, `payload` — all keyword-only, matching the facade's signature). Verified every service's new `execute(..., *, actor_id, actor_email)` matches its router call site's `actor_id=user.id, actor_email=user.email`.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-08-22-devops-panel-phase2-audit-log-mongodb.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
