"""Dependency wiring for the storage integration."""

from fastapi import Request

from app.integrations.storage.client import StorageClient


async def get_storage(request: Request) -> StorageClient:
    """Provide the process wide storage client."""
    return request.app.state.storage
