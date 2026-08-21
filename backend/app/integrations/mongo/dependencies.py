"""Dependency wiring for the mongo integration."""

from fastapi import Request
from motor.motor_asyncio import AsyncIOMotorDatabase


async def get_mongo_database(request: Request) -> AsyncIOMotorDatabase:
    """Provide the process wide database handle."""
    return request.app.state.mongo_db
