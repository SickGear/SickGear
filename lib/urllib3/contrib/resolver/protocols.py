from __future__ import annotations

import contextlib
import ipaddress
import secrets
import socket
import struct
import sys
import threading
import typing
from abc import ABCMeta, abstractmethod
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from enum import Enum

if sys.platform == "wasi":
    try:
        from ..wasi import socket
    except ImportError:
        pass

from ..._constant import UDP_LINUX_GRO
from ..._typing import _TYPE_SOCKET_OPTIONS, _TYPE_TIMEOUT_INTERNAL
from ...exceptions import HTTPError, LocationParseError
from ...util.connection import (
    _ORIGINAL_SOCKET,
    _set_socket_options,
    _with_attr_sock,
    allowed_gai_family,
)
from ...util.ssl_match_hostname import CertificateError, match_hostname
from ...util.timeout import _DEFAULT_TIMEOUT
from .utils import inet4_ntoa, inet6_ntoa, parse_https_rdata, read_name

if typing.TYPE_CHECKING:
    from .utils import HttpsRecord


class ProtocolResolver(str, Enum):
    """
    At urllib3.future we aim to propose a wide range of DNS-protocols.
    The most used techniques are available.
    """

    #: Ask the OS native DNS layer
    SYSTEM = "system"
    #: DNS over HTTPS
    DOH = "doh"
    #: DNS over QUIC
    DOQ = "doq"
    #: DNS over TLS
    DOT = "dot"
    #: DNS over UDP (insecure)
    DOU = "dou"
    #: Manual (e.g. hosts)
    MANUAL = "in-memory"
    #: Void (e.g. purposely disable resolution)
    NULL = "null"
    #: Custom (e.g. your own implementation, use this when it does not suit any of the protocols specified)
    CUSTOM = "custom"


