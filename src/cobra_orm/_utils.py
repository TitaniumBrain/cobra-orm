"""Some utility methods and classes."""

from collections.abc import Callable
from typing import (
    Any,
    Concatenate,
    Generic,
    ParamSpec,
    TypeVar,
)

# ===============================================================================
# ===============================================================================

T = TypeVar("T")
P = ParamSpec("P")
R_co = TypeVar("R_co", covariant=False)


class class_or_instance_method(Generic[P, R_co]):
    """A decorator that allows different behaviour for a method depending on the calling context (class or instance).
    You must still test what it is bound to in the method body."""

    def __init__(self, func: Callable[Concatenate[Any, P], R_co]):
        self._func = func

    def __get__(self, instance: Any | None, owner: type) -> Callable[P, R_co]:
        if instance is None:
            cls_or_self = owner
        else:
            cls_or_self = instance

        def new_func(*args: P.args, **kwargs: P.kwargs) -> R_co:
            self._func
            return self._func(cls_or_self, *args, **kwargs)

        return new_func
