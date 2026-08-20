"""Base Pydantic models applied across the whole application.

Every model here serializes to camelCase on the wire while Python code stays
snake_case — see references/api-contract.md for the full wire contract:
camelCase, the ApiResponse envelope, and the error code / i18n convention.
"""

from datetime import datetime
from typing import Any, Generic, TypeVar
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, field_serializer
from pydantic.alias_generators import to_camel

T = TypeVar("T")


class CustomModel(BaseModel):
    """Base model enforcing camelCase on the wire and one datetime format."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)

    @field_serializer("*", when_used="json", check_fields=False)
    def _serialize_datetimes(self, value: Any) -> Any:
        """Emit every datetime in UTC with an explicit offset."""
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=ZoneInfo("UTC"))
            return value.strftime("%Y-%m-%dT%H:%M:%S%z")
        return value


class FrozenModel(CustomModel):
    """Immutable base for values that cross layers or a cache boundary."""

    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, from_attributes=True, frozen=True
    )


class ErrorPayload(FrozenModel):
    """The error half of ApiResponse.

    code is a stable, non-localized key — the frontend maps it to a
    translated string via its own i18n system when one is present. message
    is an English default for logs and API consumers with no i18n layer;
    never render it directly to an end user once i18n exists.
    """

    code: str
    message: str
    context: dict[str, Any] = {}


class ApiResponse(FrozenModel, Generic[T]):
    """The one response envelope every endpoint returns, over REST or SSE alike."""

    success: bool
    data: T | None = None
    error: ErrorPayload | None = None
