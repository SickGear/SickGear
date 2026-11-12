"""
High-performance asyncio DatagramTransport with Linux-specific UDP
receive/send coalescing:

  - GRO (receive): ``setsockopt(SOL_UDP, UDP_GRO)`` + ``recvmsg`` cmsg
  - GSO (send):    ``sendmsg`` with ``UDP_SEGMENT`` cmsg

All other platforms fall back to the standard asyncio DatagramTransport.
"""

from __future__ import annotations

import asyncio
import errno
import socket
import struct
import sys
from collections import deque
import typing


from ..._constant import UDP_LINUX_GRO, UDP_LINUX_SEGMENT

__all__ = (
    "create_udp_endpoint",
    "open_dgram_connection",
    "sync_recv_gro",
    "sync_sendmsg_gso",
    "sync_send_dgram",
    "GenericSegmentOffloadUnsupported",
    "DatagramReader",
    "DatagramWriter",
)

# UDP_SEGMENT cmsg payload is __u16 (2 bytes, native endian).
_UINT16: typing.Final = struct.Struct("=H")

# UDP_GRO cmsg payload is `int` (sizeof(int) bytes, native endian) -- see
# net/ipv4/udp.c:udp_cmsg_recv() in the Linux kernel.
_GRO_CMSG: typing.Final = struct.Struct("@i")

# Maximum size of a single coalesced GRO buffer the kernel can deliver.
# 65535 is the IPv4 datagram cap; the kernel may stitch several MTU-sized
# UDP datagrams together up to this total before delivering them in one
# recvmsg(). Do *not* tighten to 65507 (which is only the per-datagram
# UDP payload limit).
_DEFAULT_GRO_BUF: typing.Final = 65535

# Hard upper bound for the receive buffer when we grow it to recover from
# truncation. 256 KiB safely accommodates any GRO-coalesced burst the
# kernel will produce.
_MAX_GRO_BUF: typing.Final = 262144

# Flow control watermarks for the custom write queue.
_HIGH_WATERMARK: typing.Final = 64 * 1024
_LOW_WATERMARK: typing.Final = 16 * 1024

# GSO kernel limit: max segments per sendmsg call.
# UDP_MAX_SEGMENTS in the kernel is 64; the total payload must also be
# <= 64 KiB, so the effective cap depends on segment size.
_GSO_MAX_SEGMENTS: typing.Final = 64
_GSO_MAX_PAYLOAD: typing.Final = 65000  # safety margin under IP_MAXPACKET (65535)

# Bound the number of recvmsg calls in a single readiness callback so we
# never starve the event loop under sustained inbound traffic.
_RECV_BURST_LIMIT: typing.Final = 32

_IS_LINUX: typing.Final = sys.platform == "linux"
_IS_DARWIN: typing.Final = sys.platform in {"darwin", "ios"}

# Pre-resolved socket constants (avoid repeated attribute lookups in hot paths).
_SOL_UDP: typing.Final = getattr(socket, "SOL_UDP", 17)
# Avoid IntFlag dispatch on every datagram
_MSG_TRUNC: typing.Final = int(getattr(socket, "MSG_TRUNC", 0))
_MSG_CTRUNC: typing.Final = int(getattr(socket, "MSG_CTRUNC", 0))

# Ancillary buffer size for the GRO cmsg. Computed once, the kernel never
# returns more than one UDP_GRO cmsg per recvmsg().
if hasattr(socket, "CMSG_SPACE"):
    _ANCBUFSIZE: typing.Final = socket.CMSG_SPACE(_GRO_CMSG.size)
else:
    # Conservative fallback (e.g. Windows)
    _ANCBUFSIZE = 64  # type: ignore[misc]


def _sock_has_gro(sock: socket.socket) -> bool:
    """Return True if UDP_GRO is enabled on *sock* (Linux only).

    The caller is responsible for having previously enabled it via
    ``setsockopt(SOL_UDP, UDP_GRO, 1)``. On non-Linux platforms the
    SOL_UDP option number 104 may collide with an unrelated option;
    we guard explicitly so we never mistakenly enable the GRO code
    path off-Linux.
    """
    if not _IS_LINUX:
        return False
    try:
        return sock.getsockopt(_SOL_UDP, UDP_LINUX_GRO) == 1
    except OSError:
        return False


def _sock_has_gso(sock: socket.socket) -> bool:
    """Return True if the kernel supports UDP_SEGMENT (Linux only)."""
    if not _IS_LINUX:
        return False
    try:
        sock.setsockopt(_SOL_UDP, UDP_LINUX_SEGMENT, 1280)
    except OSError:
        return False

    sock.setsockopt(_SOL_UDP, UDP_LINUX_SEGMENT, 0)
    return True


def _split_gro_buffer(buf: bytes, segment_size: int) -> list[bytes]:
    """Split a GRO-coalesced buffer into individual datagrams.

    For ``bytes`` input, direct slicing is the fastest option in CPython:
    each slice is a single C-level memcpy with no Python-level overhead.
    """
    n = len(buf)
    if segment_size <= 0 or n <= segment_size:
        return [
            buf
        ]  # Defensive: callers split only buffers larger than a valid GRO segment.
    return [buf[i : i + segment_size] for i in range(0, n, segment_size)]


