from __future__ import annotations

import typing
from enum import Enum

from .backend import LowLevelResponse
from .backend._async import AsyncLowLevelResponse
from .fields import RequestField
from .util.request import _TYPE_FAILEDTELL
from .util.timeout import _TYPE_DEFAULT, Timeout

if typing.TYPE_CHECKING:
    import ssl

    from typing_extensions import Literal, TypedDict

    class _TYPE_PEER_CERT_RET_DICT(TypedDict, total=False):
        subjectAltName: tuple[tuple[str, str], ...]
        subject: tuple[tuple[tuple[str, str], ...], ...]
        serialNumber: str


_TYPE_BODY: typing.TypeAlias = typing.Union[
    bytes,
    typing.IO[typing.Any],
    typing.Iterable[bytes],
    typing.Iterable[str],
    str,
    LowLevelResponse,
    AsyncLowLevelResponse,
]

_TYPE_ASYNC_BODY: typing.TypeAlias = typing.Union[
    typing.AsyncIterable[bytes],
    typing.AsyncIterable[str],
]

_TYPE_FIELD_VALUE: typing.TypeAlias = typing.Union[str, bytes]
_TYPE_FIELD_VALUE_TUPLE: typing.TypeAlias = typing.Union[
    _TYPE_FIELD_VALUE,
    typing.Tuple[str, _TYPE_FIELD_VALUE],
    typing.Tuple[str, _TYPE_FIELD_VALUE, str],
]

_TYPE_FIELDS_SEQUENCE: typing.TypeAlias = typing.Sequence[
    typing.Union[typing.Tuple[str, _TYPE_FIELD_VALUE_TUPLE], RequestField]
]
_TYPE_FIELDS: typing.TypeAlias = typing.Union[
    _TYPE_FIELDS_SEQUENCE,
    typing.Mapping[str, _TYPE_FIELD_VALUE_TUPLE],
]
_TYPE_ENCODE_URL_FIELDS: typing.TypeAlias = typing.Union[
    typing.Sequence[typing.Tuple[str, typing.Union[str, bytes]]],
    typing.Mapping[str, typing.Union[str, bytes]],
]
_TYPE_SOCKET_OPTIONS: typing.TypeAlias = typing.Sequence[
    typing.Union[
        typing.Tuple[int, int, int],
        typing.Tuple[int, int, int, str],
    ]
]
_TYPE_REDUCE_RESULT: typing.TypeAlias = typing.Tuple[
    typing.Callable[..., object], typing.Tuple[object, ...]
]


_TYPE_TIMEOUT: typing.TypeAlias = typing.Union[float, _TYPE_DEFAULT, Timeout, None]
_TYPE_TIMEOUT_INTERNAL: typing.TypeAlias = typing.Union[float, _TYPE_DEFAULT, None]
_TYPE_PEER_CERT_RET: typing.TypeAlias = typing.Union[
    "_TYPE_PEER_CERT_RET_DICT", bytes, None
]

_TYPE_BODY_POSITION: typing.TypeAlias = typing.Union[int, _TYPE_FAILEDTELL]

try:
    from typing import TypedDict

    class _TYPE_SOCKS_OPTIONS(TypedDict):
        socks_version: int | Enum
        proxy_host: str | None
        proxy_port: str | None
        username: str | None
        password: str | None
        rdns: bool

except ImportError:  # Python 3.7
    _TYPE_SOCKS_OPTIONS = typing.Dict[str, typing.Any]  # type: ignore[misc, assignment]


class ProxyConfig(typing.NamedTuple):
    ssl_context: ssl.SSLContext | None
    use_forwarding_for_https: bool
    assert_hostname: None | str | Literal[False]
    assert_fingerprint: str | None
