"""Single access path to the logs collection."""

from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from uuid import UUID

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.base.markers import database
from app.modules.audit.constants import (
    AuditCollections,
    AuditEventType,
    AuditRetention,
    AuditSeverity,
    AuditSource,
)
from app.modules.audit.schemas import AuditActor, AuditLogEntry


class AbstractAuditLogRepository(ABC):
    """Contract a caller depends on instead of the concrete Motor class below.
    Not AbstractRepository[T, Id] — an append-only, time-range-queried
    collection has no single-id lookup use case here."""

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