class BaseResolver(metaclass=ABCMeta):
    protocol: typing.ClassVar[ProtocolResolver]
    specifier: typing.ClassVar[str | None] = None

    implementation: typing.ClassVar[str]

    def __init__(
        self,
        server: str | None,
        port: int | None = None,
        *patterns: str,
        **kwargs: typing.Any,
    ) -> None:
        self._server = server
        self._port = port
        self._host_patterns: tuple[str, ...] = patterns
        self._lock = threading.Lock()
        self._kwargs = kwargs

        if not self._host_patterns and "patterns" in kwargs:
            self._host_patterns = kwargs["patterns"]

        # allow to temporarily expose a sock that is "being" created
        # this helps with our Happy Eyeballs implementation in sync.
        self._unsafe_expose: bool = False
        self._sock_cursor: socket.socket | None = None

    def recycle(self) -> BaseResolver:
        if self.is_available():
            raise RuntimeError("Attempting to recycle a Resolver that was not closed")

        args = list(self.__class__.__init__.__code__.co_varnames)
        args.remove("self")

        kwargs_cpy = deepcopy(self._kwargs)

        if self._server:
            kwargs_cpy["server"] = self._server
        if self._port:
            kwargs_cpy["port"] = self._port

        if "patterns" in args and "kwargs" in args:
            if args[:2] == ["server", "port"]:
                # Explicit server/port parameters must precede hostname patterns.
                return self.__class__(
                    kwargs_cpy.pop("server", None),
                    kwargs_cpy.pop("port", None),
                    *self._host_patterns,
                    **kwargs_cpy,
                )
            return self.__class__(*self._host_patterns, **kwargs_cpy)  # type: ignore[arg-type]
        elif "kwargs" in args:
            return self.__class__(**kwargs_cpy)

        return self.__class__()  # type: ignore[call-arg]

    @property
    def server(self) -> str | None:
        return self._server

    @property
    def port(self) -> int | None:
        return self._port

    def have_constraints(self) -> bool:
        return bool(self._host_patterns)

    def support(self, hostname: str | bytes | None) -> bool | None:
        """
        Determine if given hostname is especially resolvable by given resolver.
        If this resolver does not have any constrained list of host, it returns None. Meaning
        it support any hostname for resolution.
        """
        if not self._host_patterns:
            return None
        if hostname is None:
            hostname = "localhost"
        if isinstance(hostname, bytes):
            hostname = hostname.decode("ascii")
        try:
            match_hostname(
                {"subjectAltName": (tuple(("DNS", e) for e in self._host_patterns))},
                hostname,
            )
        except CertificateError:
            return False
        return True

    @abstractmethod
    def close(self) -> None:
        """Terminate the given resolver instance. This should render it unusable. Further inquiries should raise an exception."""
        raise NotImplementedError

    @abstractmethod
    def is_available(self) -> bool:
        """Determine if Resolver can receive inquiries."""
        raise NotImplementedError

    @abstractmethod
    def getaddrinfo(
        self,
        host: bytes | str | None,
        port: str | int | None,
        family: socket.AddressFamily,
        type: socket.SocketKind,
        proto: int = 0,
        flags: int = 0,
        *,
        quic_upgrade_via_dns_rr: bool = False,
    ) -> list[
        tuple[
            socket.AddressFamily,
            socket.SocketKind,
            int,
            str | bytes,
            tuple[str, int] | tuple[str, int, int, int],
        ]
    ]:
        """This method align itself on the standard library socket.getaddrinfo(). It must be implemented as-is on your Resolver."""
        raise NotImplementedError

    # This function is copied from socket.py in the Python 2.7 standard
    # library test suite. Added to its signature is only `socket_options`.
    # One additional modification is that we avoid binding to IPv6 servers
    # discovered in DNS if the system doesn't have IPv6 functionality.
    def create_connection(
        self,
        address: tuple[str, int],
        timeout: _TYPE_TIMEOUT_INTERNAL = _DEFAULT_TIMEOUT,
        source_address: tuple[str, int] | None = None,
        socket_options: _TYPE_SOCKET_OPTIONS | None = None,
        socket_kind: socket.SocketKind = socket.SOCK_STREAM,
        *,
        quic_upgrade_via_dns_rr: bool = False,
        timing_hook: (
            typing.Callable[[tuple[timedelta, timedelta, datetime]], None] | None
        ) = None,
        ech_config_hook: typing.Callable[[bytes], None] | None = None,
        default_socket_family: socket.AddressFamily = socket.AF_UNSPEC,
    ) -> socket.socket:
        """Connect to *address* and return the socket object.

        Convenience function.  Connect to *address* (a 2-tuple ``(host,
        port)``) and return the socket object.  Passing the optional
        *timeout* parameter will set the timeout on the socket instance
        before attempting to connect.  If no *timeout* is supplied, the
        global default timeout setting returned by :func:`socket.getdefaulttimeout`
        is used.  If *source_address* is set it must be a tuple of (host, port)
        for the socket to bind as a source address before making the connection.
        An host of '' or port 0 tells the OS to use the default.
        """

        host, port = address
        if host.startswith("["):
            host = host.strip("[]")
        err = None

        # Using the value from allowed_gai_family() in the context of getaddrinfo lets
        # us select whether to work with IPv4 DNS records, IPv6 records, or both.
        # The original create_connection function always returns all records.
        family = allowed_gai_family()

        if family != socket.AF_UNSPEC:
            default_socket_family = family

        if source_address is not None:
            if isinstance(
                ipaddress.ip_address(source_address[0]), ipaddress.IPv4Address
            ):
                default_socket_family = socket.AF_INET
            else:
                default_socket_family = socket.AF_INET6

        try:
            host.encode("idna")
        except UnicodeError:
            raise LocationParseError(f"'{host}', label empty or too long") from None

        dt_pre_resolve = datetime.now(tz=timezone.utc)
        records = self.getaddrinfo(
            host,
            port,
            default_socket_family,
            socket_kind,
            quic_upgrade_via_dns_rr=quic_upgrade_via_dns_rr,
        )
        delta_post_resolve = datetime.now(tz=timezone.utc) - dt_pre_resolve

        dt_pre_established = datetime.now(tz=timezone.utc)
        for res in records:
            af, socktype, proto, canonname, sa = res
            sock = None
            try:
                socket_cls = (
                    socket.socket
                    if _with_attr_sock is _ORIGINAL_SOCKET
                    else _with_attr_sock
                )
                sock = socket_cls(af, socktype, proto)

                # we need to add this or reusing the same origin port will likely fail within
                # short period of time. kernel put port on wait shut.
                if source_address is not None:
                    try:
                        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                    except (
                        OSError,
                        AttributeError,
                    ):  # Defensive: Windows or very old OS?
                        try:
                            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                        except (
                            OSError,
                            AttributeError,
                        ):  # Defensive: we can't do anything better than this.
                            pass

                    try:
                        sock.setsockopt(
                            socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0)
                        )
                    except (OSError, AttributeError):
                        pass

                    sock.bind(source_address)

                # attempt to leverage GRO when under Linux
                if socktype == socket.SOCK_DGRAM and sys.platform == "linux":
                    try:
                        sock.setsockopt(socket.SOL_UDP, UDP_LINUX_GRO, 1)
                    except OSError:  # Defensive: oh, well(...) anyway!
                        pass

                # If provided, set socket level options before connecting.
                _set_socket_options(sock, socket_options)

                if timeout is not _DEFAULT_TIMEOUT:
                    sock.settimeout(timeout)

                if self._unsafe_expose:
                    self._sock_cursor = sock

                sock.connect(sa)

                if self._unsafe_expose:
                    self._sock_cursor = None
                # Break explicitly a reference cycle
                err = None

                delta_post_established = (
                    datetime.now(tz=timezone.utc) - dt_pre_established
                )

                if timing_hook is not None:
                    timing_hook(
                        (
                            delta_post_resolve,
                            delta_post_established,
                            datetime.now(tz=timezone.utc),
                        )
                    )

                if isinstance(canonname, bytes) and canonname:
                    if ech_config_hook is not None:
                        ech_config_hook(canonname)

                return sock
            except (OSError, OverflowError) as _:
                err = _
                if sock is not None:
                    sock.close()
                if isinstance(_, OverflowError):
                    break

        if err is not None:
            try:
                raise err
            finally:
                # Break explicitly a reference cycle
                err = None
        else:
            raise OSError("getaddrinfo returns an empty list")


