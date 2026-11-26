from __future__ import annotations

import socket
import sys
import typing

if sys.platform == "wasi":
    try:
        from ..contrib.wasi import socket
    except ImportError:
        pass

if typing.TYPE_CHECKING:
    from .._typing import _TYPE_SOCKET_OPTIONS, _TYPE_TIMEOUT_INTERNAL
    from ..connection import HTTPConnection
    from .._async.connection import AsyncHTTPConnection
    from ..contrib.ssa import AsyncSocket

from .timeout import _DEFAULT_TIMEOUT


def is_connection_dropped(
    conn: HTTPConnection | AsyncHTTPConnection,
) -> bool:  # Platform-specific
    """
    Returns True if the connection is dropped and should be closed.
    :param conn: :class:`urllib3.connection.HTTPConnection` object.
    """
    return not conn.is_connected


# Kept for backward compatibility. Developers rely on it sometime.
def create_connection(
    address: tuple[str, int],
    timeout: _TYPE_TIMEOUT_INTERNAL = _DEFAULT_TIMEOUT,
    source_address: tuple[str, int] | None = None,
    socket_options: _TYPE_SOCKET_OPTIONS | None = None,
    socket_kind: socket.SocketKind = socket.SOCK_STREAM,
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
    from ..contrib.resolver import ResolverDescription

    return (
        ResolverDescription.from_url("system://")
        .new()
        .create_connection(
            address,
            timeout=timeout,
            source_address=source_address,
            socket_options=socket_options,
            socket_kind=socket_kind,
        )
    )


def _set_socket_options(
    sock: socket.socket | AsyncSocket, options: _TYPE_SOCKET_OPTIONS | None
) -> None:
    if options is None:
        return

    for opt in options:
        if len(opt) == 3 and sock.type == socket.SOCK_STREAM:
            sock.setsockopt(*opt)
        elif len(opt) == 4:
            protocol: str = opt[3].lower()
            if protocol == "tcp" and sock.type == socket.SOCK_STREAM:
                sock.setsockopt(*opt[:3])
            elif protocol == "udp" and sock.type == socket.SOCK_DGRAM:
                sock.setsockopt(*opt[:3])


def allowed_gai_family() -> socket.AddressFamily:
    """This function is designed to work in the context of
    getaddrinfo, where family=socket.AF_UNSPEC is the default and
    will perform a DNS search for both IPv6 and IPv4 records."""

    family = socket.AF_INET
    if HAS_IPV6:
        family = socket.AF_UNSPEC
    return family


_ORIGINAL_SOCKET = socket.socket
_with_attr_sock = socket.socket


def _has_ipv6() -> bool:
    """Returns True if the system can bind an IPv6 address."""
    sock = None
    has_ipv6 = False

    if socket.has_ipv6:
        # has_ipv6 returns true if cPython was compiled with IPv6 support.
        # It does not tell us if the system has IPv6 support enabled. To
        # determine that we must bind to an IPv6 address.
        # https://github.com/urllib3/urllib3/pull/611
        # https://bugs.python.org/issue658327
        try:
            socket_cls = (
                socket.socket
                if _with_attr_sock is _ORIGINAL_SOCKET
                else _with_attr_sock
            )
            sock = socket_cls(socket.AF_INET6)
            sock.bind(("::1", 0))
            has_ipv6 = True
        except Exception:
            pass

    if sock:
        sock.close()
    return has_ipv6


HAS_IPV6 = socket.has_ipv6 if sys.platform == "wasi" else _has_ipv6()
