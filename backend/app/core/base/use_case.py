"""Abstract use-case contract every module's service class implements.

Makes rule #9 (one use case, one class, one execute()) structural instead of
only documented: a concrete class that forgets execute() cannot be
instantiated — Python raises TypeError at the call site, not a linter
warning at review time. Input and output are left to each concrete class to
type: a Get use case, a List use case and a Create use case take genuinely
different arguments, so forcing one shared signature here would fight the
domain instead of describing it.
"""

from abc import ABC, abstractmethod
from typing import Any


class AbstractUseCase(ABC):
    """One orchestration step: validate, call the repository or uow, publish."""

    @abstractmethod
    async def execute(self, *args: Any, **kwargs: Any) -> Any:
        """Run the use case and return its result."""
        raise NotImplementedError
