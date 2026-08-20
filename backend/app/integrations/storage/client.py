"""Object storage client."""

import logging

import aioboto3

from app.core.base.markers import helper, integration
from app.core.retry import retry
from app.integrations.storage.config import storage_settings
from app.integrations.storage.constants import StorageDefaults
from app.integrations.storage.exceptions import UploadFailed

logger = logging.getLogger(__name__)


class StorageClient:
    """Wraps object storage access behind a narrow interface."""

    def __init__(self) -> None:
        self._session = aioboto3.Session()

    @integration
    async def close(self) -> None:
        """Release any pooled connection during shutdown."""
        return None

    @integration
    @retry(attempts=3, exceptions=(UploadFailed,))
    async def upload(self, key: str, body: bytes, content_type: str) -> str:
        """Store one object and return its key, retrying a transient failure up to twice more."""
        try:
            async with self._client() as client:
                await client.put_object(
                    Bucket=storage_settings.BUCKET,
                    Key=key,
                    Body=body,
                    ContentType=content_type,
                )
        except Exception as exc:
            raise UploadFailed(key=key) from exc

        logger.info("object uploaded key=%s", key)
        return key

    @integration
    async def presigned_url(self, key: str, ttl: int = StorageDefaults.PRESIGNED_URL_TTL) -> str:
        """Return a time limited URL granting read access to one object."""
        async with self._client() as client:
            return await client.generate_presigned_url(
                "get_object",
                Params={"Bucket": storage_settings.BUCKET, "Key": key},
                ExpiresIn=ttl,
            )

    @helper
    def _client(self):
        """Open a configured storage client."""
        return self._session.client(
            "s3",
            endpoint_url=storage_settings.ENDPOINT or None,
            aws_access_key_id=storage_settings.ACCESS_KEY or None,
            aws_secret_access_key=storage_settings.SECRET_KEY or None,
            region_name=storage_settings.REGION,
        )
