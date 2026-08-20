"""Pagination primitives shared by every list endpoint."""

from typing import Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel

from app.core.models import CustomModel

T = TypeVar("T")


class PaginationDefaults:
    """Bounds every paginated endpoint agrees to."""

    MAX_PAGE_SIZE = 200
    DEFAULT_PAGE_SIZE = 50


class PaginationParams(BaseModel):
    """Query parameters accepted by every paginated endpoint. Not a response body — no camelCase concern."""

    limit: int = PaginationDefaults.DEFAULT_PAGE_SIZE
    offset: int = 0


class Page(CustomModel, Generic[T]):
    """One page of results together with the total count."""

    items: list[T]
    total: int
    limit: int
    offset: int


async def pagination_params(
    limit: int = Query(PaginationDefaults.DEFAULT_PAGE_SIZE, ge=1, le=PaginationDefaults.MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
) -> PaginationParams:
    """Provide validated pagination parameters to a route."""
    return PaginationParams(limit=limit, offset=offset)
