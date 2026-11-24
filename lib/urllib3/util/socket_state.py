from __future__ import annotations

import errno
import sys
import socket
import struct
import typing

from .._constant import (
    DEFAULT_KEEPALIVE_IDLE_WINDOW,
    DEFAULT_BACKGROUND_WATCH_WINDOW,
    DEFAULT_TCP_KEEPALIVE_ATTEMPT_COUNT,
)

if typing.TYPE_CHECKING:
    from ..contrib.ssa import AsyncSocket
    from ..util.ssltransport import SSLTransport

IS_NT = sys.platform in {"win32", "cygwin", "msys"}
IS_DARWIN_OR_BSD = not IS_NT and (
    sys.platform == "darwin"
    or "bsd" in sys.platform
    or "dragonfly" in sys.platform
    or sys.platform == "ios"
)
IS_BSD = "bsd" in sys.platform or "dragonfly" in sys.platform
IS_DARWIN = sys.platform == "darwin" or sys.platform == "ios"
IS_LINUX = not IS_DARWIN_OR_BSD and sys.platform == "linux"
SOCKET_CLOSED_ERRNOS: frozenset[int] = frozenset(
    filter(
        None,
        (
            getattr(errno, "EBADF", None),
            getattr(errno, "ENOTSOCK", None),
            getattr(errno, "EINVAL", None),
            getattr(errno, "ENOTCONN", None),
        ),
    )
)

# Of course, Windows don't have any nice shortcut
# through getsockopt, why make it simple when a
# hard way exist? Let's contact the winapi directly.
if IS_NT:
    try:
        import ctypes
        import ctypes.wintypes
    except ImportError:
        WSAIoctl_Fn = None
        WSAGetLastError_Fn = None
    else:

        class WindowsTcpInfo(ctypes.Structure):
            """
            WindowsTcpInfo structure (https://learn.microsoft.com/en-us/windows/desktop/api/mstcpip/ns-mstcpip-tcp_info_v0)

            Minimum supported client: (Windows 10, version 1703 // Windows Server 2016)
            """

            _fields_ = [
                ("State", ctypes.c_int),
                ("Mss", ctypes.wintypes.ULONG),
                ("ConnectionTimeMs", ctypes.c_uint64),
                ("TimestampsEnabled", ctypes.wintypes.BOOLEAN),
                ("RttUs", ctypes.wintypes.ULONG),
                ("MinRttUs", ctypes.wintypes.ULONG),
                ("BytesInFlight", ctypes.wintypes.ULONG),
                ("Cwnd", ctypes.wintypes.ULONG),
                ("SndWnd", ctypes.wintypes.ULONG),
                ("RcvWnd", ctypes.wintypes.ULONG),
                ("RcvBuf", ctypes.wintypes.ULONG),
                ("BytesOut", ctypes.c_uint64),
                ("BytesIn", ctypes.c_uint64),
                ("BytesReordered", ctypes.wintypes.ULONG),
                ("BytesRetrans", ctypes.wintypes.ULONG),
                ("FastRetrans", ctypes.wintypes.ULONG),
                ("DupAcksIn", ctypes.wintypes.ULONG),
                ("TimeoutEpisodes", ctypes.wintypes.ULONG),
                ("SynRetrans", ctypes.c_uint8),
            ]

        try:
            WSAIoctl_Fn = ctypes.windll.ws2_32.WSAIoctl  # type: ignore[attr-defined]

            WSAIoctl_Fn.argtypes = [
                ctypes.c_void_p,  # [in]  SOCKET  s
                ctypes.wintypes.DWORD,  # [in]  DWORD   SIO_TCP_INFO
                ctypes.c_void_p,  # [in]  LPVOID  lpvInBuffer
                ctypes.wintypes.DWORD,  # [in]  DWORD   cbInBuffer
                ctypes.c_void_p,  # [out] LPVOID  lpvOutBuffer
                ctypes.wintypes.DWORD,  # [in]  DWORD   cbOutBuffer
                ctypes.POINTER(
                    ctypes.wintypes.DWORD
                ),  # [out] LPWORD  lpcbBytesReturned
                ctypes.c_void_p,  # [in]  LPWSAOVERLAPPED lpOverlapped
                ctypes.c_void_p,  # [in]  LPWSAOVERLAPPED_COMPLETION_ROUTINE lpCompletionRoutine
            ]
            WSAIoctl_Fn.restype = ctypes.c_int  # int
        except AttributeError:  # Defensive: very old Windows distribution
            WSAIoctl_Fn = None

        try:
            WSAGetLastError_Fn = ctypes.windll.ws2_32.WSAGetLastError  # type: ignore[attr-defined]
            WSAGetLastError_Fn.argtypes = []
            WSAGetLastError_Fn.restype = ctypes.c_int
        except AttributeError:  # Defensive: very old Windows distribution
            WSAGetLastError_Fn = None

        SIO_TCP_INFO = ctypes.wintypes.DWORD(
            1 << 31  # IOC_IN
            | 1 << 30  # IOC_OUT
            | 3 << 27  # IOC_VENDOR
            | 39
        )

        WSAENOTSOCK = 10038
        WSAEINVAL = 10022
        WSA_OPERATION_ABORTED = 995


