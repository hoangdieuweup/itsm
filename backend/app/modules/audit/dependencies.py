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
