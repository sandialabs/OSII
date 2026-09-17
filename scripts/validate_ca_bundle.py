"""Validate an explicitly supplied PEM CA bundle before a container build."""

from __future__ import annotations

import argparse
import base64
import hashlib
import re
import ssl
from pathlib import Path


CERTIFICATE_PATTERN = re.compile(
    rb"-----BEGIN CERTIFICATE-----\s*(.*?)\s*-----END CERTIFICATE-----",
    re.DOTALL,
)
PRIVATE_KEY_PATTERN = re.compile(rb"-----BEGIN [^-\r\n]*PRIVATE KEY-----")
MAX_BUNDLE_BYTES = 10 * 1024 * 1024


def validate_ca_bundle(path: Path) -> tuple[str, ...]:
    if not path.is_file():
        raise ValueError(f"CA bundle is not a readable file: {path}")

    contents = path.read_bytes()
    if not contents:
        raise ValueError("CA bundle is empty")
    if len(contents) > MAX_BUNDLE_BYTES:
        raise ValueError("CA bundle is larger than 10 MiB")
    if PRIVATE_KEY_PATTERN.search(contents):
        raise ValueError("CA bundle contains a private key; provide public certificates only")

    matches = CERTIFICATE_PATTERN.findall(contents)
    if not matches:
        raise ValueError("CA bundle does not contain a PEM CERTIFICATE block")
    if contents.count(b"-----BEGIN CERTIFICATE-----") != len(matches):
        raise ValueError("CA bundle contains an incomplete CERTIFICATE block")

    fingerprints: list[str] = []
    for index, encoded in enumerate(matches, start=1):
        try:
            der = base64.b64decode(re.sub(rb"\s+", b"", encoded), validate=True)
            pem = ssl.DER_cert_to_PEM_cert(der)
            ssl.PEM_cert_to_DER_cert(pem)
        except (ValueError, UnicodeError) as exc:
            raise ValueError(f"certificate {index} is not valid PEM-encoded X.509 data") from exc
        fingerprints.append(hashlib.sha256(der).hexdigest())

    try:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(cafile=str(path))
    except ssl.SSLError as exc:
        raise ValueError(f"CA bundle cannot be loaded as a trust bundle: {exc}") from exc

    return tuple(fingerprints)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument(
        "--digest-only",
        action="store_true",
        help="print only the bundle SHA-256 digest after validation",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="also print the SHA-256 fingerprint of every certificate",
    )
    args = parser.parse_args()

    try:
        fingerprints = validate_ca_bundle(args.bundle)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    bundle_digest = hashlib.sha256(args.bundle.read_bytes()).hexdigest()
    if args.digest_only:
        print(bundle_digest)
        return 0

    print(f"Validated {len(fingerprints)} public certificate(s) in {args.bundle.resolve()}")
    print(f"Bundle SHA-256: {bundle_digest}")
    if args.verbose:
        for index, fingerprint in enumerate(fingerprints, start=1):
            print(f"Certificate {index} SHA-256: {fingerprint}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
