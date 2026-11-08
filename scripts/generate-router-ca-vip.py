#!/usr/bin/env python3
"""Generate a time-bound SHA-512-derived Home Router-CA virtual IPv6 identifier.

The digest and vIP are identifiers, not secret keys or authentication credentials.
"""
from __future__ import annotations

import fcntl
import hashlib
import ipaddress
import json
import os
import re
import secrets
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

DATA_ROOT = Path(os.environ.get("NLS_DATA_ROOT", "/var/lib/nls-netos"))
METADATA_PATH = DATA_ROOT / "nls-router-ca/home-ca/home-ca-metadata.json"
VIP_DIR = DATA_ROOT / "nls-router-ca/home-ca"
VIP_RECORD = VIP_DIR / "home-ca-vip.json"
DIGEST_DIR = DATA_ROOT / "crypto/sha-512"
DIGEST_FILE = DIGEST_DIR / "r-ca-vip.key"
LOCK_FILE = VIP_DIR / ".home-ca-vip.lock"
DEFAULT_TTL_HOURS = 24
DOMAIN = b"NLS-NetOS/Router-CA/vIP/v1\\x00"
GLOBAL_UNICAST = ipaddress.IPv6Network("2000::/3")


def utc_now() -> datetime:
    """Return a second-precision UTC timestamp suitable for audit records."""
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def atomic_write(path: Path, content: str, mode: int) -> None:
    """Atomically replace a file in its destination directory."""
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp_name, mode)
        os.replace(temp_name, path)
        dir_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def canonical_metadata(metadata: dict) -> bytes:
    """Serialize stable metadata; exclude the volatile inspection timestamp."""
    snapshot = json.loads(json.dumps(metadata))
    management = snapshot.get("management")
    if isinstance(management, dict):
        management.pop("last_inspected", None)
    return json.dumps(
        snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def address_from_digest(digest: bytes) -> str:
    """Map the first 128 digest bits into the NLS 2000::/3 address policy."""
    if len(digest) != hashlib.sha512().digest_size:
        raise ValueError("expected a complete SHA-512 digest")
    raw_128 = int.from_bytes(digest[:16], "big")
    # Set the high three bits to 001, preserving 125 digest-derived bits.
    value = (raw_128 & ((1 << 125) - 1)) | (1 << 125)
    address = ipaddress.IPv6Address(value)
    if address not in GLOBAL_UNICAST:
        raise ValueError("derived address is outside the configured 2000::/3 policy")
    return address.exploded


def load_current_record(metadata_sha256: str, now: datetime) -> dict | None:
    """Reuse a valid, unexpired record only when its digest file also matches."""
    try:
        record = json.loads(VIP_RECORD.read_text(encoding="utf-8"))
        expires = datetime.fromisoformat(record["expires_at"].replace("Z", "+00:00"))
        digest_hex = DIGEST_FILE.read_text(encoding="ascii").strip()
        if not re.fullmatch(r"[0-9a-f]{128}", digest_hex):
            return None
        digest = bytes.fromhex(digest_hex)
        expected_address = address_from_digest(digest)
        parsed_address = ipaddress.IPv6Address(record["ipv6_address"])
        if (
            record.get("metadata_sha256") == metadata_sha256
            and expires > now
            and parsed_address == ipaddress.IPv6Address(expected_address)
            and record.get("hash_algorithm") == "SHA-512"
        ):
            return record
    except (FileNotFoundError, OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None
    return None


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

    VIP_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    DIGEST_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    for directory in (VIP_DIR, DIGEST_DIR):
        os.chown(directory, 0, 0)
        os.chmod(directory, 0o700)

    # Serialize boot/manual invocations so digest and vIP record cannot diverge.
    lock_fd = os.open(LOCK_FILE, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        os.fchown(lock_fd, 0, 0)
        os.fchmod(lock_fd, 0o600)
        fcntl.flock(lock_fd, fcntl.LOCK_EX)

        current = load_current_record(metadata_sha256, now)
        if current is not None:
            print(f"[nls-vip] Existing vIP remains valid: {current['ipv6_address']}")
            return 0

        created_at = now
        expires_at = created_at + timedelta(hours=ttl_hours)
        nonce = secrets.token_bytes(32)
        timestamp = iso_utc(created_at)

        # Domain-separated input: canonical CA metadata + UTC time + fresh nonce.
        payload = (
            DOMAIN
            + len(metadata_bytes).to_bytes(8, "big")
            + metadata_bytes
            + timestamp.encode("ascii")
            + b"\\x00"
            + nonce
        )
        digest = hashlib.sha512(payload).digest()
        digest_hex = digest.hex()
        ipv6_address = address_from_digest(digest)

        certificate = metadata.get("certificate")
        fingerprint = (
            certificate.get("sha256_fingerprint")
            if isinstance(certificate, dict)
            else None
        )
        trust = metadata.get("trust")
        trusted = (
            isinstance(trust, dict)
            and trust.get("trust_status") == "TRUSTED"
            and trust.get("enabled") is True
            and trust.get("certificate_chain_verified") is True
            and bool(fingerprint)
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
            "certificate_sha256_fingerprint": fingerprint,
            "created_at": timestamp,
            "expires_at": iso_utc(expires_at),
            "ttl_seconds": ttl_hours * 3600,
            "nonce_hex": nonce.hex(),
            "nonce_bytes": len(nonce),
            "trust_validation_required": True,
            "notes": (
                "Candidate vIP only. It is not proof of identity or authorization. "
                "Activate only after independent Router-CA certificate-chain, "
                "identity, policy, and revocation validation."
            ),
        }

        atomic_write(DIGEST_FILE, digest_hex + "\\n", 0o600)
        atomic_write(VIP_RECORD, json.dumps(record, indent=2) + "\\n", 0o600)
        for path in (DIGEST_FILE, VIP_RECORD):
            os.chown(path, 0, 0)
            os.chmod(path, 0o600)

        print(f"[nls-vip] Generated candidate vIP: {ipv6_address}")
        print(f"[nls-vip] SHA-512 digest: {DIGEST_FILE}")
        print(f"[nls-vip] vIP record: {VIP_RECORD}")
        print(f"[nls-vip] Expires: {record['expires_at']} (UTC)")
        print(f"[nls-vip] Trust state: {record['status']}")
        return 0
    finally:
        os.close(lock_fd)


if __name__ == "__main__":
    raise SystemExit(main())
