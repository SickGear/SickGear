from __future__ import annotations

import ctypes
import os
import sys
import typing
from io import UnsupportedOperation

if typing.TYPE_CHECKING:
    import ssl


class _OpenSSL:
    """Access hazardous material from CPython OpenSSL (or compatible SSL) implementation."""

    def __init__(self) -> None:
        import platform

        if platform.python_implementation() != "CPython":
            raise UnsupportedOperation("Only CPython is supported")

        import ssl

        self._name = ssl.OPENSSL_VERSION
        self.ssl = ssl

        # bug seen in Windows + CPython < 3.11
        # where CPython official API for options
        # cast OpenSSL get_options to SIGNED long
        # where we want UNSIGNED long.
        _ssl_options_signed_long_bug = False

        if not hasattr(ssl, "_ssl"):
            raise UnsupportedOperation(  # Defensive: nonstandard ssl module lacks the CPython handle used by ctypes.
                "Unsupported interpreter due to missing private ssl module"
            )

        if platform.system() == "Windows":
            # possible search locations
            candidates = {
                os.path.dirname(sys.executable),
                os.path.join(sys.prefix, "DLLs"),
                sys.prefix,
            }

            if hasattr(ssl._ssl, "__file__"):
                candidates.add(os.path.dirname(ssl._ssl.__file__))

            _ssl_options_signed_long_bug = sys.version_info < (3, 11)

            ssl_potential_match = None
            crypto_potential_match = None

            for d in candidates:
                if not os.path.exists(d):
                    continue

                for filename in os.listdir(d):
                    if ssl_potential_match is None:
                        if filename.startswith("libssl") and filename.endswith(".dll"):
                            ssl_potential_match = os.path.join(d, filename)

                    if crypto_potential_match is None:
                        if filename.startswith("libcrypto") and filename.endswith(
                            ".dll"
                        ):
                            crypto_potential_match = os.path.join(d, filename)

                if crypto_potential_match and ssl_potential_match:
                    break

            if not ssl_potential_match or not crypto_potential_match:
                raise UnsupportedOperation(  # Defensive: this interpreter layout exposes no usable OpenSSL DLL pair.
                    "Could not locate OpenSSL DLLs next to Python; "
                    "check your /DLLs folder or your PATH."
                )

            self._ssl = ctypes.CDLL(ssl_potential_match)
            self._crypto = ctypes.CDLL(crypto_potential_match)
        else:
            # that's the most common path
            # ssl built in module already loaded both crypto and ssl
            # symbols.
            if hasattr(ssl._ssl, "__file__"):
                self._ssl = ctypes.CDLL(ssl._ssl.__file__)
            else:
                # _ssl is statically linked into the interpreter
                # (e.g. python-build-standalone via uv). The symbols are NOT
                # exported in the dynamic symbol table, and loading a system
                # libssl would be a different library instance whose functions
                # cannot safely operate on SSL_CTX* pointers created by the
                # statically-linked copy (segfault due to separate global state).
                # see https://github.com/jawah/urllib3.future/issues/325
                raise UnsupportedOperation(
                    "Unable to use ctypes: _ssl is statically linked into "
                    "the interpreter. Falling back to alternate methods."
                )

            self._crypto = self._ssl

        # we want to ensure a minimal set of symbols
        # are present. CPython should have at least:
        for required_symbol in [
            "SSL_CTX_use_certificate",
            "SSL_CTX_check_private_key",
            "SSL_CTX_use_PrivateKey",
        ]:
            if not hasattr(self._ssl, required_symbol):
                raise UnsupportedOperation(  # Defensive: the loaded libssl lacks a required native entry point.
                    f"Python interpreter built against '{self._name}' is unsupported. (libssl) {required_symbol} is not present."
                )

        for required_symbol in [
            "BIO_free",
            "BIO_new_mem_buf",
            "PEM_read_bio_X509",
            "PEM_read_bio_PrivateKey",
            "ERR_get_error",
            "ERR_clear_error",
            "ERR_error_string",
        ]:
            if not hasattr(self._crypto, required_symbol):
                raise UnsupportedOperation(  # Defensive: the loaded libcrypto lacks a required native entry point.
                    f"Python interpreter built against '{self._name}' is unsupported. (libcrypto) {required_symbol} is not present."
                )

        # https://docs.openssl.org/3.0/man3/SSL_CTX_use_certificate/
        self.SSL_CTX_use_certificate = self._ssl.SSL_CTX_use_certificate
        self.SSL_CTX_use_certificate.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self.SSL_CTX_use_certificate.restype = ctypes.c_int

        self.SSL_CTX_check_private_key = self._ssl.SSL_CTX_check_private_key
        self.SSL_CTX_check_private_key.argtypes = [ctypes.c_void_p]
        self.SSL_CTX_check_private_key.restype = ctypes.c_int

        # https://docs.openssl.org/3.0/man3/BIO_new/
        self.BIO_free = self._crypto.BIO_free
        self.BIO_free.argtypes = [ctypes.c_void_p]
        self.BIO_free.restype = None

        self.BIO_new_mem_buf = self._crypto.BIO_new_mem_buf
        self.BIO_new_mem_buf.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self.BIO_new_mem_buf.restype = ctypes.c_void_p

        # https://docs.openssl.org/3.0/man3/PEM_read_bio_PrivateKey/
        self.PEM_read_bio_X509 = self._crypto.PEM_read_bio_X509
        self.PEM_read_bio_X509.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
        ]
        self.PEM_read_bio_X509.restype = ctypes.c_void_p

        self.PEM_read_bio_PrivateKey = self._crypto.PEM_read_bio_PrivateKey
        self.PEM_read_bio_PrivateKey.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
        ]
        self.PEM_read_bio_PrivateKey.restype = ctypes.c_void_p

        # https://docs.openssl.org/3.0/man3/SSL_CTX_use_certificate/
        self.SSL_CTX_use_PrivateKey = self._ssl.SSL_CTX_use_PrivateKey
        self.SSL_CTX_use_PrivateKey.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self.SSL_CTX_use_PrivateKey.restype = ctypes.c_int

        self.ERR_get_error = self._crypto.ERR_get_error
        self.ERR_get_error.argtypes = []
        self.ERR_get_error.restype = ctypes.c_ulong

        self.ERR_clear_error = self._crypto.ERR_clear_error
        self.ERR_clear_error.argtypes = []
        self.ERR_clear_error.restype = None

        self.ERR_error_string = self._crypto.ERR_error_string
        self.ERR_error_string.argtypes = [ctypes.c_ulong, ctypes.c_char_p]
        self.ERR_error_string.restype = ctypes.c_char_p

        if hasattr(self._ssl, "SSL_CTX_get_options"):
            self.SSL_CTX_get_options = self._ssl.SSL_CTX_get_options
            self.SSL_CTX_get_options.argtypes = [ctypes.c_void_p]
            self.SSL_CTX_get_options.restype = (
                ctypes.c_ulong if not _ssl_options_signed_long_bug else ctypes.c_long
            )  # OpenSSL's options are long
        elif hasattr(self._ssl, "SSL_CTX_ctrl"):
            # some old build inline SSL_CTX_get_options (mere C define)
            # define SSL_CTX_get_options(ctx) SSL_CTX_ctrl((ctx),SSL_CTRL_OPTIONS,0,NULL)
            # define SSL_CTRL_OPTIONS                        32

            self.SSL_CTX_ctrl = self._ssl.SSL_CTX_ctrl
            self.SSL_CTX_ctrl.argtypes = [
                ctypes.c_void_p,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_void_p,
            ]
            self.SSL_CTX_ctrl.restype = (
                ctypes.c_ulong if not _ssl_options_signed_long_bug else ctypes.c_long
            )

            self.SSL_CTX_get_options = lambda ctx: self.SSL_CTX_ctrl(  # type: ignore[assignment]
                ctx, 32, 0, None
            )
        else:
            raise UnsupportedOperation()  # Defensive: neither supported native options accessor is available.

    def pull_error(self) -> typing.NoReturn:
        raise self.ssl.SSLError(
            self.ERR_error_string(
                self.ERR_get_error(), ctypes.create_string_buffer(256)
            ).decode()
        )


