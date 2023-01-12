#!/usr/bin/env python

"""
Adapted from the docs of cryptography

Creates a key and self-signed certificate for local use
"""

import datetime
import os
import socket

# noinspection PyPackageRequirements
from cryptography.hazmat.backends import default_backend
# noinspection PyPackageRequirements
from cryptography.hazmat.primitives import hashes, serialization
# noinspection PyPackageRequirements
from cryptography.hazmat.primitives.asymmetric import rsa
# noinspection PyPackageRequirements
from cryptography import x509
# noinspection PyPackageRequirements
from cryptography.x509.oid import NameOID

from six import PY2, text_type


def localipv4():
    try:
        s_ipv4 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s_ipv4.connect(('1.2.3.4', 80))    # Option: use 100.64.1.1 (IANA-Reserved IPv4 Prefix for Shared Address Space)
        ipv4 = s_ipv4.getsockname()[0]
        s_ipv4.close()
    except (BaseException, Exception):
        ipv4 = None
    return ipv4


# Ported from cryptography/utils.py
def int_from_bytes(data, byteorder, signed=False):
    assert 'big' == byteorder
    assert not signed

    if not PY2:
        import binascii
        return int(binascii.hexlify(data), 16)

    # call bytes() on data to allow the use of bytearrays
    # noinspection PyUnresolvedReferences
    return int(bytes(data).encode('hex'), 16)


# Ported from cryptography/x509/base.py
def random_serial_number():
    return int_from_bytes(os.urandom(20), 'big') >> 1


# Ported from cryptography docs/x509/tutorial.rst (set with no encryption)
def generate_key(key_size=4096, output_file='server.key'):
    # Generate our key
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=key_size,
        backend=default_backend()
    )

    # Write our key to disk for safe keeping
    with open(output_file, 'wb') as f:
        f.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        ))

    return private_key


# Ported from cryptography docs/x509/tutorial.rst
def generate_local_cert(private_key, days_valid=3650, output_file='server.crt', loc_name=None, org_name=None):

    def_name = u'SickGear'

    # Various details about who we are. For a self-signed certificate the
    # subject and issuer are always the same.
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.LOCALITY_NAME, loc_name or def_name),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, org_name or def_name)
    ])

    # build Subject Alternate Names (aka SAN) list
    # First the host names, add with x509.DNSName():
    san_list = [x509.DNSName(u'localhost')]
    try:
        thishostname = text_type(socket.gethostname())
        san_list.append(x509.DNSName(thishostname))
    except (BaseException, Exception):
        pass

    # Then the host IP addresses, add with x509.IPAddress()
    # Inside a try-except, just to be sure
    try:
        # noinspection PyCompatibility
        from ipaddress import IPv4Address, IPv6Address
        san_list.append(x509.IPAddress(IPv4Address(u'127.0.0.1')))
        san_list.append(x509.IPAddress(IPv6Address(u'::1')))

        # append local v4 ip
        mylocalipv4 = localipv4()
        if mylocalipv4:
            san_list.append(x509.IPAddress(IPv4Address(u'' + mylocalipv4)))
    except (ImportError, Exception):
        pass

    cert = x509.CertificateBuilder() \
        .subject_name(subject) \
        .issuer_name(issuer) \
        .public_key(private_key.public_key()) \
        .not_valid_before(datetime.datetime.utcnow()) \
        .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=days_valid)) \
        .serial_number(random_serial_number()) \
        .add_extension(x509.SubjectAlternativeName(san_list), critical=True) \
        .sign(private_key, hashes.SHA256(), default_backend())

    # Write the certificate out to disk.
    with open(output_file, 'wb') as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))

    return cert
