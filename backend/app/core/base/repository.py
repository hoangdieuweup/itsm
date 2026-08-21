"""Abstract repository contract every module's concrete repository implements."""

from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar
from uuid import UUID

EntityT = TypeVar("EntityT")
IdT = TypeVar("IdT", UUID, int, str, Any)


class AbstractRepository(ABC, Generic[EntityT, IdT]):
    """The read contract every module's repository must satisfy.

    Each module extends this with its own write and lookup methods — see
    references/layer-examples.md.
    """

    @abstractmethod
    async def get_by_id(self, entity_id: IdT) -> EntityT | None:
        """Return one entity, or None when it does not exist."""
        raise NotImplementedError

    @abstractmethod
    async def list_page(self, limit: int, offset: int) -> tuple[list[EntityT], int]:
        """Return one page of entities together with the total count."""
        raise NotImplementedError
