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