def _max_segments_for(size: int) -> int:
    """Return how many segments of *size* bytes fit in a single GSO call."""
    if size <= 0:
        return _GSO_MAX_SEGMENTS
    cap = _GSO_MAX_PAYLOAD // size
    if cap < 1:
        return 1
    return cap if cap < _GSO_MAX_SEGMENTS else _GSO_MAX_SEGMENTS


def _group_by_segment_size(
    datagrams: list[bytes],
) -> list[tuple[int, list[bytes]]]:
    """Group consecutive same-size datagrams for Linux UDP GSO.

    GSO requires every segment in a single ``sendmsg`` to be exactly
    ``segment_size`` bytes, except the very last which may be shorter.
    The kernel further caps a single call at ``_GSO_MAX_SEGMENTS``
    segments and ~64 KiB of payload, whichever is smaller.
    """
    if not datagrams:
        return []

    groups: list[tuple[int, list[bytes]]] = []
    first = datagrams[0]
    current_size = len(first)
    current_group: list[bytes] = [first]
    cap = _max_segments_for(current_size)

    for dgram in datagrams[1:]:
        size = len(dgram)
        if size == current_size and len(current_group) < cap:
            current_group.append(dgram)
        elif size < current_size and len(current_group) < cap:
            # A short final segment is legal as the *last* segment of a
            # GSO batch. Emit the group with this trailing short one.
            current_group.append(dgram)
            groups.append((current_size, current_group))
            current_group = []
            current_size = 0  # forces a fresh group on the next iteration
        else:
            if current_group:
                groups.append((current_size, current_group))
            current_size = size
            current_group = [dgram]
            cap = _max_segments_for(current_size)

    if current_group:
        groups.append((current_size, current_group))
    return groups


def _parse_gro_segment_size(ancdata: list[tuple[int, int, bytes]]) -> int | None:
    """Extract the GRO segment size from recvmsg ancillary data.

    Returns ``None`` if no UDP_GRO cmsg is present (single datagram).
    """
    for cmsg_level, cmsg_type, cmsg_data in ancdata:
        if cmsg_level == _SOL_UDP and cmsg_type == UDP_LINUX_GRO:
            n = len(cmsg_data)
            if n >= _GRO_CMSG.size:
                return _GRO_CMSG.unpack_from(cmsg_data, 0)[0]  # type: ignore[no-any-return]
            if (
                n >= _UINT16.size
            ):  # Defensive: alternate kernels may provide a short UDP_GRO control message.
                # Older kernels / unusual builds emit a u16 here.
                return _UINT16.unpack_from(cmsg_data, 0)[0]  # type: ignore[no-any-return]
            return (
                0  # Defensive: malformed or unsupported UDP_GRO control-message format.
            )
    return None


def sync_recv_gro(
    sock: socket.socket, bufsize: int, gro_segment_size: int = 1280
) -> bytes | list[bytes]:
    """Blocking ``recvmsg`` with GRO cmsg parsing.

    Returns the raw datagram (``bytes``) when no GRO coalescing took
    place, or a list of segments (``list[bytes]``) when the kernel
    delivered a coalesced buffer.

    Raises ``OSError`` on payload truncation so callers can grow their
    buffer.
    """
    data, ancdata, flags, _addr = sock.recvmsg(bufsize, _ANCBUFSIZE)

    if flags & _MSG_TRUNC:
        raise OSError(
            f"recvmsg payload truncated; bufsize={bufsize} too small for "
            f"the coalesced GRO buffer"
        )
    if not data:
        return b""
    if flags & _MSG_CTRUNC:
        # Ancillary truncated -- we may have lost the GRO cmsg. Treat as
        # a single datagram to avoid mis-splitting.
        return data

    parsed = _parse_gro_segment_size(ancdata)
    if parsed is None:
        # No GRO cmsg -- single datagram. Return as-is.
        return data
    segment_size = parsed if parsed > 0 else gro_segment_size

    if (
        len(data) <= segment_size
    ):  # Defensive: alternate UDP stacks may attach GRO metadata to an uncoalesced datagram.
        return data
    return _split_gro_buffer(data, segment_size)


class GenericSegmentOffloadUnsupported(Exception):
    """Raised when a UDP GSO send is rejected by the kernel/driver
    because the NIC does not actually support segmentation offload,
    even though Kernel support it.

    Callers should disable GSO on the affected socket for the rest of
    the connection and re-send the failing batch without GSO. This
    mirrors the fallback strategy used by ``quic-go``.
    """


# Errnos returned by the kernel/driver when a UDP segmentation offload
# request cannot actually be honored by the NIC or routing path.
_GSO_UNSUPPORTED_ERRNOS: typing.Final = frozenset(
    e
    for e in (
        getattr(errno, "EIO", None),
        getattr(errno, "EINVAL", None),
        getattr(errno, "ENOTSUP", None),
        getattr(errno, "EOPNOTSUPP", None),
        getattr(errno, "ENOPROTOOPT", None),
    )
    if e is not None
)


# Errnos returned when a datagram is larger than the path/link MTU allows
# and cannot be fragmented. qh3 performs Datagram Packetization Layer Path
# MTU Discovery (DPLPMTUD) by emitting PING probe datagrams of increasing
# size; an oversized probe is expected to bounce with ``EMSGSIZE``.
_MSG_TOO_BIG_ERRNOS: typing.Final = frozenset(
    e
    for e in (
        getattr(errno, "EMSGSIZE", None),
        getattr(errno, "WSAEMSGSIZE", None),
    )
    if e is not None
)

