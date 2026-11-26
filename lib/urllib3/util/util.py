from __future__ import annotations

import typing
import sys
from types import TracebackType


def to_bytes(
    x: str | bytes, encoding: str | None = None, errors: str | None = None
) -> bytes:
    if isinstance(x, bytes):
        return x
    elif not isinstance(x, str):
        raise TypeError(f"not expecting type {type(x).__name__}")
    if encoding or errors:
        return x.encode(encoding or "utf-8", errors=errors or "strict")
    return x.encode()


def to_str(
    x: str | bytes, encoding: str | None = None, errors: str | None = None
) -> str:
    if isinstance(x, str):
        return x
    elif not isinstance(x, bytes):
        raise TypeError(f"not expecting type {type(x).__name__}")
    if encoding or errors:
        return x.decode(encoding or "utf-8", errors=errors or "strict")
    return x.decode()


def reraise(
    tp: type[BaseException] | None,
    value: BaseException,
    tb: TracebackType | None = None,
) -> typing.NoReturn:
    try:
        if value.__traceback__ is not tb:
            raise value.with_traceback(tb)
        raise value
    finally:
        value = None  # type: ignore[assignment]
        tb = None


# asyncio.iscoroutinefunction is deprecated in Python 3.14 and will be removed in 3.16.
# Use inspect.iscoroutinefunction for Python 3.14+ and asyncio.iscoroutinefunction for earlier.
# Note: There are subtle behavioral differences between the two functions, but for
# the use cases in niquests (checking if callbacks/hooks are async), both should work.
if sys.version_info >= (3, 14):
    import inspect

    iscoroutinefunction = inspect.iscoroutinefunction
else:
    import asyncio

    iscoroutinefunction = asyncio.iscoroutinefunction
