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

"""
HTTP factories create HTTP protools based on defined set of arguments.

We define the :class:`HTTPProtocol` interface to allow interchange
HTTP versions and protocol implementations. But constructors of
the class is not part of the interface. Every implementation
can use a different options to init instances.

Factories unify access to the creation of the protocol instances,
so that clients and servers can swap protocol implementations,
delegating the initialization to factories.
"""

from __future__ import annotations

import importlib
import inspect
from abc import ABCMeta
from typing import Any

from ._protocols import HTTPOverQUICProtocol, HTTPOverTCPProtocol, HTTPProtocol


class HTTPProtocolFactory(metaclass=ABCMeta):
    @staticmethod
    def new(
        type_protocol: type[HTTPProtocol],
        implementation: str | None = None,
        **kwargs: Any,
    ) -> HTTPOverQUICProtocol | HTTPOverTCPProtocol:
        """Create a new state-machine that target given protocol type."""
        assert type_protocol != HTTPProtocol, (
            "HTTPProtocol is ambiguous and cannot be requested in the factory."
        )

        package_name: str = __name__.split(".")[0]

        version_target: str = "".join(
            c for c in str(type_protocol).replace(package_name, "") if c.isdigit()
        )
        module_expr: str = f".protocols.http{version_target}"

        if implementation:
            module_expr += f"._{implementation.lower()}"

        try:
            http_module = importlib.import_module(
                module_expr, f"{package_name}.contrib.hface"
            )
        except ImportError as e:
            raise NotImplementedError(
                f"{type_protocol} cannot be loaded. Tried to import '{module_expr}'."
            ) from e

        implementations: list[
            tuple[str, type[HTTPOverQUICProtocol | HTTPOverTCPProtocol]]
        ] = inspect.getmembers(
            http_module,
            lambda e: (
                isinstance(e, type)
                and issubclass(e, (HTTPOverQUICProtocol, HTTPOverTCPProtocol))
            ),
        )

        if not implementations:
            raise NotImplementedError(
                f"{type_protocol} cannot be loaded. "
                "No compatible implementation available. "
                "Make sure your implementation inherit either from HTTPOverQUICProtocol or HTTPOverTCPProtocol."
            )

        implementation_target: type[HTTPOverQUICProtocol | HTTPOverTCPProtocol] = (
            implementations.pop()[1]
        )

        return implementation_target(**kwargs)