_IS_GIL_DISABLED = hasattr(sys, "_is_gil_enabled") and sys._is_gil_enabled() is False

_head_extra_fields = []

if sys.flags.debug:  # Defensive: legacy ABI compatibility.
    # TODO: Investigate ABI detection: sys.flags.debug does not identify Py_TRACE_REFS.
    # In debug builds (_POSIX_C_SOURCE or Py_DEBUG is defined), PyObject_HEAD
    # is preceded by _PyObject_HEAD_EXTRA, which typically consists of
    # two pointers (_ob_next, _ob_prev).
    _head_extra_fields = [("_ob_next", ctypes.c_void_p), ("_ob_prev", ctypes.c_void_p)]

# PyObject_HEAD layout differs between GIL and free-threaded builds.
#
# GIL build (16 bytes):
#   Py_ssize_t ob_refcnt;      // 8 bytes
#   PyTypeObject *ob_type;     // 8 bytes
#
# Free-threaded build (32 bytes):
#   uintptr_t ob_tid;          // 8 bytes
#   uint16_t  ob_flags;        // 2 bytes  (called _padding in 3.13)
#   PyMutex   ob_mutex;        // 1 byte   (uint8_t)
#   uint8_t   ob_gc_bits;      // 1 byte
#   uint32_t  ob_ref_local;    // 4 bytes
#   Py_ssize_t ob_ref_shared;  // 8 bytes
#   PyTypeObject *ob_type;     // 8 bytes
if _IS_GIL_DISABLED:
    _pyobject_head_fields = [
        ("ob_tid", ctypes.c_size_t),
        ("ob_flags", ctypes.c_uint16),
        ("ob_mutex", ctypes.c_uint8),
        ("ob_gc_bits", ctypes.c_uint8),
        ("ob_ref_local", ctypes.c_uint32),
        ("ob_ref_shared", ctypes.c_ssize_t),
        ("ob_type", ctypes.c_void_p),
    ]
