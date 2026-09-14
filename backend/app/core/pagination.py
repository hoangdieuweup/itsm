"""Pagination primitives shared by every list endpoint."""

from collections.abc import Sequence
from typing import Any, Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.markers import helper
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


class PageQuery:
    """Runs the two queries behind a repository's list_page: one page of rows and
    the table's total count. A repository keeps only its own row-to-schema mapping."""

    @staticmethod
    @helper
    async def fetch_rows(
        session: AsyncSession,
        model: type[Any],
        *,
        limit: int,
        offset: int,
        order_by: Any = None,
        options: Sequence[Any] = (),
    ) -> tuple[list[Any], int]:
        """Return one page of `model` rows together with the table's total row count."""
        stmt = select(model).options(*options).limit(limit).offset(offset)
        if order_by is not None:
            stmt = stmt.order_by(order_by)
        rows = list(await session.scalars(stmt))
        total = await session.scalar(select(func.count()).select_from(model))
        return rows, total or 0
