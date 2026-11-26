from __future__ import annotations

import socket
import typing

from ....util.ssl_ import resolve_cert_reqs, ssl_wrap_socket
from ..dou import PlainResolver
from ..protocols import (
    DomainNameServerParseException,
    DomainNameServerQuery,
    DomainNameServerReturn,
    ProtocolResolver,
)
from ..utils import rfc1035_pack, rfc1035_should_read, rfc1035_unpack
from ..system import SystemResolver


class TLSResolver(PlainResolver):
    """
    Basic DNS resolver over TLS.
    Comply with RFC 7858: https://datatracker.ietf.org/doc/html/rfc7858
    """

    protocol = ProtocolResolver.DOT
    implementation = "ssl"

    def __init__(
        self,
        server: str,
        port: int | None = None,
        *patterns: str,
        **kwargs: typing.Any,
    ) -> None:
        if "timeout" in kwargs and isinstance(kwargs["timeout"], (int, float)):
            timeout = kwargs["timeout"]
        else:
            timeout = None

        if "source_address" in kwargs and isinstance(kwargs["source_address"], str):
            bind_ip, bind_port = kwargs["source_address"].split(":", 1)
        else:
            bind_ip, bind_port = "0.0.0.0", "0"

        self._socket = SystemResolver().create_connection(
            (server, port or 853),
            timeout=timeout,
            source_address=(bind_ip, int(bind_port))
            if bind_ip != "0.0.0.0" or bind_port != "0"
            else None,
            socket_options=((socket.IPPROTO_TCP, socket.TCP_NODELAY, 1, "tcp"),),
            socket_kind=socket.SOCK_STREAM,
        )

        super().__init__(server, port, *patterns, **kwargs)

        self._socket = ssl_wrap_socket(
            self._socket,
            server_hostname=server
            if "server_hostname" not in kwargs
            else kwargs["server_hostname"],
            keyfile=kwargs["key_file"] if "key_file" in kwargs else None,
            certfile=kwargs["cert_file"] if "cert_file" in kwargs else None,
            cert_reqs=resolve_cert_reqs(kwargs["cert_reqs"])
            if "cert_reqs" in kwargs
            else None,
            ca_certs=kwargs["ca_certs"] if "ca_certs" in kwargs else None,
            ssl_version=kwargs["ssl_version"] if "ssl_version" in kwargs else None,
            ciphers=kwargs["ciphers"] if "ciphers" in kwargs else None,
            ca_cert_dir=kwargs["ca_cert_dir"] if "ca_cert_dir" in kwargs else None,
            key_password=kwargs["key_password"] if "key_password" in kwargs else None,
            ca_cert_data=kwargs["ca_cert_data"] if "ca_cert_data" in kwargs else None,
            certdata=kwargs["cert_data"] if "cert_data" in kwargs else None,
            keydata=kwargs["key_data"] if "key_data" in kwargs else None,
        )

    def _exchange(
        self, queries: list[DomainNameServerQuery]
    ) -> list[DomainNameServerReturn]:
        with self._lock:
            for query in queries:
                # DNS over TLS requires a two-byte length prefix.
                self._socket.sendall(rfc1035_pack(bytes(query)))

        responses: list[DomainNameServerReturn] = []
        response_ids: set[int] = set()
        while len(responses) < len(queries):
            with self._lock:
                for query in queries:
                    dns_resp = self._completed.get(query.id)
                    if dns_resp is not None and query.id not in response_ids:
                        responses.append(dns_resp)
                        response_ids.add(query.id)
                if len(responses) == len(queries):
                    continue

                try:
                    payload = self._socket.recv(1500)
                    while rfc1035_should_read(payload):
                        extra = self._socket.recv(1500)
                        if not extra:
                            payload = b""
                            break
                        payload += extra
                except (
                    TimeoutError,
                    OSError,
                    socket.timeout,
                    ConnectionError,
                ) as e:
                    raise socket.gaierror(
                        "Got unexpectedly disconnected while waiting for name resolution"
                    ) from e

                if not payload:
                    # The state lock is already held; self.close() would acquire it again.
                    self._socket.close()
                    self._terminated = True
                    raise socket.gaierror(
                        "DNS server closed the connection before sending a complete response"
                    )

                for fragment in rfc1035_unpack(payload):
                    try:
                        dns_resp = DomainNameServerReturn(fragment)
                    except DomainNameServerParseException:
                        continue
                    pending_query = self._pending.get(dns_resp.id)
                    if (
                        pending_query is not None
                        and dns_resp.matches(pending_query)
                        and dns_resp.id not in self._completed
                    ):
                        self._completed[dns_resp.id] = dns_resp
        return responses


class GoogleResolver(
    TLSResolver
):  # Defensive: we do not cover specific vendors/DNS shortcut
    specifier = "google"

    def __init__(self, *patterns: str, **kwargs: typing.Any) -> None:
        if "server" in kwargs:
            kwargs.pop("server")
        if "port" in kwargs:
            port = kwargs["port"]
            kwargs.pop("port")
        else:
            port = None

        super().__init__("dns.google", port, *patterns, **kwargs)


class CloudflareResolver(
    TLSResolver
):  # Defensive: we do not cover specific vendors/DNS shortcut
    specifier = "cloudflare"

    def __init__(self, *patterns: str, **kwargs: typing.Any) -> None:
        if "server" in kwargs:
            kwargs.pop("server")
        if "port" in kwargs:
            port = kwargs["port"]
            kwargs.pop("port")
        else:
            port = None

        super().__init__("1.1.1.1", port, *patterns, **kwargs)


class AdGuardResolver(
    TLSResolver
):  # Defensive: we do not cover specific vendors/DNS shortcut
    specifier = "adguard"

    def __init__(self, *patterns: str, **kwargs: typing.Any) -> None:
        if "server" in kwargs:
            kwargs.pop("server")
        if "port" in kwargs:
            port = kwargs["port"]
            kwargs.pop("port")
        else:
            port = None

        super().__init__("unfiltered.adguard-dns.com", port, *patterns, **kwargs)


class OpenDNSResolver(
    TLSResolver
):  # Defensive: we do not cover specific vendors/DNS shortcut
    specifier = "opendns"

    def __init__(self, *patterns: str, **kwargs: typing.Any) -> None:
        if "server" in kwargs:
            kwargs.pop("server")
        if "port" in kwargs:
            port = kwargs["port"]
            kwargs.pop("port")
        else:
            port = None

        super().__init__("dns.opendns.com", port, *patterns, **kwargs)


class Quad9Resolver(
    TLSResolver
):  # Defensive: we do not cover specific vendors/DNS shortcut
    specifier = "quad9"

    def __init__(self, *patterns: str, **kwargs: typing.Any) -> None:
        if "server" in kwargs:
            kwargs.pop("server")
        if "port" in kwargs:
            port = kwargs["port"]
            kwargs.pop("port")
        else:
            port = None

        super().__init__("dns11.quad9.net", port, *patterns, **kwargs)