else:
    _pyobject_head_fields = [
        ("ob_refcnt", ctypes.c_ssize_t),
        ("ob_type", ctypes.c_void_p),
    ]


# Define the PySSLContext C structure using ctypes.
# This definition assumes that 'SSL_CTX *ctx' is the first member
# immediately following PyObject_HEAD. This has been observed to be
# the case in various CPython versions (e.g., 3.7 through 3.14 so far).
#
# CPython's Modules/_ssl.c (simplified):
# typedef struct {
#     PyObject_HEAD
#     SSL_CTX *ctx;
#     // ... other members ...
# } PySSLContextObject;
#
class PySSLContextStruct(ctypes.Structure):
    _fields_ = (
        _head_extra_fields  # type: ignore[assignment]
        + _pyobject_head_fields
        + [
            ("ssl_ctx", ctypes.c_void_p),  # SSL_CTX *ctx; (this is the pointer we want)
            # If there were other C members between ob_type and ssl_ctx,
            # they would need to be defined here with their correct types and padding.
        ]
    )


def _split_client_cert(data: bytes) -> list[bytes]:
    line_ending = b"\n" if b"-----\r\n" not in data else b"\r\n"
    boundary = b"-----END CERTIFICATE-----" + line_ending

    certificates = []

    for chunk in data.split(boundary):
        if chunk:
            start_marker = chunk.find(b"-----BEGIN CERTIFICATE-----" + line_ending)
            if start_marker == -1:
                break
            pem_reconstructed = b"".join([chunk[start_marker:], boundary])
            certificates.append(pem_reconstructed)

    return certificates


