from __future__ import annotations

from ...backend import HttpVersion
from .protocol import ExtensionFromHTTP


class RawExtensionFromHTTP(ExtensionFromHTTP):
    """Raw I/O from given HTTP stream after a 101 Switching Protocol Status."""

    @staticmethod
    def supported_svn() -> set[HttpVersion]:
        return {HttpVersion.h11, HttpVersion.h2, HttpVersion.h3}

    def headers(self, http_version: HttpVersion) -> dict[str, str]:
        """Specific HTTP headers required (request) before the 101 status response."""
        return {}

    def close(self) -> None:
        """End/Notify close for sub protocol."""
        if self._dsa is not None:
            try:
                self._dsa.close()
            except OSError:
                # A failed FIN write must not prevent response cleanup below.
                pass
            self._dsa = None
        if self._response is not None:
            self._response.close()
            self._response = None
        self._police_officer = None

    @staticmethod
    def implementation() -> str:
        return "raw"  # Defensive: metadata for the implicit raw extension.

    @staticmethod
    def supported_schemes() -> set[str]:
        return set()

    @staticmethod
    def scheme_to_http_scheme(scheme: str) -> str:
        return scheme  # Defensive: raw extensions define no URL scheme.

    def next_payload(self) -> bytes | None:
        if self._police_officer is None or self._dsa is None:
            raise OSError("The HTTP extension is closed or uninitialized")
        with self._police_officer.borrow(self._response):
            with self._read_error_catcher():
                data, eot, _ = self._dsa.recv_extended(None)
            return data

    def send_payload(self, buf: str | bytes) -> None:
        if self._police_officer is None or self._dsa is None:
            raise OSError("The HTTP extension is closed or uninitialized")

        if isinstance(buf, str):
            buf = buf.encode()

        with self._police_officer.borrow(self._response):
            with self._write_error_catcher():
                self._dsa.sendall(buf)
