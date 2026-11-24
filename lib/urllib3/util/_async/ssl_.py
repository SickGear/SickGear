from __future__ import annotations

import io
import os
import typing
import warnings
from pathlib import Path

if typing.TYPE_CHECKING:
    from typing_extensions import Literal

from ...contrib.anytls import ssl, IS_NONSTDLIB

from ...contrib.imcc import load_cert_chain as _ctx_load_cert_chain
from ...contrib.ssa import AsyncSocket, SSLAsyncSocket
from ...exceptions import SSLError
from ..ssl_ import (
    ALPN_PROTOCOLS,
    _CacheableSSLContext,
    _cert_store_stats,
    _is_key_file_encrypted,
    create_urllib3_context,
)


_SSLContextCache = _CacheableSSLContext()


async def ssl_wrap_socket(
    sock: AsyncSocket,
    keyfile: str | None = None,
    certfile: str | None = None,
    cert_reqs: int | None = None,
    ca_certs: str | None = None,
    server_hostname: str | None = None,
    ssl_version: int | None = None,
    ciphers: str | None = None,
    ssl_context: ssl.SSLContext | None = None,
    ca_cert_dir: str | None = None,
    key_password: str | None = None,
    ca_cert_data: None | str | bytes = None,
    tls_in_tls: bool = False,
    alpn_protocols: list[str] | None = None,
    certdata: str | bytes | None = None,
    keydata: str | bytes | None = None,
    check_hostname: bool | None = None,
    ssl_minimum_version: int | None = None,
    ssl_maximum_version: int | None = None,
    ech_config_list: bytes | None = None,
    ssl_backend: Literal["rtls", "utls", "ssl"] | None = None,
) -> SSLAsyncSocket:
    """
    All arguments except for server_hostname, ssl_context, and ca_cert_dir have
    the same meaning as they do when using :func:`ssl.wrap_socket`.

    :param server_hostname:
        When SNI is supported, the expected hostname of the certificate
    :param ssl_context:
        A pre-made :class:`SSLContext` object. If none is provided, one will
        be created using :func:`create_urllib3_context`.
    :param ciphers:
        A string of ciphers we wish the client to support.
    :param ca_cert_dir:
        A directory containing CA certificates in multiple separate files, as
        supported by OpenSSL's -CApath flag or the capath argument to
        SSLContext.load_verify_locations().
    :param key_password:
        Optional password if the keyfile is encrypted.
    :param ca_cert_data:
        Optional string containing CA certificates in PEM format suitable for
        passing as the cadata parameter to SSLContext.load_verify_locations()
    :param tls_in_tls:
        No-op in asynchronous mode. Call wrap_socket of the SSLAsyncSocket later.
    :param alpn_protocols:
        Manually specify other protocols to be announced during tls handshake.
    :param certdata:
        Specify an in-memory client intermediary certificate for mTLS.
    :param keydata:
        Specify an in-memory client intermediary key for mTLS.
    :param ssl_backend:
        Force the TLS implementation (``"rtls"``, ``"utls"`` or ``"ssl"``)
        used to build the context. Ignored when ``ssl_context`` is provided.
    """
    context = ssl_context

    cache_disabled: bool = context is not None

    with _SSLContextCache.lock(
        keyfile,
        certfile if certfile is None else Path(certfile),
        cert_reqs,
        ca_certs,
        ssl_version,
        ciphers,
        ca_cert_dir if ca_cert_dir is None else Path(ca_cert_dir),
        alpn_protocols,
        certdata,
        keydata,
        key_password,
        ca_cert_data,
        os.getenv("SSLKEYLOGFILE", None),
        ssl_minimum_version,
        ssl_maximum_version,
        check_hostname,
        ssl_backend,
    ):
        cached_ctx = _SSLContextCache.get() if not cache_disabled else None

        if cached_ctx is None:
            if context is None:
                context = create_urllib3_context(
                    ssl_version,
                    cert_reqs,
                    ciphers=ciphers,
                    ssl_minimum_version=ssl_minimum_version,
                    ssl_maximum_version=ssl_maximum_version,
                    ssl_backend=ssl_backend,
                )

            if cert_reqs is not None:
                context.verify_mode = cert_reqs  # type: ignore[assignment]

            if check_hostname is not None:
                context.check_hostname = check_hostname

            if ca_certs or ca_cert_dir or ca_cert_data:
                # SSLContext does not support bytes for cadata[...]
                if ca_cert_data and isinstance(ca_cert_data, bytes):
                    ca_cert_data = ca_cert_data.decode()

                try:
                    context.load_verify_locations(ca_certs, ca_cert_dir, ca_cert_data)
                except OSError as e:
                    raise SSLError(e) from e

            elif hasattr(context, "load_default_certs"):
                try:
                    store_stats = _cert_store_stats(context)
                    # try to load OS default certs; works well on Windows.
                    if "x509_ca" not in store_stats or not store_stats["x509_ca"]:
                        context.load_default_certs()
                except (
                    AttributeError,
                    NotImplementedError,
                ):  # Defensive: 3rd party SSLContext implementation (e.g. truststore)
                    pass

            # Attempt to detect if we get the goofy behavior of the
            # keyfile being encrypted and OpenSSL asking for the
            # passphrase via the terminal and instead error out.
            if keyfile and key_password is None and _is_key_file_encrypted(keyfile):
                raise SSLError("Client private key is encrypted, password is required")

            if certfile:
                if key_password is None:
                    context.load_cert_chain(certfile, keyfile)
                else:
                    context.load_cert_chain(certfile, keyfile, key_password)
            elif certdata and keydata:
                if IS_NONSTDLIB:
                    context.load_cert_chain(certdata, keydata, key_password)
                else:
                    try:
                        _ctx_load_cert_chain(context, certdata, keydata, key_password)
                    except io.UnsupportedOperation as e:
                        warnings.warn(
                            "Passing in-memory client/intermediary certificate for mTLS is unsupported on your platform. "
                            f"Reason: {e}. It will be picked out if you upgrade to a QUIC connection or if you install "
                            "alternative ssl backend (rtls/utls).",
                            UserWarning,
                        )

            try:
                context.set_alpn_protocols(alpn_protocols or ALPN_PROTOCOLS)
            except (
                NotImplementedError
            ):  # Defensive: in CI, we always have set_alpn_protocols
                pass

            if ciphers:
                context.set_ciphers(ciphers)

            if not cache_disabled:
                _SSLContextCache.save(context)
        else:
            context = cached_ctx

    if ech_config_list and hasattr(context, "set_ech_configs"):
        # we need to mutate the ctx, so it's going to be a copy
        # ech config list is specific to a single connection.
        context = context.set_ech_configs(ech_config_list)

    return await sock.wrap_socket(context, server_hostname=server_hostname)
