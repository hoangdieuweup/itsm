"""Every cache key in the application is built here.

Keys assembled as f-strings scattered across modules make correct invalidation
impossible, because nothing can enumerate what exists. Each domain module
supplies its own entity name through its constants module.
"""

from app.integrations.cache.constants import CacheDefaults


class CacheKeyBuilder:
    """The only place a cache key string is assembled."""

    @staticmethod
    def entity_key(entity: str, entity_id: int, version: int) -> str:
        """Build a versioned key for one entity instance."""
        return f"{entity}:{entity_id}:v{version}:s{CacheDefaults.PAYLOAD_SCHEMA_VERSION}"

    @staticmethod
    def version_key(entity: str, entity_id: int) -> str:
        """Build the key holding the current generation of an entity."""
        return f"ver:{entity}:{entity_id}"

    @staticmethod
    def lock_key(entity: str, entity_id: int) -> str:
        """Build the key used to serialize loads across processes."""
        return f"lock:{entity}:{entity_id}"

    @staticmethod
    def session_key(namespace: str, identifier: str) -> str:
        """Build a key for a short-lived, single-use, or mutex value that
        isn't a versioned entity cache — e.g. an OAuth PKCE state, a per-user
        refresh mutex, or a per-user upstream token cache. namespace is
        supplied by the owning module's own constants.py, same convention as
        entity_key's `entity` argument."""
        return f"{namespace}:{identifier}"
