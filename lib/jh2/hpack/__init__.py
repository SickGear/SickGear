"""
hpack
~~~~~

HTTP/2 header encoding for Python.
"""

from __future__ import annotations

from .exceptions import (
    HPACKDecodingError,
    HPACKError,
    InvalidTableIndex,
    InvalidTableSizeError,
    OversizedHeaderListError,
)
from .hpack import Decoder, Encoder
from .struct import HeaderTuple, NeverIndexedHeaderTuple

__all__ = [
    "Encoder",
    "Decoder",
    "HeaderTuple",
    "NeverIndexedHeaderTuple",
    "HPACKError",
    "HPACKDecodingError",
    "InvalidTableIndex",
    "OversizedHeaderListError",
    "InvalidTableSizeError",
]