# Windows surfaces "message too long" as WSAEMSGSIZE (10040) through the
# ``winerror`` attribute as well, so account for it explicitly.
_WSAEMSGSIZE_WINERROR: typing.Final = 10040


def _is_msg_too_big(exc: OSError) -> bool:
    """Return True when *exc* means the datagram exceeded the path MTU."""
    if exc.errno in _MSG_TOO_BIG_ERRNOS:
        return True
    return getattr(exc, "winerror", None) == _WSAEMSGSIZE_WINERROR


def sync_send_dgram(sock: socket.socket, data: bytes) -> None:
    """Send a single datagram, dropping it if it is oversized.

    A datagram the kernel rejects with ``EMSGSIZE`` is silently dropped:
    it is an over-large qh3 DPLPMTUD probe that is meant to fail, not a
    fatal connection error (see issue #377). Any other error propagates.

    ``send`` (not ``sendall``) is used deliberately: a UDP datagram is
    sent atomically, so the stream-oriented retry loop of ``sendall``
    would be meaningless here (and would re-send a leftover tail as a
    corrupt second datagram if it ever triggered).
    """
    try:
        sock.send(data)
    except OSError as exc:
        if not _is_msg_too_big(exc):
            raise


def sync_sendmsg_gso(sock: socket.socket, datagrams: list[bytes]) -> None:
    """Batch-send datagrams using GSO. Falls back to individual sends.

    Raises :class:`GenericSegmentOffloadUnsupported` if the kernel/driver
    rejects the GSO send because the underlying NIC does not actually
    support UDP segmentation offload (e.g. ``EIO`` from ``sendmsg``).
    The current group is not sent in that case; callers are expected to
    disable GSO for the connection and re-send the batch without GSO.
    Duplicate delivery of any earlier group is harmless for QUIC
    (the receiver de-duplicates by packet number).
    """
    for segment_size, group in _group_by_segment_size(datagrams):
        if len(group) == 1:
            try:
                sock.send(group[0])
            except OSError as exc:
                # Oversized DPLPMTUD probe -- drop it (issue #377).
                if not _is_msg_too_big(exc):
                    raise
            continue
        try:
            # Passing the iov as multiple buffers lets the kernel
            # concatenate them into a single message without our having
            # to pre-join in user space.
            sock.sendmsg(
                group,
                [(_SOL_UDP, UDP_LINUX_SEGMENT, _UINT16.pack(segment_size))],
            )
        except OSError as exc:
            if exc.errno in _GSO_UNSUPPORTED_ERRNOS:
                raise GenericSegmentOffloadUnsupported() from exc
            # The batch was rejected. This can be a transient error (e.g.
            # interface MTU change) or an oversized DPLPMTUD probe segment
            # (EMSGSIZE). Fall back to one-by-one for this batch -- keeping
            # GSO enabled -- so that only the genuinely oversized datagram
            # is dropped and any legal (e.g. short trailing) segment in the
            # same group is still delivered (issue #377).
            for dgram in group:
                try:
                    sock.send(dgram)
                except OSError as inner:
                    if not _is_msg_too_big(inner):
                        raise


