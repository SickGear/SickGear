from __future__ import annotations

import base64

PEM_HEADER = "-----BEGIN CERTIFICATE-----"
PEM_FOOTER = "-----END CERTIFICATE-----"


def DER_cert_to_PEM_cert(der_cert_bytes: bytes) -> str:
    """Convert a DER-encoded certificate to PEM format."""
    f = str(base64.standard_b64encode(der_cert_bytes), "ASCII", "strict")
    ss = [PEM_HEADER]
    ss += [f[i : i + 64] for i in range(0, len(f), 64)]
    ss.append(PEM_FOOTER + "\n")
    return "\n".join(ss)


def PEM_cert_to_DER_cert(pem_cert_string: str) -> bytes:
    """Convert a PEM-encoded certificate to DER format."""
    # Strip header/footer and whitespace
    if not pem_cert_string.startswith(PEM_HEADER):
        raise ValueError(  # Defensive: stdlib cpy
            f"Invalid PEM encoding; must start with {PEM_HEADER}"
        )
    if not pem_cert_string.strip().endswith(PEM_FOOTER):
        raise ValueError(  # Defensive: stdlib cpy
            f"Invalid PEM encoding; must end with {PEM_FOOTER}"
        )
    d = pem_cert_string.strip()[len(PEM_HEADER) : -len(PEM_FOOTER)]
    return base64.decodebytes(d.encode("ASCII", "strict"))
