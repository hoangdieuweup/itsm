"""Errors owned by the storage integration."""

from app.exceptions import IntegrationError, NotFoundError
from app.integrations.storage.constants import StorageErrorCode


class UploadFailed(IntegrationError):
    """Raised when an object could not be written to storage."""

    code = StorageErrorCode.UPLOAD_FAILED
    message = "Failed to upload object"


class ObjectNotFound(NotFoundError):
    """Raised when the requested key does not exist in the bucket."""

    code = StorageErrorCode.OBJECT_NOT_FOUND
    message = "Object not found"
