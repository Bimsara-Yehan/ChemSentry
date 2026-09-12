#!/usr/bin/env python3
"""Generate a local CA, server cert, and device/client certs for Mosquitto.

Creates files under `firmware/certs/` by default:
 - ca.key.pem, ca.crt.pem
 - server.key.pem, server.crt.pem
 - <device>.key.pem, <device>.crt.pem

Usage:
    python generate_certs.py --out firmware/certs --devices device1,device2
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timedelta
from ipaddress import ip_address

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def write_pem(path: str, data: bytes) -> None:
    with open(path, "wb") as f:
        f.write(data)


def gen_private_key(key_size: int = 2048) -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=key_size)


def gen_ca(subject_name: str, valid_days: int = 3650):
    key = gen_private_key(4096)
    subject = issuer = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, subject_name)]
    )
    now = datetime.utcnow()
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=valid_days))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    return key, cert


def gen_cert_signed(
    csr_name: str,
    san: list[str],
    issuer_key,
    issuer_cert,
    valid_days: int = 3650,
    key_size: int = 2048,
):
    key = gen_private_key(key_size)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, csr_name)])
    now = datetime.utcnow()
    builder = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(issuer_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=valid_days))
    )

    san_list = []
    for s in san:
        try:
            san_list.append(x509.IPAddress(ip_address(s)))
        except Exception:
            san_list.append(x509.DNSName(s))

    builder = builder.add_extension(
        x509.SubjectAlternativeName(san_list), critical=False
    )
    cert = builder.sign(private_key=issuer_key, algorithm=hashes.SHA256())
    return key, cert


def pem_private_key(key) -> bytes:
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )


def pem_cert(cert) -> bytes:
    return cert.public_bytes(serialization.Encoding.PEM)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="firmware/certs", help="output directory")
    parser.add_argument(
        "--devices",
        default="device1",
        help="comma-separated device/client common names to generate (default: device1)",
    )
    parser.add_argument(
        "--common-name", default="ChemSentry Local CA", help="CA common name"
    )
    args = parser.parse_args()

    out = os.path.abspath(args.out)
    ensure_dir(out)

    ca_key, ca_cert = gen_ca(args.common_name)
    write_pem(os.path.join(out, "ca.key.pem"), pem_private_key(ca_key))
    write_pem(os.path.join(out, "ca.crt.pem"), pem_cert(ca_cert))

    # Server cert (for broker) - include localhost and 127.0.0.1
    server_san = ["localhost", "127.0.0.1"]
    srv_key, srv_cert = gen_cert_signed(
        "chemsentry-mosquitto", server_san, ca_key, ca_cert
    )
    write_pem(os.path.join(out, "server.key.pem"), pem_private_key(srv_key))
    write_pem(os.path.join(out, "server.crt.pem"), pem_cert(srv_cert))

    # Device/client certs
    devices = [d.strip() for d in args.devices.split(",") if d.strip()]
    for d in devices:
        dev_key, dev_cert = gen_cert_signed(d, [d], ca_key, ca_cert)
        write_pem(os.path.join(out, f"{d}.key.pem"), pem_private_key(dev_key))
        write_pem(os.path.join(out, f"{d}.crt.pem"), pem_cert(dev_cert))

    print(f"Wrote certs to: {out}")


if __name__ == "__main__":
    main()
