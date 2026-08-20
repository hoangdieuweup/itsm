"""Layer markers: decorator classes that tag a method with its architectural role.

Implemented as classes, not functions returning closures, so each marker is a
named, reusable unit like every other role in this codebase — lowercase by
design, read as an annotation the same way @property/@staticmethod already are.

Fully transparent: __get__ delegates to the wrapped function's own descriptor
protocol, so a decorated method binds self and awaits exactly as if this
decorator were never applied — verified for sync, async, and @staticmethod.

See references/layer-examples.md for which method in each module gets which
marker. A method carrying more than one marker is a sign it is doing more
than one job — split it instead of stacking markers.
"""

import functools
from collections.abc import Callable
from typing import Any, TypeVar, overload

_F = TypeVar("_F", bound=Callable[..., Any])


class _MethodMarker:
    """Base for every marker below. Never used directly."""

    layer: str

    @overload
    def __new__(cls, func: _F) -> _F: ...  # type: ignore[misc]
    @overload
    def __new__(cls, func: Callable[..., Any]) -> "_MethodMarker": ...
    def __new__(cls, func: Callable[..., Any]) -> Any:
        instance = super().__new__(cls)
        instance._init(func)
        return instance

    def _init(self, func: Callable[..., Any]) -> None:
        functools.update_wrapper(self, func)
        self._func = func
        setattr(func, "__layer__", self.layer)  # noqa: B010 -- dynamic attribute, not a fixed attr of Callable

    def __get__(self, obj: Any, objtype: type | None = None) -> Any:
        """Delegate binding to the wrapped function — sync and async both bind correctly this way."""
        if obj is None:
            return self._func
        return self._func.__get__(obj, objtype)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Forward straight through for a bare function (no class involved)."""
        return self._func(*args, **kwargs)


class database(_MethodMarker):  # noqa: N801 -- lowercase by design, read as an annotation like @staticmethod
    """A method that reads or writes a module's own tables directly."""

    layer = "database"


class helper(_MethodMarker):  # noqa: N801 -- lowercase by design, read as an annotation like @staticmethod
    """A method with no business decision: formatting, normalization, or support for another method."""

    layer = "helper"


class rule(_MethodMarker):  # noqa: N801 -- lowercase by design, read as an annotation like @staticmethod
    """A method holding a pure business decision — no I/O."""

    layer = "rule"


class use_case(_MethodMarker):  # noqa: N801 -- lowercase by design, read as an annotation like @staticmethod
    """The execute() of a use case — one class, one operation."""

    layer = "use_case"


class facade(_MethodMarker):  # noqa: N801 -- lowercase by design, read as an annotation like @staticmethod
    """A method exposed to other modules through public.py."""

    layer = "facade"


class integration(_MethodMarker):  # noqa: N801 -- lowercase by design, read as an annotation like @staticmethod
    """A method that calls an external system directly (Redis, RabbitMQ, object storage)."""

    layer = "integration"
