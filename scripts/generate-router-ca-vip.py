#!/usr/bin/env python3
"""Provision a time-bounded Router-CA ULA IPv6 alias from Home-CA metadata.

The resulting address is an identifier/locator, NOT a cryptographic key and
NOT a certificate or proof of trust. Generated runtime material stays on host.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import secrets
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

DEFAULT_METADATA = Path("/var/lib/nls-netos/nls-router-ca/home-ca/home-ca-metadata.json")
DEFAULT_KEY = Path("/var/lib/nls-netos/crypto/sha-512/r-ca-vip.key")
DEFAULT_RECORD = Path("/var/lib/nls-netos/nls-router-ca/home-ca/home-ca-vip.json")
DOMAIN = b"NLS-NETOS:ROUTER-CA:VIP:v1\x00"


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def atomic_write(path: Path, data: bytes, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.chown(temporary, 0, 0)
        os.replace(temporary, path)
        os.chown(path, 0, 0)
        os.chmod(path, mode)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def load_metadata(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"CA metadata is missing or is not a regular file: {path}")
    with path.open("r", encoding="utf-8") as stream:
        metadata = json.load(stream)
    if not isinstance(metadata, dict):
        raise ValueError("CA metadata root must be a JSON object")
    return metadata


def existing_unexpired(key_path: Path, record_path: Path, metadata_sha256: str, now: datetime) -> str | None:
    try:
        if key_path.is_symlink() or record_path.is_symlink():
            raise ValueError("VIP output path must not be a symbolic link")
        record = json.loads(record_path.read_text(encoding="utf-8"))
        address = key_path.read_text(encoding="ascii").strip()
        parsed = ipaddress.IPv6Address(address)
        expiry = datetime.fromisoformat(record["expires_at"].replace("Z", "+00:00"))
        if (record.get("metadata_sha256") == metadata_sha256
                and record.get("algorithm") == "SHA-512"
                and record.get("address") == str(parsed)
                and parsed in ipaddress.IPv6Network("fc00::/7")
                and expiry > now):
            return str(parsed)
    except FileNotFoundError:
        return None
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None
    return None


def generate(metadata: dict[str, Any], now: datetime) -> tuple[str, dict[str, Any]]:
    metadata_bytes = canonical_json(metadata)
    metadata_sha256 = hashlib.sha256(metadata_bytes).hexdigest()
    issued_at = iso_utc(now)
    expires_at = iso_utc(now + timedelta(hours=24))
    nonce = secrets.token_bytes(32)

    # Domain-separated SHA-512 over canonical CA metadata, UTC issuance time,
    # and a fresh 256-bit CSPRNG nonce. Randomly select one of four 128-bit
    # digest blocks, then place it in the locally-scoped ULA fc00::/7 space.
    digest = hashlib.sha512(DOMAIN + metadata_bytes + b"\x00" + issued_at.encode("ascii") + b"\x00" + nonce).digest()
    block_index = secrets.randbelow(4)
    address_bytes = bytearray(digest[block_index * 16:(block_index + 1) * 16])
    address_bytes[0] = (address_bytes[0] & 0x03) | 0xFC
    address = str(ipaddress.IPv6Address(bytes(address_bytes)))

    record = {
        "schema_version": 1,
        "identity_type": "HOME_ROUTER_CA_VIP",
        "address": address,
        "address_scope": "ULA (fc00::/7); local/private routing only",
        "algorithm": "SHA-512",
        "derivation": "SHA-512(domain || canonical_CA_metadata || UTC_issued_at || CSPRNG_nonce); random 128-bit digest block; ULA prefix applied",
        "digest_block_index": block_index,
        "metadata_source": str(DEFAULT_METADATA),
        "metadata_sha256": metadata_sha256,
        "nonce_hex": nonce.hex(),
        "issued_at": issued_at,
        "expires_at": expires_at,
        "validity_seconds": 86400,
        "time_source": "system UTC clock",
        "trust_status": "NOT_ESTABLISHED",
        "note": "This VIP is an address identifier, not a cryptographic key or certificate."
    }
    return address, record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, default=DEFAULT_METADATA)
    parser.add_argument("--key-output", type=Path, default=DEFAULT_KEY)
    parser.add_argument("--record-output", type=Path, default=DEFAULT_RECORD)
    parser.add_argument("--force", action="store_true", help="replace an existing VIP even if it has not expired")
    args = parser.parse_args()

    if os.geteuid() != 0:
        print("ERROR: run as root", file=sys.stderr)
        return 1

    try:
        metadata = load_metadata(args.metadata)
        metadata_sha256 = hashlib.sha256(canonical_json(metadata)).hexdigest()
        now = utc_now()
        if not args.force:
            current = existing_unexpired(args.key_output, args.record_output, metadata_sha256, now)
            if current:
                print(f"Existing unexpired Router-CA VIP preserved: {current}")
                return 0

        address, record = generate(metadata, now)
        # Persist the companion record first. If the second write fails, the
        # next invocation will detect the incomplete pair and safely replace it.
        atomic_write(args.record_output, (json.dumps(record, indent=2) + "\n").encode("utf-8"))
        atomic_write(args.key_output, (address + "\n").encode("ascii"))
        print(f"Router-CA VIP: {address}")
        print(f"Generated: {record['issued_at']}")
        print(f"Expires:   {record['expires_at']}")
        print(f"Address file: {args.key_output}")
        print(f"Metadata:     {args.record_output}")
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
