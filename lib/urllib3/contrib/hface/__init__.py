# Copyright 2022 Akamai Technologies, Inc
# Largely rewritten in 2023 for urllib3-future
# Copyright 2024 Ahmed Tahri
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

import sys

# WASI platform doesn't support lazy imports.
if sys.platform == "wasi":
    try:
        from .protocols import http1 as _http1  # noqa: F401
    except ImportError:
        pass

    try:
        from .protocols import http2 as _http2  # noqa: F401
    except ImportError:
        pass

from ._configuration import QuicTLSConfig
from .protocols import (
    HTTP1Protocol,
    HTTP2Protocol,
    HTTP3Protocol,
    HTTPOverQUICProtocol,
    HTTPOverTCPProtocol,
    HTTPProtocol,
    HTTPProtocolFactory,
)

__all__ = (
    "QuicTLSConfig",
    "HTTP1Protocol",
    "HTTP2Protocol",
    "HTTP3Protocol",
    "HTTPOverQUICProtocol",
    "HTTPOverTCPProtocol",
    "HTTPProtocol",
    "HTTPProtocolFactory",
)