# qh3 ships a Rust-native, quinn-udp backed optimized UDP I/O
# transport. When the package is installed we prefer it (faster batch
# I/O, native GRO/GSO handling). When it is not, this Python
# implementation provides functionally equivalent semantics.
#
# The qh3 import is intentionally deferred to ``create_udp_endpoint``
# below so that merely importing this module never triggers an eager
# qh3 import (qh3 is an optional dependency).
class _NativeOptimizedDatagramTransport(asyncio.DatagramTransport):
    __slots__ = (
        "_loop",
        "_sock",
        "_sock_fd",
        "_protocol",
        "_address",
        "_connected",
        "_gro_enabled",
        "_gso_enabled",
        "_gro_segment_size",
        "_recv_buf_size",
        "_closing",
        "_closed",
        "_closed_fut",
        "_extra",
        "_paused",
        "_write_ready",
        "_send_queue",
        "_buffer_size",
        "_protocol_paused",
        "_writer_registered",
        "_reader_registered",
        "_protocol_supports_batch",
    )

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        sock: socket.socket,
        protocol: asyncio.DatagramProtocol,
        address: tuple[str, int] | None,
        gro_enabled: bool,
        gso_enabled: bool,
        gro_segment_size: int,
    ) -> None:
        super().__init__()
        self._loop = loop
        self._sock = sock
        self._sock_fd = sock.fileno()
        self._protocol = protocol
        self._address = address

        # Detect whether the socket is connect()-ed. When it is, we MUST
        # use send() -- sendto(addr) returns EISCONN on Linux/BSD.
        try:
            sock.getpeername()
            self._connected = True
        except OSError:
            self._connected = False

        self._gro_enabled = gro_enabled
        self._gso_enabled = gso_enabled
        self._gro_segment_size = gro_segment_size
        self._closing = False
        self._closed = False
        self._closed_fut: asyncio.Future[None] = loop.create_future()
        self._paused = False
        self._write_ready = True
        self._writer_registered = False
        self._reader_registered = False

        # Write buffer state.
        self._send_queue: deque[tuple[bytes, tuple[str, int] | None]] = deque()
        self._buffer_size = 0
        self._protocol_paused = False

        # When GRO is enabled we always need room for a fully coalesced
        # burst; otherwise a single MTU-sized datagram suffices.
        self._recv_buf_size = (
            _DEFAULT_GRO_BUF if gro_enabled else max(gro_segment_size, 1500)
        )

        # Cache whether the protocol opts in to the batch callback so
        # we can skip the per-recvmsg getattr.
        self._protocol_supports_batch = hasattr(protocol, "datagrams_received")

        try:
            sockname = sock.getsockname()
        except OSError:  # Defensive: optional socket-address metadata must not prevent transport construction.
            sockname = None

        self._extra = {
            "peername": address,
            "socket": sock,
            "sockname": sockname,
            "family": sock.family,
            "type": sock.type,
        }

    def get_extra_info(self, name: str, default: typing.Any = None) -> typing.Any:
        return self._extra.get(name, default)

    def is_closing(self) -> bool:
        return self._closing

    def get_protocol(self) -> asyncio.BaseProtocol:
        return self._protocol

    def set_protocol(self, protocol: asyncio.BaseProtocol) -> None:
        self._protocol = protocol  # type: ignore[assignment]
        self._protocol_supports_batch = hasattr(protocol, "datagrams_received")

    def get_write_buffer_size(self) -> int:
        return self._buffer_size

    def close(self) -> None:
        if self._closing:
            return
        self._closing = True
        self._unregister_reader()
        # Drain the write queue gracefully in the background.
        if not self._send_queue:
            self._loop.call_soon(self._call_connection_lost, None)

    def abort(self) -> None:
        if self._closing:
            return
        self._closing = True
        # Per asyncio contract, connection_lost MUST be invoked
        # asynchronously -- never re-entrantly from inside abort().
        self._send_queue.clear()
        self._buffer_size = 0
        self._loop.call_soon(self._call_connection_lost, None)

    def _call_connection_lost(self, exc: Exception | None) -> None:
        if self._closed:
            return
        self._closed = True
        self._unregister_reader()
        self._unregister_writer()
        try:
            self._protocol.connection_lost(exc)
        except (
            KeyboardInterrupt,
            SystemExit,
        ):  # Defensive: propagate process-exit signals raised by protocol callbacks.
            raise
        except BaseException:  # Defensive: a failing protocol callback must not interrupt transport bookkeeping.  # noqa: BLE001
            pass
        finally:
            try:
                self._sock.close()
            except OSError:  # Defensive: descriptor cleanup may fail after transport bookkeeping finishes.
                pass
            if not self._closed_fut.done():
                self._closed_fut.set_result(None)

    def _register_reader(self) -> None:
        if self._reader_registered or self._closed:
            return
        try:
            self._loop.add_reader(self._sock_fd, self._on_readable)
            self._reader_registered = True
        except (OSError, ValueError):
            pass

    def _unregister_reader(self) -> None:
        if not self._reader_registered:
            return
        self._reader_registered = False
        try:
            self._loop.remove_reader(self._sock_fd)
        except (OSError, ValueError):
            pass

    def _register_writer(self) -> None:
        if self._writer_registered or self._closed:
            return
        try:
            self._loop.add_writer(self._sock_fd, self._on_write_ready)
            self._writer_registered = True
        except (OSError, ValueError):
            pass

    def _unregister_writer(self) -> None:
        if not self._writer_registered:
            return
        self._writer_registered = False
        try:
            self._loop.remove_writer(self._sock_fd)
        except (OSError, ValueError):
            pass

    def _raw_send(self, data: bytes, addr: tuple[str, int] | None) -> None:
        """Issue a single send/sendto on the underlying socket.

        Picks the right syscall based on whether the socket is
        ``connect()``-ed: a connected UDP socket rejects ``sendto`` with
        ``EISCONN`` on Linux and macOS.
        """
        if self._connected:
            self._sock.send(data)
        else:
            target = addr if addr is not None else self._address
            if target is None:
                # Last-resort: try send() and let the kernel raise.
                self._sock.send(data)
            else:
                self._sock.sendto(data, target)

    def sendto(self, data: bytes, addr: tuple[str, int] | None = None) -> None:  # type: ignore[override]
        if self._closing:
            raise OSError("Transport is closing")

        target = addr if addr is not None else self._address

        # If the writer is currently busy draining backlog, queue this
        # datagram behind whatever is already there to preserve order.
        if not self._write_ready or self._send_queue:
            self._queue_write(data, target)
            return

        try:
            self._raw_send(data, target)
            return
        except BlockingIOError:
            pass
        except InterruptedError:
            # Retry once on EINTR; if it fails again, queue.
            try:
                self._raw_send(data, target)
                return
            except BlockingIOError:
                pass
            except OSError as exc:
                if not _is_msg_too_big(exc):
                    self._protocol.error_received(exc)
                return
        except OSError as exc:
            if not _is_msg_too_big(exc):
                self._protocol.error_received(exc)
            return

        # Fell through with EAGAIN -- queue and arm the writer.
        self._write_ready = False
        self._register_writer()
        self._queue_write(data, target)

    def sendto_many(self, datagrams: list[bytes]) -> None:
        """Send multiple datagrams, using GSO when available.

        Falls back to individual ``sendto`` calls when GSO is not
        supported or the socket write buffer is full. Guarantees that
        *every* input datagram is either transmitted or queued -- none
        are silently dropped.
        """
        if self._closing:
            raise OSError("Transport is closing")
        if not datagrams:
            return

        # If the writer is busy, append everything to the backlog so
        # ordering is preserved.
        if not self._write_ready or self._send_queue:
            target = self._address
            for dgram in datagrams:
                self._queue_write(dgram, target)
            return

        if self._gso_enabled:
            self._send_linux_gso(datagrams)
        else:
            for dgram in datagrams:
                # sendto() will queue automatically on EAGAIN.
                self.sendto(dgram)
                if self._closing or self._closed:
                    return

    def _send_linux_gso(self, datagrams: list[bytes]) -> None:
        """Send a list of datagrams using UDP_SEGMENT.

        On EAGAIN at any point, *all* not-yet-sent datagrams (including
        the failing group's contents) are pushed into the write queue
        in order, the writer is armed, and the function returns. Nothing
        is ever silently dropped.
        """
        groups = _group_by_segment_size(datagrams)
        addr = self._address
        sock = self._sock

        for i, (segment_size, group) in enumerate(groups):
            try:
                if len(group) == 1:
                    self._raw_send(group[0], addr)
                else:
                    # Multi-buffer iov -> single concatenated UDP message
                    # split server-side at segment_size boundaries.
                    sock.sendmsg(
                        group,
                        [
                            (
                                _SOL_UDP,
                                UDP_LINUX_SEGMENT,
                                _UINT16.pack(segment_size),
                            )
                        ],
                    )
            except BlockingIOError:
                self._write_ready = False
                self._register_writer()
                # Queue this group + every remaining group so nothing
                # gets lost.
                for _sz, g in groups[i:]:
                    for dgram in g:
                        self._queue_write(dgram, addr)
                return
            except InterruptedError:
                # Push what we haven't sent yet onto the queue and let
                # the writer retry. Avoids unbounded retry loops here.
                for _sz, g in groups[i:]:
                    for dgram in g:
                        self._queue_write(dgram, addr)
                self._write_ready = False
                self._register_writer()
                return
            except OSError as exc:
                # The kernel rejected this entire batch. If it was a
                # GSO send, fall back to per-datagram sends so partial
                # progress is still possible.
                if len(group) > 1:
                    # NIC/driver lies about GSO support: disable it
                    # permanently for this transport so future batches
                    # take the plain ``sendto`` path.
                    if exc.errno in _GSO_UNSUPPORTED_ERRNOS:
                        self._gso_enabled = False
                    for idx, dgram in enumerate(group):
                        try:
                            self._raw_send(dgram, addr)
                        except BlockingIOError:
                            self._write_ready = False
                            self._register_writer()
                            self._queue_write(dgram, addr)
                            # Push the rest of this group + everything after.
                            # Track position: equal datagrams can occur more than once.
                            for tail in group[idx + 1 :]:
                                self._queue_write(tail, addr)
                            for _sz, g in groups[i + 1 :]:
                                for d in g:
                                    self._queue_write(d, addr)
                            return
                        except OSError as inner:
                            # Oversized DPLPMTUD probe: drop just this
                            # datagram and keep going (issue #377).
                            if _is_msg_too_big(inner):
                                continue
                            self._protocol.error_received(inner)
                            if self._closing or self._closed:
                                return
                else:
                    # Oversized probe -- drop this group (issue #377).
                    if _is_msg_too_big(exc):
                        continue
                    self._protocol.error_received(exc)
                    if self._closing or self._closed:
                        return

    def _queue_write(self, data: bytes, addr: tuple[str, int] | None) -> None:
        self._send_queue.append((data, addr))
        self._buffer_size += len(data)
        if self._buffer_size >= _HIGH_WATERMARK and not self._protocol_paused:
            self._protocol_paused = True
            try:
                self._protocol.pause_writing()
            except (
                KeyboardInterrupt,
                SystemExit,
            ):  # Defensive: propagate process-exit signals raised by protocol callbacks.
                raise
            except BaseException:  # Defensive: a failing protocol callback must not interrupt transport bookkeeping.  # noqa: BLE001
                pass

    def _maybe_resume_protocol(self) -> None:
        if self._protocol_paused and self._buffer_size <= _LOW_WATERMARK:
            self._protocol_paused = False
            try:
                self._protocol.resume_writing()
            except (
                KeyboardInterrupt,
                SystemExit,
            ):  # Defensive: propagate process-exit signals raised by protocol callbacks.
                raise
            except BaseException:  # Defensive: a failing protocol callback must not interrupt transport bookkeeping.  # noqa: BLE001
                pass

    def _on_write_ready(self) -> None:
        """Drain the write backlog when the socket becomes writable."""
        queue = self._send_queue
        raw_send = self._raw_send

        while queue:
            data, addr = queue[0]
            try:
                raw_send(data, addr)
            except BlockingIOError:
                # Still not writable -- keep the writer armed and bail.
                return
            except InterruptedError:
                continue
            except OSError as exc:
                # Drop *only* this datagram (it was rejected by the
                # kernel) and continue with the rest. Then surface the
                # error to the protocol so it can react.
                queue.popleft()
                self._buffer_size -= len(data)
                self._maybe_resume_protocol()
                # Oversized DPLPMTUD probe -- drop it without surfacing an
                # error to the protocol (issue #377).
                if not _is_msg_too_big(exc):
                    try:
                        self._protocol.error_received(exc)
                    except (
                        KeyboardInterrupt,
                        SystemExit,
                    ):  # Defensive: propagate process-exit signals raised by protocol callbacks.
                        raise
                    except BaseException:  # Defensive: a failing protocol callback must not interrupt transport bookkeeping.  # noqa: BLE001
                        pass
                if self._closing or self._closed:
                    break
                continue

            queue.popleft()
            self._buffer_size -= len(data)
            self._maybe_resume_protocol()

        # Only relinquish the writer if the queue truly drained.
        # (A protocol callback may have re-queued during this loop.)
        if not queue:
            self._write_ready = True
            self._unregister_writer()

            if self._closing and not self._closed:
                self._loop.call_soon(self._call_connection_lost, None)

    def pause_reading(self) -> None:
        if not self._paused:
            self._paused = True
            self._unregister_reader()

    def resume_reading(self) -> None:
        if self._paused:
            self._paused = False
            self._register_reader()

    def _start(self) -> None:
        self._loop.call_soon(self._protocol.connection_made, self)
        self._register_reader()

    def _on_readable(self) -> None:
        if self._closing:
            return
        self._recv_linux_gro()

    def _recv_linux_gro(self) -> None:
        # Hoist hot attribute lookups into locals for the burst loop.
        sock_recvmsg = self._sock.recvmsg
        protocol = self._protocol
        datagram_received = protocol.datagram_received
        batch_cb = (
            protocol.datagrams_received  # type: ignore[attr-defined]
            if self._protocol_supports_batch
            else None
        )
        default_segment_size = self._gro_segment_size
        ancbufsize = _ANCBUFSIZE

        for _ in range(_RECV_BURST_LIMIT):
            try:
                data, ancdata, flags, addr = sock_recvmsg(
                    self._recv_buf_size, ancbufsize
                )
            except BlockingIOError:
                return
            except InterruptedError:
                continue  # Defensive: modern Python retries EINTR; retain alternate socket compatibility.
            except OSError as exc:
                try:
                    protocol.error_received(exc)
                except (
                    KeyboardInterrupt,
                    SystemExit,
                ):  # Defensive: propagate process-exit signals raised by protocol callbacks.
                    raise
                except BaseException:  # Defensive: a failing protocol callback must not interrupt transport bookkeeping.  # noqa: BLE001
                    pass
                return

            if not data:
                return

            # Detect payload truncation -- if we ever hit this we are
            # silently losing tail bytes, which manifests as opaque
            # QUIC decryption failures upstream.
            if flags & _MSG_TRUNC:
                bufsize = self._recv_buf_size
                try:
                    protocol.error_received(
                        OSError(
                            f"recvmsg payload truncated; recv buffer "
                            f"({bufsize}) is too small for the coalesced "
                            f"GRO buffer"
                        )
                    )
                except (
                    KeyboardInterrupt,
                    SystemExit,
                ):  # Defensive: propagate process-exit signals raised by protocol callbacks.
                    raise
                except BaseException:  # Defensive: a failing protocol callback must not interrupt transport bookkeeping.  # noqa: BLE001
                    pass
                # Grow the buffer for next time, up to the kernel max.
                if bufsize < _MAX_GRO_BUF:
                    self._recv_buf_size = min(bufsize * 2, _MAX_GRO_BUF)
                continue

            if flags & _MSG_CTRUNC:
                # Ancillary truncated; we cannot trust segment_size.
                # Treat as single datagram to avoid mis-splitting.
                datagram_received(data, addr)
                continue

            parsed = _parse_gro_segment_size(ancdata)
            if parsed is None:
                # No GRO cmsg -- kernel delivered a single datagram.
                datagram_received(data, addr)
                continue

            segment_size = parsed if parsed > 0 else default_segment_size
            if (
                len(data) <= segment_size
            ):  # Defensive: alternate UDP stacks may attach GRO metadata to an uncoalesced datagram.
                datagram_received(data, addr)
                continue

            segments = _split_gro_buffer(data, segment_size)
            if batch_cb is not None:
                batch_cb(segments, addr)
            else:
                for seg in segments:
                    datagram_received(seg, addr)

        # Hit the burst limit -- yield to the loop and reschedule.
        if not self._closing and self._reader_registered:
            self._loop.call_soon(self._on_readable)


