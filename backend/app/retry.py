"""Retry decorator for transient failures in external calls.

Reach for this on a call to an external system (storage, an HTTP client to
another service) that can fail transiently. It is not a substitute for the
queue's own retry-via-DLX — that handles a message still failing after every
attempt here is exhausted; see references/messaging.md.
"""

import asyncio
import functools
import logging
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

R = TypeVar("R")


class retry:  # noqa: N801 -- lowercase by design, read as an annotation like @staticmethod
    """Retry an async call with exponential backoff on the given exception types.

    Raises the last exception once attempts is exhausted — this only absorbs
    the transient case, the caller still decides what "still failing" means.
    """

    def __init__(
        self,
        *,
        attempts: int = 3,
        base_delay_seconds: float = 0.5,
        exceptions: tuple[type[Exception], ...] = (Exception,),
    ) -> None:
        self._attempts = attempts
        self._base_delay_seconds = base_delay_seconds
        self._exceptions = exceptions

    def __call__(self, func: Callable[..., Awaitable[R]]) -> Callable[..., Awaitable[R]]:
        @functools.wraps(func)
        async def wrapped(*args: Any, **kwargs: Any) -> R:
            delay = self._base_delay_seconds
            for attempt in range(1, self._attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except self._exceptions as exc:
                    if attempt == self._attempts:
                        raise
                    logger.warning(
                        "retrying %s after attempt %s/%s: %s", func.__name__, attempt, self._attempts, exc
                    )
                    await asyncio.sleep(delay)
                    delay *= 2
            raise AssertionError("unreachable")  # loop above always returns or raises

        return wrapped
