"""Abstract repository contract every module's concrete repository implements."""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

EntityT = TypeVar("EntityT")


class AbstractRepository(ABC, Generic[EntityT]):
    """The read contract every module's repository must satisfy.

    Each module extends this with its own write and lookup methods — see
    references/layer-examples.md.
    """

    @abstractmethod
    async def get_by_id(self, entity_id: int) -> EntityT | None:
        """Return one entity, or None when it does not exist."""
        raise NotImplementedError

    @abstractmethod
    async def list_page(self, limit: int, offset: int) -> tuple[list[EntityT], int]:
        """Return one page of entities together with the total count."""
        raise NotImplementedError