async def create_udp_endpoint(
    loop: asyncio.AbstractEventLoop,
    protocol_factory: typing.Callable[[], asyncio.DatagramProtocol],
    *,
    local_addr: tuple[str, int] | None = None,
    remote_addr: tuple[str, int] | None = None,
    family: int = socket.AF_UNSPEC,
    reuse_port: bool = False,
    gro_segment_size: int = 1280,
    sock: socket.socket | None = None,
) -> tuple[asyncio.DatagramTransport, asyncio.DatagramProtocol]:
    if sock is not None:
        try:
            connected_addr = sock.getpeername()
        except OSError:
            connected_addr = None
    else:
        # 1. Resolve addresses
        if family == socket.AF_UNSPEC:
            target_addr = local_addr or remote_addr
            if target_addr:
                infos = await loop.getaddrinfo(
                    target_addr[0], target_addr[1], type=socket.SOCK_DGRAM
                )
                family = infos[0][0]
            else:
                family = socket.AF_INET

        # 2. Create socket
        sock = socket.socket(family, socket.SOCK_DGRAM)
        try:
            sock.setblocking(False)

            if reuse_port:
                try:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                except (AttributeError, OSError):
                    pass
            if local_addr:
                sock.bind(local_addr)

            connected_addr = None
            if remote_addr:
                await loop.sock_connect(sock, remote_addr)
                connected_addr = remote_addr
        except BaseException:
            sock.close()
            raise

    # 3. Determine capabilities -- the caller is responsible for enabling
    #    GRO/GSO via setsockopt before handing us the socket.
    gro_enabled = _sock_has_gro(sock)
    gso_enabled = _sock_has_gso(sock)

    # so far we can only trust Linux for GRO/GSO.
    if not _IS_LINUX and not _IS_DARWIN:
        # Windows have different paradigm around transport. can't register/listen fd.
        # see Proactor loop.
        return await loop.create_datagram_endpoint(protocol_factory, sock=sock)

    # 4. Wire up the optimized transport. Prefer qh3's Rust-native
    #    implementation when the package is available; fall back to the
    #    pure-Python native one otherwise. The qh3 import is performed
    #    here (not at module load) so that this module never forces an
    #    eager import of qh3 just to be importable.
    if _IS_LINUX:
        try:
            from qh3.asyncio._transport import (
                OptimizedDatagramTransport as _TransportImpl,
            )
        except ImportError:
            _TransportImpl = _NativeOptimizedDatagramTransport  # type: ignore[misc,assignment]
    else:
        _TransportImpl = _NativeOptimizedDatagramTransport  # type: ignore[misc,assignment]

    protocol = protocol_factory()
    transport = _TransportImpl(
        loop=loop,
        sock=sock,
        protocol=protocol,
        address=connected_addr,
        gro_enabled=gro_enabled,
        gso_enabled=gso_enabled,
        gro_segment_size=gro_segment_size,
    )
    transport._start()
    return transport, protocol