def is_established(sock: socket.socket | AsyncSocket | SSLTransport) -> bool:
    """
    Determine by best effort if the socket is closed
    without ever attempting to read from it.
    This works by trying to get the TCP current status.

    That function is extremely sensible, making change here
    must be carefully thought before even suggesting a change.
    """
    if sock.fileno() == -1:
        return False  # Defensive: checked higher in stack already

    # shortcut async closed via transport state
    if hasattr(sock, "_writer"):
        transport = getattr(sock._writer, "_transport", None)

        if transport and transport.is_closing():
            return False

    # catch earlier the most catastrophic states
    # this pre-check avoid wasting time on TCP probing
    try:
        err = sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
        if err != 0:
            return False
    except OSError:
        return False

    # Well... If we're on UDP (or anything else),
    try:
        if (sock.type & socket.SOCK_STREAM) != socket.SOCK_STREAM:
            return True
    except TypeError:  # Defensive: unit test mocking
        if sock.type != socket.SOCK_STREAM:
            return True

    if IS_DARWIN_OR_BSD:
        if sys.platform in {"darwin", "ios"}:
            TCP_CONNECTION_INFO = getattr(socket, "TCP_CONNECTION_INFO", 0x106)
        else:  # Defensive: FreeBSD not tested in CI (yet)
            # TODO: Find a way to continuously test against FreeBSD!
            TCP_CONNECTION_INFO = getattr(socket, "TCP_INFO", None)

            if TCP_CONNECTION_INFO is None:
                return True

        try:
            info = sock.getsockopt(socket.IPPROTO_TCP, TCP_CONNECTION_INFO, 1024)
        except OSError as e:  # Defensive: unlikely as closed state checked higher
            # this path is there for tight racing condition. e.g. fd closed OS level while is_connected proceed.
            if e.errno in SOCKET_CLOSED_ERRNOS:
                return False
            return True

        if not info:  # Defensive: in theory impossible.
            return True

        state: int = struct.unpack("B", info[0:1])[0]

        # macOS/BSD TCP states:
        # TCPS_CLOSED      = 0
        # TCPS_LISTEN      = 1
        # TCPS_SYN_SENT    = 2
        # TCPS_SYN_RCVD    = 3
        # TCPS_ESTABLISHED = 4
        # TCPS_CLOSE_WAIT  = 5
        # TCPS_FIN_WAIT_1  = 6
        # TCPS_CLOSING     = 7
        # TCPS_LAST_ACK    = 8
        # TCPS_FIN_WAIT_2  = 9
        # TCPS_TIME_WAIT   = 10
        return state == 4
    elif IS_LINUX:
        TCP_INFO = getattr(socket, "TCP_INFO", 11)

        try:
            info = sock.getsockopt(socket.IPPROTO_TCP, TCP_INFO, 1024)
        except OSError as e:  # Defensive: unlikely as closed state checked higher
            # this path is there for tight racing condition. e.g. fd closed OS level while is_connected proceed.
            if e.errno in SOCKET_CLOSED_ERRNOS:
                return False
            return True

        if not info:  # Defensive: in theory impossible.
            return True

        state = struct.unpack("B", info[0:1])[0]

        # linux header
        # enum {
        #     TCP_ESTABLISHED = 1,
        #     TCP_SYN_SENT    = 2,
        #     TCP_SYN_RECV    = 3,
        #     TCP_FIN_WAIT1   = 4,
        #     TCP_FIN_WAIT2   = 5,
        #     TCP_TIME_WAIT   = 6,
        #     TCP_CLOSE       = 7,
        #     TCP_CLOSE_WAIT  = 8,
        #     TCP_LAST_ACK    = 9,
        #     TCP_LISTEN      = 10,
        #     TCP_CLOSING     = 11
        # };
        return state == 1
    elif IS_NT:
        if WSAIoctl_Fn is None:  # Defensive: old Windows distro
            return True

        sockfd = ctypes.c_void_p(sock.fileno())

        info_version = ctypes.wintypes.DWORD(0)
        tcp_info = WindowsTcpInfo()
        bytes_returned = ctypes.wintypes.DWORD(0)

        ioctl_return_code = WSAIoctl_Fn(
            sockfd,
            SIO_TCP_INFO,
            ctypes.pointer(info_version),
            ctypes.wintypes.DWORD(ctypes.sizeof(info_version)),
            ctypes.pointer(tcp_info),
            ctypes.wintypes.DWORD(ctypes.sizeof(tcp_info)),
            ctypes.pointer(bytes_returned),
            None,
            None,
        )

        if ioctl_return_code == 0:
            # https://learn.microsoft.com/en-us/windows/win32/api/mstcpip/ne-mstcpip-tcpstate
            # 0 = Closed
            # 1 = Listen
            # 2 = Syn Sent
            # 3 = Syn Rcvd
            # 4 = Established
            # 5 = Fin Wait 1
            # 6 = Fin Wait 2
            # 7 = Close Wait
            # 8 = Closing
            # 9 = Last Ack
            # 10 = Time Wait
            # 11 = Max?
            return tcp_info.State == 4  # type: ignore[no-any-return]
        elif WSAGetLastError_Fn is not None:  # Defensive: failed native TCP probe.
            err = WSAGetLastError_Fn()

            if err in (
                WSAENOTSOCK,
                WSAEINVAL,
                WSA_OPERATION_ABORTED,
            ):
                return False

    return True