def load_cert_chain(
    ctx: ssl.SSLContext,
    certdata: bytes | str,
    keydata: bytes | str,
    password: bytes | str | typing.Callable[[], str | bytes] | None = None,
) -> None:
    """
    Unique workaround the known limitation of CPython inability to initialize the mTLS context without files.
    :raise UnsupportedOperation: If anything goes wrong in the process.
    """
    lib = _OpenSSL()

    # Get the memory address of the Python ssl.SSLContext object.
    # id() returns the address of the PyObject.
    addr = id(ctx)

    # Cast this memory address to a pointer to our defined PySSLContextStruct.
    ptr_to_pysslcontext_struct = ctypes.cast(addr, ctypes.POINTER(PySSLContextStruct))

    # Access the 'ssl_ctx' field from the structure. This field holds the
    # actual SSL_CTX* C pointer value.
    ssl_ctx_address = ptr_to_pysslcontext_struct.contents.ssl_ctx

    # We want to ensure we got the right pointer address
    # the safest way to achieve that is to retrieve options
    # and compare it with the official ctx property.
    if lib.SSL_CTX_get_options is not None:
        bypass_options = lib.SSL_CTX_get_options(ssl_ctx_address)
        expected_options = int(ctx.options)

        if bypass_options != expected_options:  # Defensive: ABI sanity check.
            raise UnsupportedOperation(
                f"CPython internal SSL_CTX changed! Cannot pursue safely. Expected = {expected_options:x} Actual = {bypass_options:x}"
            )

    # normalize inputs
    if isinstance(certdata, str):
        certdata = certdata.encode()
    if isinstance(keydata, str):
        keydata = keydata.encode()

    client_chain = _split_client_cert(certdata)

    leaf_certificate = client_chain[0]

    # Use a BIO to read the client certificate
    # only the leaf certificate is supported here.
    cert_bio = lib.BIO_new_mem_buf(leaf_certificate, len(leaf_certificate))

    if not cert_bio:
        raise MemoryError(
            "Unable to allocate memory to load the client certificate"
        )  # Defensive: native certificate BIO allocation failed.

    # Use a BIO to load the key in-memory
    key_bio = lib.BIO_new_mem_buf(keydata, len(keydata))

    if not key_bio:
        raise MemoryError(
            "Unable to allocate memory to load the client key"
        )  # Defensive: native private-key BIO allocation failed.

    # prepare the password
    if callable(password):
        password = password()

    if isinstance(password, str):
        password = password.encode()

    assert password is None or isinstance(password, bytes)

    # the allocated X509 obj MUST NOT be freed by ourselves
    # OpenSSL internals will free it once not needed.
    cert = lib.PEM_read_bio_X509(cert_bio, None, None, None)

    # we do own the BIO, once the X509 leaf is instantiated, no need
    # to keep it afterward.
    lib.BIO_free(cert_bio)

    if not cert:
        lib.pull_error()

    pkey = lib.PEM_read_bio_PrivateKey(key_bio, None, None, password)

    lib.BIO_free(key_bio)

    if not pkey:
        lib.pull_error()

    if lib.SSL_CTX_use_certificate(ssl_ctx_address, cert) != 1:
        lib.pull_error()

    if lib.SSL_CTX_use_PrivateKey(ssl_ctx_address, pkey) != 1:
        lib.pull_error()

    if lib.SSL_CTX_check_private_key(ssl_ctx_address) != 1:
        lib.pull_error()

    # Unfortunately, most of the time
    # SSL_CTX_add_extra_chain_cert is unavailable
    # in the final CPython build.
    # According to OpenSSL latest docs: "The engine
    # will attempt to build the required chain for the CA store"
    # It's not going to be used as a trust anchor! (i.e. not self-signed)
    # "If no chain is specified, the library will try to complete the
    # chain from the available CA certificates in the trusted
    # CA storage, see SSL_CTX_load_verify_locations(3)."
    # see: https://docs.openssl.org/master/man3/SSL_CTX_add_extra_chain_cert/#notes
    if len(client_chain) > 1:
        ctx.load_verify_locations(cadata=(b"\n".join(client_chain[1:])).decode())


__all__ = ("load_cert_chain",)