class DatagramReader:
    """API-compatible with ``asyncio.StreamReader`` (duck-typed) so that
    ``AsyncSocket`` can assign an instance to ``self._reader`` and the
    existing ``recv()`` code works unchanged.

    When GRO delivers multiple coalesced segments in a single syscall,
    ``feed_datagrams()`` stores them as a single ``list[bytes]`` entry.
    ``read()`` then returns that list directly so the caller can feed
    all segments to the QUIC state-machine in one pass before probing --
    avoiding the per-datagram recv->feed->probe round-trip overhead.
    """

    __slots__ = ("_buffer", "_waiter", "_exception", "_eof")

    def __init__(self) -> None:
        self._buffer: deque[bytes | list[bytes]] = deque()
        self._waiter: asyncio.Future[None] | None = None
        self._exception: BaseException | None = None
        self._eof = False

    def feed_datagram(self, data: bytes, addr: typing.Any) -> None:
        """Feed a single (non-coalesced) datagram."""
        if self._eof:
            return
        self._buffer.append(data)
        waiter = self._waiter
        if waiter is not None and not waiter.done():
            waiter.set_result(None)

    def feed_datagrams(self, data: list[bytes], addr: typing.Any) -> None:
        """Feed a batch of coalesced datagrams as a single entry."""
        if self._eof or not data:
            return
        self._buffer.append(data)
        waiter = self._waiter
        if waiter is not None and not waiter.done():
            waiter.set_result(None)

    def set_exception(self, exc: BaseException) -> None:
        self._exception = exc
        waiter = self._waiter
        if waiter is not None and not waiter.done():
            waiter.set_result(None)

    def connection_lost(self, exc: BaseException | None) -> None:
        self._eof = True
        if exc is not None and self._exception is None:
            self._exception = exc
        waiter = self._waiter
        if waiter is not None and not waiter.done():
            waiter.set_result(None)

    def at_eof(self) -> bool:
        return self._eof and not self._buffer

    def _drain_buf(self) -> bytes | list[bytes]:
        datagrams: list[bytes] = []
        for entry in self._buffer:
            # An entry is either a single datagram (bytes) or a batch
            # of coalesced datagrams (list[bytes]) from one GRO syscall.
            if isinstance(entry, bytes):
                datagrams.append(entry)
            else:
                datagrams.extend(entry)
        self._buffer.clear()
        # Preserve the public contract: a single datagram is returned as
        # bytes; multiple datagrams are returned as list[bytes].
        if len(datagrams) == 1:
            return datagrams[0]
        return datagrams

    async def read(self, n: int = -1) -> bytes | list[bytes]:
        """Return the next entry from the buffer.

        * ``bytes``       -- a single datagram (non-coalesced).
        * ``list[bytes]`` -- a batch of coalesced datagrams from one
          GRO syscall.
        * ``b""``         -- EOF.

        Buffered data is delivered first, *before* any pending exception
        is raised, so callers can drain the stream cleanly on shutdown.
        """
        if self._buffer:
            return self._drain_buf()

        if self._exception is not None:
            exc, self._exception = self._exception, None
            raise exc

        if self._eof:
            return b""

        if self._waiter is not None:
            raise RuntimeError(
                "DatagramReader.read() called concurrently from two coroutines"
            )

        waiter = asyncio.get_running_loop().create_future()
        self._waiter = waiter
        try:
            await waiter
        finally:
            self._waiter = None

        if self._buffer:
            return self._drain_buf()

        if self._exception is not None:
            exc, self._exception = self._exception, None
            raise exc

        return b""


