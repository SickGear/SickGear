from __future__ import annotations

import binascii
import socket
import struct
import typing
from random import uniform
from time import monotonic

if typing.TYPE_CHECKING:

    class HttpsRecord(typing.TypedDict):
        priority: int
        target: str
        alpn: list[str]
        ipv4hint: list[str]
        ipv6hint: list[str]
        echconfig: bytes


_UDP_DEFAULT_TIMEOUT = 7.0
_UDP_INITIAL_RETRY_DELAY = 1 / 3


def _udp_retry_deadlines(deadline: float) -> typing.Iterator[float]:
    delay = _UDP_INITIAL_RETRY_DELAY
    while monotonic() < deadline:
        yield min(monotonic() + delay, deadline)
        delay *= uniform(1.8, 2.2)


def inet4_ntoa(address: bytes) -> str:
    """
    Convert an IPv4 address from bytes to str.
    """
    if len(address) != 4:
        raise ValueError(  # Defensive: overly protective
            f"IPv4 addresses are 4 bytes long, got {len(address)} byte(s) instead"
        )

    return "%u.%u.%u.%u" % (address[0], address[1], address[2], address[3])


def inet6_ntoa(address: bytes) -> str:
    """
    Convert an IPv6 address from bytes to str.
    """
    if len(address) != 16:
        raise ValueError(  # Defensive: overly protective
            f"IPv6 addresses are 16 bytes long, got {len(address)} byte(s) instead"
        )

    hex = binascii.hexlify(address)
    chunks = []

    i = 0
    length = len(hex)

    while i < length:
        chunk = hex[i : i + 4].decode().lstrip("0") or "0"
        chunks.append(chunk)
        i += 4

    # Compress the longest subsequence of 0-value chunks to ::
    best_start = 0
    best_len = 0
    start = -1
    last_was_zero = False

    for i in range(8):
        if chunks[i] != "0":
            if last_was_zero:
                end = i
                current_len = end - start
                if current_len > best_len:
                    best_start = start
                    best_len = current_len
                last_was_zero = False
        elif not last_was_zero:
            start = i
            last_was_zero = True
    if last_was_zero:
        end = 8
        current_len = end - start
        if current_len > best_len:
            best_start = start
            best_len = current_len
    if best_len > 1:
        if best_start == 0 and (best_len == 6 or best_len == 5 and chunks[5] == "ffff"):
            # We have an embedded IPv4 address
            if best_len == 6:
                prefix = "::"
            else:
                prefix = "::ffff:"
            thex = prefix + inet4_ntoa(address[12:])
        else:
            thex = (
                ":".join(chunks[:best_start])
                + "::"
                + ":".join(chunks[best_start + best_len :])
            )
    else:
        thex = ":".join(chunks)

    return thex


def is_ipv4(addr: str) -> bool:
    try:
        socket.inet_aton(addr)
        return True
    except OSError:
        return False


def is_ipv6(addr: str) -> bool:
    try:
        socket.inet_pton(socket.AF_INET6, addr)
        return True
    except OSError:
        return False


def validate_length_of(hostname: str) -> None:
    """RFC 1035 impose a limit on a domain name length. We verify it there."""
    if len(hostname.strip(".")) > 253:
        raise UnicodeError("hostname to resolve exceed 253 characters")
    elif any([len(_) > 63 for _ in hostname.split(".")]):
        raise UnicodeError("at least one label to resolve exceed 63 characters")


def rfc1035_should_read(payload: bytes) -> bool:
    if not payload:
        return False
    if len(payload) <= 2:
        return True

    cursor = payload

    while True:
        expected_size: int = struct.unpack("!H", cursor[:2])[0]

        if len(cursor[2:]) == expected_size:
            return False
        elif len(cursor[2:]) < expected_size:
            return True

        cursor = cursor[2 + expected_size :]


def rfc1035_unpack(payload: bytes) -> tuple[bytes, ...]:
    cursor = payload
    packets = []

    while cursor:
        expected_size: int = struct.unpack("!H", cursor[:2])[0]

        packets.append(cursor[2 : 2 + expected_size])
        cursor = cursor[2 + expected_size :]

    return tuple(packets)


def rfc1035_pack(message: bytes) -> bytes:
    return struct.pack("!H", len(message)) + message


def read_name(data: bytes, offset: int) -> tuple[str, int]:
    """
    Read a DNS‐encoded name (with compression pointers) from data[offset:].
    Returns (name, new_offset).
    """
    labels = []
    visited = set()
    next_offset = None
    pointer_jumps = 0
    wire_length = 1

    while True:
        if offset < 0 or offset >= len(data):
            raise ValueError("DNS name is truncated")

        length = data[offset]
        marker = length & 0xC0
        if marker == 0xC0:
            if offset + 1 >= len(data):
                raise ValueError("DNS compression pointer is truncated")
            pointer = struct.unpack_from("!H", data, offset)[0] & 0x3FFF
            if pointer >= len(data):
                raise ValueError("DNS compression pointer is out of range")
            if pointer in visited:
                raise ValueError("DNS compression pointer cycle detected")
            visited.add(pointer)
            pointer_jumps += 1
            if pointer_jumps > 128:
                raise ValueError("DNS name has too many compression pointers")
            if next_offset is None:
                next_offset = offset + 2
            offset = pointer
            continue
        if marker:
            raise ValueError("DNS label has invalid marker bits")
        if length == 0:
            offset += 1
            break
        if offset + 1 + length > len(data):
            raise ValueError("DNS label is truncated")
        wire_length += length + 1
        if wire_length > 255:
            raise ValueError("Expanded DNS name exceeds 255 wire octets")
        offset += 1
        labels.append(data[offset : offset + length].decode("ascii"))
        offset += length
    return ".".join(labels), next_offset if next_offset is not None else offset


def parse_https_rdata(rdata: bytes) -> HttpsRecord:
    """
    Parse the RDATA of an SVCB/HTTPS record.
    Returns a dict with keys: priority, target, alpn, ipv4hint, ipv6hint, echconfig.
    """
    off = 0
    priority = struct.unpack_from("!H", rdata, off)[0]
    off += 2

    target, off = read_name(rdata, off)

    # pull out all the key/value params
    params = {}
    while off + 4 <= len(rdata):
        key, length = struct.unpack_from("!HH", rdata, off)
        off += 4
        params[key] = rdata[off : off + length]
        off += length

    # decode ALPN (key=1), IPv4 (4), IPv6 (6), ECHConfig (5)
    def parse_alpn(buf: bytes) -> list[str]:
        out = []
        i: int = 0
        while i < len(buf):
            ln = buf[i]
            out.append(buf[i + 1 : i + 1 + ln].decode())
            i += 1 + ln
        return out

    alpn: list[str] = parse_alpn(params.get(1, b""))
    ipv4 = [
        inet4_ntoa(params[4][i : i + 4]) for i in range(0, len(params.get(4, b"")), 4)
    ]
    ipv6 = [
        inet6_ntoa(params[6][i : i + 16]) for i in range(0, len(params.get(6, b"")), 16)
    ]
    echconfs = params.get(5, b"")

    return {
        "priority": priority,
        "target": target or ".",  # empty name → root
        "alpn": alpn,
        "ipv4hint": ipv4,
        "ipv6hint": ipv6,
        "echconfig": echconfs,
    }


__all__ = (
    "inet4_ntoa",
    "inet6_ntoa",
    "is_ipv4",
    "is_ipv6",
    "validate_length_of",
    "rfc1035_pack",
    "rfc1035_unpack",
    "rfc1035_should_read",
    "parse_https_rdata",
    "read_name",
)