class ManyResolver(BaseResolver):
    """
    Special resolver that use many child resolver. Priorities
    are based on given order (list of BaseResolver).
    """

    def __init__(self, *resolvers: BaseResolver) -> None:
        super().__init__(None, None)

        self._size = len(resolvers)

        self._unconstrained: list[BaseResolver] = [
            _ for _ in resolvers if not _.have_constraints()
        ]
        self._constrained: list[BaseResolver] = [
            _ for _ in resolvers if _.have_constraints()
        ]

        self._concurrent: int = 0
        self._terminated: bool = False

    def recycle(self) -> BaseResolver:
        resolvers = []

        for resolver in self._unconstrained + self._constrained:
            resolvers.append(resolver.recycle())

        return ManyResolver(*resolvers)

    def close(self) -> None:
        for resolver in self._unconstrained + self._constrained:
            resolver.close()

        self._terminated = True

    def is_available(self) -> bool:
        return not self._terminated

    def __resolvers(
        self, constrained: bool = False
    ) -> typing.Generator[BaseResolver, None, None]:
        resolvers = self._unconstrained if not constrained else self._constrained

        if not resolvers:
            return

        with self._lock:
            self._concurrent += 1

        try:
            resolver_count = len(resolvers)
            start_idx = (self._concurrent - 1) % resolver_count

            for idx in range(start_idx, resolver_count):
                if not resolvers[idx].is_available():
                    with self._lock:
                        resolvers[idx] = resolvers[idx].recycle()
                yield resolvers[idx]

            if start_idx > 0:
                for idx in range(0, start_idx):
                    if not resolvers[idx].is_available():
                        with self._lock:
                            resolvers[idx] = resolvers[idx].recycle()
                    yield resolvers[idx]
        finally:
            with self._lock:
                self._concurrent -= 1

    def getaddrinfo(
        self,
        host: bytes | str | None,
        port: str | int | None,
        family: socket.AddressFamily,
        type: socket.SocketKind,
        proto: int = 0,
        flags: int = 0,
        *,
        quic_upgrade_via_dns_rr: bool = False,
    ) -> list[
        tuple[
            socket.AddressFamily,
            socket.SocketKind,
            int,
            str | bytes,
            tuple[str, int] | tuple[str, int, int, int],
        ]
    ]:
        if isinstance(host, bytes):
            host = host.decode("ascii")
        if host is None:
            host = "localhost"

        tested_resolvers = []

        any_constrained_tried: bool = False

        with contextlib.closing(self.__resolvers(True)) as candidates:
            for resolver in candidates:
                can_resolve = resolver.support(host)

                if can_resolve is True:
                    any_constrained_tried = True

                    try:
                        results = resolver.getaddrinfo(
                            host,
                            port,
                            family,
                            type,
                            proto,
                            flags,
                            quic_upgrade_via_dns_rr=quic_upgrade_via_dns_rr,
                        )

                        if results:
                            return results
                    except socket.gaierror as exc:
                        if isinstance(exc.args[0], str) and (
                            "DNSSEC" in exc.args[0] or "DNSKEY" in exc.args[0]
                        ):
                            raise
                        continue
                    except (OSError, HTTPError):
                        # a DoH or DoT server that is down, try the next resolver for this host
                        continue
                elif can_resolve is False:
                    tested_resolvers.append(resolver)

        if any_constrained_tried:
            raise socket.gaierror(
                f"Name or service not known: {host} using {self._size - len(self._unconstrained)} resolver(s)"
            )

        with contextlib.closing(self.__resolvers()) as candidates:
            for resolver in candidates:
                try:
                    results = resolver.getaddrinfo(
                        host,
                        port,
                        family,
                        type,
                        proto,
                        flags,
                        quic_upgrade_via_dns_rr=quic_upgrade_via_dns_rr,
                    )

                    if results:
                        return results
                except socket.gaierror as exc:
                    if isinstance(exc.args[0], str) and (
                        "DNSSEC" in exc.args[0] or "DNSKEY" in exc.args[0]
                    ):
                        raise
                    continue

        raise socket.gaierror(
            f"Name or service not known: {host} using {self._size - len(self._constrained)} resolver(s)"
        )