class DatagramWriter:
    """API-compatible with ``asyncio.StreamWriter`` (duck-typed) so that
    ``AsyncSocket`` can assign an instance to ``self._writer`` and the
    existing ``sendall()``, ``close()``, ``wait_for_close()`` code works
    unchanged.
    """

    __slots__ = (
        "_transport",
        "_address",
        "_closed_event",
        "_paused",
        "_drain_waiters",
        "_supports_batch",
    )

    def __init__(self, transport: asyncio.DatagramTransport) -> None:
        self._transport = transport
        self._address: tuple[str, int] | None = transport.get_extra_info("peername")
        self._closed_event = asyncio.Event()
        self._paused = False
        # A list, not a single future: multiple coroutines may await
        # drain() simultaneously and they must all be woken.
        self._drain_waiters: list[asyncio.Future[None]] = []
        self._supports_batch = hasattr(transport, "sendto_many")

    @property
    def transport(self) -> asyncio.DatagramTransport:
        return self._transport

    def write(self, data: bytes | bytearray | memoryview | list[bytes]) -> None:
        transport = self._transport
        if transport.is_closing():
            return
        if isinstance(data, list):
            if self._supports_batch:
                transport.sendto_many(data)  # type: ignore[attr-defined]
            else:
                # Plain asyncio transport -- send individually.
                addr = self._address
                for dgram in data:
                    transport.sendto(dgram, addr)
        else:
            if not isinstance(data, bytes):
                data = bytes(data)
            transport.sendto(data, self._address)

    def writelines(self, datagrams: list[bytes]) -> None:
        """Send a batch of datagrams. ``StreamWriter``-compatible alias."""
        self.write(datagrams)

    async def drain(self) -> None:
        if not self._paused:
            return
        loop = asyncio.get_running_loop()
        waiter: asyncio.Future[None] = loop.create_future()
        self._drain_waiters.append(waiter)
        try:
            await waiter
        finally:
            try:
                self._drain_waiters.remove(waiter)
            except ValueError:
                pass

    def close(self) -> None:
        self._transport.close()

    def is_closing(self) -> bool:
        return self._transport.is_closing()

    async def wait_closed(self) -> None:
        await self._closed_event.wait()

    def get_extra_info(self, name: str, default: typing.Any = None) -> typing.Any:
        return self._transport.get_extra_info(name, default)

    def _pause_writing(self) -> None:
        self._paused = True

    def _resume_writing(self) -> None:
        self._paused = False
        # Wake every waiter; new ones may arrive after this call but they
        # will see ``_paused == False`` and return immediately.
        waiters = self._drain_waiters
        self._drain_waiters = []
        for w in waiters:
            if not w.done():
                w.set_result(None)


