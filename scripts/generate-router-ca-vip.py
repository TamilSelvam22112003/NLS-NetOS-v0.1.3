#!/usr/bin/env python3
"""Generate a time-bound Home Router-CA virtual IPv6 identifier.

The SHA-512 output is an integrity-derived identifier input, not a secret key
and not an authentication credential. The generated IPv6 address is a candidate
vIP; it must not be treated as trusted until Router-CA trust validation passes.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import secrets
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

DATA_ROOT = Path("/var/lib/nls-netos")
METADATA_PATH = DATA_ROOT / "nls-router-ca/home-ca/home-ca-metadata.json"
VIP_DIR = DATA_ROOT / "nls-router-ca/home-ca"
VIP_RECORD = VIP_DIR / "home-ca-vip.json"
DIGEST_DIR = DATA_ROOT / "crypto/sha-512"
DIGEST_FILE = DIGEST_DIR / "r-ca-vip.key"
DEFAULT_TTL_HOURS = 24
DOMAIN = b"NLS-NetOS/Router-CA/vIP/v1\x00"


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def atomic_write(path: Path, content: str, mode: int) -> None:
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp_name, mode)
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def canonical_metadata(metadata: dict) -> bytes:
    # Ignore only the boot-time inspection timestamp; it is operational noise
    # and would otherwise change the vIP on every reboot.
    snapshot = json.loads(json.dumps(metadata))
    management = snapshot.get("management")
    if isinstance(management, dict):
        management.pop("last_inspected", None)
    return json.dumps(
        snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def main() -> int:
    if os.geteuid() != 0:
        print("[nls-vip] ERROR: run as root", file=sys.stderr)
        return 1

    try:
        metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"[nls-vip] Metadata not found; skipping: {METADATA_PATH}")
        return 0
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[nls-vip] ERROR: cannot read CA metadata: {exc}", file=sys.stderr)
        return 1

    if not isinstance(metadata, dict):
        print("[nls-vip] ERROR: CA metadata must be a JSON object", file=sys.stderr)
        return 1

    cert = metadata.get("certificate")
    if not isinstance(cert, dict) or cert.get("present") is not True:
        print("[nls-vip] CA certificate is not present; vIP generation skipped")
        return 0

    cert_fingerprint = cert.get("sha256_fingerprint")
    if not isinstance(cert_fingerprint, str) or not cert_fingerprint.strip():
        print("[nls-vip] CA certificate fingerprint missing; vIP generation skipped")
        return 0

    try:
        ttl_hours = int(os.environ.get("NLS_CA_VIP_TTL_HOURS", DEFAULT_TTL_HOURS))
    except ValueError:
        print("[nls-vip] ERROR: NLS_CA_VIP_TTL_HOURS must be an integer", file=sys.stderr)
        return 1
    if not 1 <= ttl_hours <= 168:
        print("[nls-vip] ERROR: vIP TTL must be between 1 and 168 hours", file=sys.stderr)
        return 1

    metadata_bytes = canonical_metadata(metadata)
    metadata_sha256 = hashlib.sha256(metadata_bytes).hexdigest()
    now = utc_now()

    # Reuse the current address while its metadata snapshot and lifetime remain valid.
    try:
        current = json.loads(VIP_RECORD.read_text(encoding="utf-8"))
        expires = datetime.fromisoformat(current["expires_at"].replace("Z", "+00:00"))
        if (
            current.get("metadata_sha256") == metadata_sha256
            and current.get("certificate_sha256_fingerprint") == cert_fingerprint
            and expires > now
            and current.get("ipv6_address")
        ):
            print(f"[nls-vip] Existing vIP remains valid: {current['ipv6_address']}")
            return 0
    except (FileNotFoundError, OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        pass

    created_at = now
    expires_at = created_at + timedelta(hours=ttl_hours)
    nonce = secrets.token_bytes(32)
    timestamp = iso_utc(created_at)

    # Hash a domain-separated, canonical, unambiguous input structure.
    payload = (
        DOMAIN
        + len(metadata_bytes).to_bytes(8, "big")
        + metadata_bytes
        + timestamp.encode("ascii")
        + b"\x00"
        + nonce
    )
    digest = hashlib.sha512(payload).digest()
    digest_hex = digest.hex()

    # Use the first 128 digest bits, then constrain the top three bits to
    # 001 (2000::/3 global-unicast space used by the NLS address policy).
    raw_128 = int.from_bytes(digest[:16], "big")
    ipv6_value = (raw_128 & ((1 << 125) - 1)) | (1 << 125)
    ipv6_address = ipaddress.IPv6Address(ipv6_value).exploded

    DIGEST_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    VIP_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chown(DIGEST_DIR, 0, 0)
    os.chmod(DIGEST_DIR, 0o700)
    os.chown(VIP_DIR, 0, 0)
    os.chmod(VIP_DIR, 0o700)

    # This file contains a digest, not a reusable cryptographic secret.
    atomic_write(DIGEST_FILE, digest_hex + "\n", 0o600)

    trust = metadata.get("trust", {})
    trusted = (
        isinstance(trust, dict)
        and trust.get("trust_status") == "TRUSTED"
        and trust.get("enabled") is True
        and trust.get("certificate_chain_verified") is True
    )
    record = {
        "schema_version": 1,
        "identifier_type": "router_ca_virtual_ipv6",
        "status": "ACTIVE" if trusted else "PENDING_TRUST",
        "ipv6_address": ipv6_address,
        "address_policy": "2000::/3",
        "hash_algorithm": "SHA-512",
        "digest_file": str(DIGEST_FILE),
        "digest_bits": 512,
        "address_source_bits": "first_128_bits_with_2000::/3_policy_mask",
        "metadata_file": str(METADATA_PATH),
        "metadata_sha256": metadata_sha256,
        "certificate_sha256_fingerprint": cert_fingerprint,
        "created_at": timestamp,
        "expires_at": iso_utc(expires_at),
        "ttl_seconds": ttl_hours * 3600,
        "nonce_hex": nonce.hex(),
        "nonce_bytes": len(nonce),
        "trust_validation_required": True,
        "notes": (
            "Candidate vIP only. Do not use as proof of identity or authorization. "
            "Activate only after independent Router-CA certificate-chain and trust validation."
        ),
    }
    atomic_write(VIP_RECORD, json.dumps(record, indent=2) + "\n", 0o600)

    for path in (DIGEST_FILE, VIP_RECORD):
        os.chown(path, 0, 0)
        os.chmod(path, 0o600)

    print(f"[nls-vip] Generated candidate vIP: {ipv6_address}")
    print(f"[nls-vip] Digest: {DIGEST_FILE}")
    print(f"[nls-vip] Record: {VIP_RECORD}")
    print(f"[nls-vip] Expires: {record['expires_at']} (UTC)")
    print(f"[nls-vip] Trust state: {record['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