def enable_keepalive(
    sock: socket.socket | AsyncSocket | SSLTransport,
    idle: int = int(DEFAULT_KEEPALIVE_IDLE_WINDOW),
    interval: int = int(DEFAULT_BACKGROUND_WATCH_WINDOW),
    count: int = DEFAULT_TCP_KEEPALIVE_ATTEMPT_COUNT,
) -> None:
    """Enable SO_KEEPALIVE and tune timers as portably as possible.

    Per-platform timer tuning is best-effort and silently skipped on failure.
    Do not use outside an HTTP/1.1 connection. Ping frame is the recommended
    alternative.

    If the end user already enabled tcp keepalive on the socket (e.g. via
    ``socket_options``), this function is a no-op: their configuration prime.
    """

    try:
        already_enabled = bool(sock.getsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE))
    except OSError:  # Defensive: edge OSes
        return

    if already_enabled:
        return

    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    except OSError:  # Defensive: edge OSes
        return

    if IS_LINUX or IS_BSD or IS_DARWIN:
        # Idle option name differs on Darwin
        if IS_DARWIN:
            idle_opt = getattr(socket, "TCP_KEEPALIVE", 0x10)
        else:
            idle_opt = getattr(socket, "TCP_KEEPIDLE", None)

        if idle_opt is None:  # Defensive: edge OSes
            return

        try:
            sock.setsockopt(socket.IPPROTO_TCP, idle_opt, idle)
        except OSError:  # Defensive: edge OSes
            return

        if hasattr(socket, "TCP_KEEPINTVL"):
            try:
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, interval)
            except OSError:  # Defensive: edge OSes
                pass
        if hasattr(socket, "TCP_KEEPCNT"):
            try:
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, count)
            except OSError:  # Defensive: edge OSes
                pass
    elif IS_NT:
        # Prefer modern setsockopt path (Win10 1709+).
        # It's the ONLY path that honors TCP_KEEPCNT on Windows.
        # See: https://learn.microsoft.com/en-us/windows/win32/winsock/ipproto-tcp-socket-options
        modern_ok = False
        if (
            hasattr(socket, "TCP_KEEPIDLE")
            and hasattr(socket, "TCP_KEEPINTVL")
            and hasattr(socket, "TCP_KEEPCNT")
        ):
            try:
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, idle)
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, interval)
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, count)
                modern_ok = True
            except OSError:  # Defensive: edge OSes
                pass  # likely pre-1709 Windows; fall through to ioctl
        if not modern_ok and hasattr(socket, "SIO_KEEPALIVE_VALS"):
            try:  # Defensive: legacy Windows keepalive API.
                sock.ioctl(  # type: ignore[union-attr]
                    socket.SIO_KEEPALIVE_VALS,
                    (1, idle * 1000, interval * 1000),
                )
            except OSError:  # Defensive: edge OSes
                pass