class _DatagramBridgeProtocol(asyncio.DatagramProtocol):
    """Bridges ``asyncio.DatagramProtocol`` callbacks to ``DatagramReader``
    / ``DatagramWriter``.
    """

    __slots__ = ("_reader", "_writer")

    def __init__(self, reader: DatagramReader) -> None:
        self._reader = reader
        self._writer: DatagramWriter | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        # Transport is already wired via DatagramWriter.
        pass

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        self._reader.feed_datagram(data, addr)

    def datagrams_received(self, data: list[bytes], addr: tuple[str, int]) -> None:
        self._reader.feed_datagrams(data, addr)

    def error_received(self, exc: Exception) -> None:
        # Standard asyncio transports report rejected sends here (e.g. Windows).
        if isinstance(exc, OSError) and _is_msg_too_big(exc):
            return
        # Surface to the reader so callers awaiting read() see it, but
        # do NOT mark EOF -- UDP errors are usually transient (ICMP
        # unreachable etc.) and the connection may recover.
        self._reader.set_exception(exc)

    def connection_lost(self, exc: BaseException | None) -> None:
        self._reader.connection_lost(exc)
        writer = self._writer
        if writer is not None:
            writer._closed_event.set()
            # Wake any pending drain() so the caller doesn't hang.
            writer._resume_writing()

    def pause_writing(self) -> None:
        if self._writer is not None:
            self._writer._pause_writing()

    def resume_writing(self) -> None:
        if self._writer is not None:
            self._writer._resume_writing()


async def open_dgram_connection(
    remote_addr: tuple[str, int] | None = None,
    *,
    local_addr: tuple[str, int] | None = None,
    family: int = socket.AF_UNSPEC,
    sock: socket.socket | None = None,
    gro_segment_size: int = 1280,
) -> tuple[DatagramReader, DatagramWriter]:
    loop = asyncio.get_running_loop()

    reader = DatagramReader()
    protocol = _DatagramBridgeProtocol(reader)

    transport, _ = await create_udp_endpoint(
        loop,
        lambda: protocol,
        local_addr=local_addr,
        remote_addr=remote_addr,
        family=family,
        gro_segment_size=gro_segment_size,
        sock=sock,
    )

    writer = DatagramWriter(transport)
    protocol._writer = writer

    return reader, writer
