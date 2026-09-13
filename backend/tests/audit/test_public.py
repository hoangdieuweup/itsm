"""Integration tests for app.modules.audit.public — real MongoDB via testcontainers."""

from uuid import uuid4

import pytest
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.integrations.mongo.exceptions import MongoUnavailable
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
        unreachable_client = AsyncIOMotorClient("mongodb://localhost:1/", serverSelectionTimeoutMS=200)
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
        unreachable_client = AsyncIOMotorClient("mongodb://localhost:1/", serverSelectionTimeoutMS=200)
        api = AuditApi(MongoAuditLogRepository(unreachable_client["itsm_test_unreachable"]))

        with pytest.raises(MongoUnavailable):
            await api.list_logs(limit=10, offset=0)

        unreachable_client.close()