class SupportedQueryType(int, Enum):
    """
    urllib3.future does not need anything else so far. let's be pragmatic.
    Each type is associated with its hex value as per the RFC.
    """

    A = 0x0001
    AAAA = 0x001C
    HTTPS = 0x0041


class DomainNameServerQuery:
    """
    Minimalist DNS query/message to ask for A, AAAA and HTTPS records.
    Only meant for urllib3.future use. Does not cover all of possible extent of use.
    """

    def __init__(
        self, host: str, query_type: SupportedQueryType, override_id: int | None = None
    ) -> None:
        self._id = struct.pack(
            "!H", secrets.randbits(16) if override_id is None else override_id
        )
        self._host = host.rstrip(".")
        self._normalized_host = self._host.lower()
        self._query = query_type
        self._query_class = 1
        self._flags = struct.pack("!H", 0x0100)
        self._qd_count = struct.pack("!H", 1)

        self._cached: bytes | None = None

    @property
    def id(self) -> int:
        return struct.unpack("!H", self._id)[0]  # type: ignore[no-any-return]

    @property
    def raw_id(
        self,
    ) -> bytes:  # Defensive: diagnostic DNS access; resolver logic uses stored fields.
        return self._id

    @property
    def normalized_host(self) -> str:
        return self._normalized_host

    @property
    def query_type(self) -> SupportedQueryType:
        return self._query

    @property
    def query_class(self) -> int:
        return self._query_class

    def __repr__(
        self,
    ) -> str:  # Defensive: diagnostic DNS access; resolver logic uses stored fields.
        return f"<Query '{self._host}' IN {self._query.name}>"

    def __bytes__(self) -> bytes:
        if self._cached:
            return self._cached

        payload = b""

        payload += self._id
        payload += self._flags
        payload += self._qd_count
        payload += b"\x00\x00"
        payload += b"\x00\x00"
        payload += b"\x00\x00"

        for ext in self._host.split("."):
            payload += struct.pack("!B", len(ext))
            payload += ext.encode("ascii")

        payload += b"\x00"
        payload += struct.pack("!H", self._query.value)
        payload += struct.pack("!H", self._query_class)

        self._cached = payload

        return payload

    @staticmethod
    def bulk(
        host: str, *types: SupportedQueryType
    ) -> list[
        DomainNameServerQuery
    ]:  # Defensive: optional query-construction helper; no internal callers.
        queries = []

        for query_type in types:
            queries.append(DomainNameServerQuery(host, query_type=query_type))

        return queries


