"""Constants owned by the storage integration."""

from enum import StrEnum


class StorageDefaults:
    """Numeric defaults owned by the storage integration."""

    MAX_UPLOAD_BYTES = 50 * 1024 * 1024
    PRESIGNED_URL_TTL = 3600


class StorageErrorCode(StrEnum):
    """Stable error codes raised by this integration."""

    UPLOAD_FAILED = "storage_upload_failed"
    OBJECT_NOT_FOUND = "storage_object_not_found"
