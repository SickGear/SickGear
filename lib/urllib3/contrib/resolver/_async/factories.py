from __future__ import annotations

import importlib
import inspect
import typing
from abc import ABCMeta
from base64 import b64encode
from typing import Any
from urllib.parse import parse_qs

from ....util import parse_url
from ..factories import ResolverDescription
from ..protocols import ProtocolResolver
from .protocols import AsyncBaseResolver


class AsyncResolverFactory(metaclass=ABCMeta):
    @staticmethod
    def has(
        protocol: ProtocolResolver,
        specifier: str | None = None,
        implementation: str | None = None,
    ) -> bool:
        package_name: str = __name__.split(".")[0]
        module_expr = f".{protocol.value.replace('-', '_')}"

        if implementation:
            module_expr += f"._{implementation.replace('-', '_').lower()}"

        try:
            resolver_module = importlib.import_module(
                module_expr, f"{package_name}.contrib.resolver._async"
            )
        except ImportError:
            return False

        implementations: list[tuple[str, type[AsyncBaseResolver]]] = inspect.getmembers(
            resolver_module,
            lambda e: (
                isinstance(e, type)
                and issubclass(e, AsyncBaseResolver)
                and (
                    (specifier is None and e.specifier is None)
                    or specifier == e.specifier
                )
            ),
        )

        if not implementations:
            return False

        return True

    @staticmethod
    def new(
        protocol: ProtocolResolver,
        specifier: str | None = None,
        implementation: str | None = None,
        **kwargs: Any,
    ) -> AsyncBaseResolver:
        package_name: str = __name__.split(".")[0]

        module_expr = f".{protocol.value.replace('-', '_')}"

        if implementation:
            module_expr += f"._{implementation.replace('-', '_').lower()}"

        spe_msg = " " if specifier is None else f' (w/ specifier "{specifier}") '

        try:
            resolver_module = importlib.import_module(
                module_expr, f"{package_name}.contrib.resolver._async"
            )
        except ImportError as e:
            raise NotImplementedError(
                f"{protocol}{spe_msg}cannot be loaded. Tried to import '{module_expr}'. Did you specify a non-existent implementation?"
            ) from e

        implementations: list[tuple[str, type[AsyncBaseResolver]]] = inspect.getmembers(
            resolver_module,
            lambda e: (
                isinstance(e, type)
                and issubclass(e, AsyncBaseResolver)
                and (
                    (specifier is None and e.specifier is None)
                    or specifier == e.specifier
                )
                and hasattr(e, "protocol")
                and e.protocol == protocol
            ),
        )

        if not implementations:
            raise NotImplementedError(
                f"{protocol}{spe_msg}cannot be loaded. "
                "No compatible implementation available. "
                "Make sure your implementation inherit from BaseResolver."
            )

        implementation_target: type[AsyncBaseResolver] = implementations.pop()[1]

        return implementation_target(**kwargs)


class AsyncResolverDescription(ResolverDescription):
    """Describe how a BaseResolver must be instantiated."""

    def new(self) -> AsyncBaseResolver:
        kwargs = {**self.kwargs}

        if self.server:
            kwargs["server"] = self.server
        if self.port:
            kwargs["port"] = self.port
        if self.host_patterns:
            kwargs["patterns"] = self.host_patterns

        return AsyncResolverFactory.new(
            self.protocol,
            self.specifier,
            self.implementation,
            **kwargs,
        )

    @staticmethod
    def from_url(url: str) -> AsyncResolverDescription:
        parsed_url = parse_url(url)

        schema = parsed_url.scheme

        if schema is None:
            raise ValueError("Given DNS url is missing a protocol")

        specifier = None
        implementation = None

        if "+" in schema:
            schema, specifier = tuple(schema.lower().split("+", 1))

        protocol = ProtocolResolver(schema)
        kwargs: dict[str, typing.Any] = {}

        if parsed_url.path:
            kwargs["path"] = parsed_url.path

        if parsed_url.auth:
            # Decode userinfo once; passwords may themselves contain colons.
            username, password = parsed_url.auth_decoded
            assert username is not None
            if password is not None:
                username = username.strip("'\"")
                password = password.strip("'\"")
                authorization = (
                    f"Basic {b64encode(f'{username}:{password}'.encode()).decode()}"
                )
            else:
                authorization = f"Bearer {username}"
            # Use the same header representation as the URL query parameters.
            kwargs["headers"] = [f"Authorization:{authorization}"]

        if parsed_url.query:
            parameters = parse_qs(parsed_url.query)

            for parameter in parameters:
                parameter_insensible = parameter.lower()

                if (
                    isinstance(parameters[parameter], list)
                    and len(parameters[parameter]) > 1
                ):
                    if parameter_insensible == "implementation":
                        raise ValueError("Only one implementation can be passed to URL")

                    values = []

                    for e in parameters[parameter]:
                        if "," in e:
                            values.extend(e.split(","))
                        else:
                            values.append(e)

                    if parameter_insensible in kwargs:
                        if isinstance(kwargs[parameter_insensible], list):
                            kwargs[parameter_insensible].extend(values)
                        else:
                            values.append(kwargs[parameter_insensible])
                            kwargs[parameter_insensible] = values
                        continue

                    kwargs[parameter_insensible] = values
                    continue

                # Values can contain credentials or case-sensitive filesystem paths.
                value: str = parameters[parameter][0].strip(" ")

                if parameter_insensible == "implementation":
                    if implementation is not None:
                        raise ValueError("Only one implementation can be passed to URL")
                    implementation = value.lower()
                    continue

                if "," in value:
                    list_of_values = value.split(",")

                    if parameter_insensible in kwargs:
                        if isinstance(kwargs[parameter_insensible], list):
                            kwargs[parameter_insensible].extend(list_of_values)
                        else:
                            list_of_values.append(kwargs[parameter_insensible])
                            kwargs[parameter_insensible] = list_of_values
                        continue

                    kwargs[parameter_insensible] = list_of_values
                    continue

                value_converted: bool | int | float | None = None

                if value.lower() in ["false", "true"]:
                    value_converted = value.lower() == "true"
                elif value.isdigit():
                    value_converted = int(value)
                elif (
                    value.count(".") == 1
                    and value.index(".") > 0
                    and value.replace(".", "").isdigit()
                ):
                    value_converted = float(value)

                parsed_value = value if value_converted is None else value_converted
                # A query path overrides the URL path; other repeated values accumulate.
                if parameter_insensible != "path" and parameter_insensible in kwargs:
                    if not isinstance(kwargs[parameter_insensible], list):
                        kwargs[parameter_insensible] = [kwargs[parameter_insensible]]
                    kwargs[parameter_insensible].append(parsed_value)
                else:
                    kwargs[parameter_insensible] = parsed_value

        host_patterns: list[str] = []

        if "hosts" in kwargs:
            host_patterns = (
                kwargs["hosts"].split(",")
                if isinstance(kwargs["hosts"], str)
                else kwargs["hosts"]
            )
            del kwargs["hosts"]

        return AsyncResolverDescription(
            protocol,
            specifier,
            implementation,
            parsed_url.host,
            parsed_url.port,
            *host_patterns,
            **kwargs,
        )