#: Most common status code, not exhaustive at all.
COMMON_RCODE_LABEL: dict[int, str] = {
    0: "No Error",
    1: "Format Error",
    2: "Server Failure",
    3: "Non-Existent Domain",
    5: "Query Refused",
    9: "Not Authorized",
}


class DomainNameServerParseException(Exception): ...


class DomainNameServerReturn:
    """
    Minimalist DNS response parser. Allow to quickly extract key-data out of it.
    Meant for A, AAAA and HTTPS records. Basically only what we need.
    """

    def __init__(self, payload: bytes, *, ignore_truncated_https: bool = False) -> None:
        try:
            up = struct.unpack("!HHHHHH", payload[:12])

            self._id = up[0]
            self._flags = up[1]
            self._qd_count = up[2]
            self._an_count = up[3]

            self._qr = (self._flags >> 15) & 0x01
            self._opcode = (self._flags >> 11) & 0x0F

            self._rcode = payload[3] & 0x0F

            if self._qd_count != 1:
                raise ValueError("DNS response must contain exactly one question")

            # Parse QNAME using read_name which handles compression pointers (0xC0xx)
            self._hostname, idx = read_name(payload, 12)
            self._normalized_hostname = self._hostname.rstrip(".").lower()
            self._query_type, self._query_class = struct.unpack(
                "!HH", payload[idx : idx + 4]
            )
            idx += 4

            self._records: list[tuple[SupportedQueryType, int, str | HttpsRecord]] = []
            self._answer_ttls: list[int] = []

            if (
                ignore_truncated_https
                and self._flags & 0x0200
                and self._query_type == SupportedQueryType.HTTPS.value
                and self._rcode == 0
            ):
                # UDP may finish an HTTPS question without using its incomplete
                # answer. Do not cache addresses without the missing HTTPS data.
                self._answer_ttls.append(0)
                return

            if self._an_count:
                answers_read = 0
                while idx < len(payload) and answers_read < self._an_count:
                    # Parse the answer NAME field (may be a compression pointer or full label)
                    _, idx = read_name(payload, idx)

                    # Read TYPE (2), CLASS (2), TTL (4), RDLENGTH (2) = 10 bytes
                    rr_type, rr_class, rr_ttl = struct.unpack(
                        "!HHI", payload[idx : idx + 8]
                    )
                    self._answer_ttls.append(rr_ttl)
                    answers_read += 1
                    entry_size = struct.unpack("!H", payload[idx + 8 : idx + 10])[0]

                    if idx + 10 + entry_size > len(payload):
                        raise ValueError("DNS resource record is truncated")

                    data = payload[idx + 10 : idx + 10 + entry_size]

                    idx += 10 + entry_size

                    # Dispatch based on the TYPE field, not data length
                    try:
                        query_type = SupportedQueryType(rr_type)
                    except ValueError:
                        # Unknown/unsupported record type (e.g. CNAME, SOA) -- skip
                        continue

                    decoded_data: str | HttpsRecord
                    if query_type == SupportedQueryType.A:
                        decoded_data = inet4_ntoa(data)
                    elif query_type == SupportedQueryType.AAAA:
                        decoded_data = inet6_ntoa(data)
                    elif query_type == SupportedQueryType.HTTPS:
                        if not data:
                            continue
                        decoded_data = parse_https_rdata(data)
                    else:
                        continue  # Defensive: a new enum member may not yet have a record decoder.

                    self._records.append((query_type, rr_ttl, decoded_data))
                if answers_read != self._an_count:
                    raise ValueError("DNS answer section is truncated")
        except (struct.error, IndexError, ValueError, UnicodeDecodeError) as e:
            raise DomainNameServerParseException(
                "A protocol error occurred while parsing the DNS response payload: "
                f"{str(e)}"
            ) from e

    @property
    def id(self) -> int:
        return self._id  # type: ignore[no-any-return]

    @property
    def hostname(
        self,
    ) -> str:  # Defensive: diagnostic DNS access; resolver logic uses stored fields.
        return self._hostname

    @property
    def normalized_hostname(
        self,
    ) -> str:  # Defensive: diagnostic DNS access; resolver logic uses stored fields.
        return self._normalized_hostname

    @property
    def qr(
        self,
    ) -> int:  # Defensive: diagnostic DNS access; resolver logic uses stored fields.
        return self._qr  # type: ignore[no-any-return]

    @property
    def opcode(
        self,
    ) -> int:  # Defensive: diagnostic DNS access; resolver logic uses stored fields.
        return self._opcode  # type: ignore[no-any-return]

    @property
    def qd_count(
        self,
    ) -> int:  # Defensive: diagnostic DNS access; resolver logic uses stored fields.
        return self._qd_count  # type: ignore[no-any-return]

    @property
    def query_type(
        self,
    ) -> int:  # Defensive: diagnostic DNS access; resolver logic uses stored fields.
        return self._query_type  # type: ignore[no-any-return]

    @property
    def query_class(
        self,
    ) -> int:  # Defensive: diagnostic DNS access; resolver logic uses stored fields.
        return self._query_class  # type: ignore[no-any-return]

    def matches(self, query: DomainNameServerQuery) -> bool:
        return (
            self._id == query.id
            and self._qr == 1
            and self._opcode == 0
            and self._qd_count == 1
            and self._normalized_hostname == query.normalized_host
            and self._query_type == query.query_type.value
            and self._query_class == query.query_class
        )

    @property
    def records(self) -> list[tuple[SupportedQueryType, int, str | HttpsRecord]]:
        return self._records

    @property
    def answer_ttls(self) -> list[int]:
        return self._answer_ttls

    @property
    def is_found(
        self,
    ) -> bool:  # Defensive: diagnostic DNS access; resolver logic uses stored fields.
        return bool(self._records)

    @property
    def rcode(self) -> int:
        return self._rcode

    @property
    def is_ok(self) -> bool:
        return self._rcode == 0

    def __repr__(
        self,
    ) -> str:  # Defensive: diagnostic DNS access; resolver logic uses stored fields.
        if self.is_ok:
            return f"<Records '{self.hostname}' {self._records}>"
        return f"<DNS Error '{self.hostname}' with Status {self.rcode} ({COMMON_RCODE_LABEL[self.rcode] if self.rcode in COMMON_RCODE_LABEL else 'Unknown'})>"
