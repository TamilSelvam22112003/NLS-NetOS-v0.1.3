#!/usr/bin/env python3
"""Derive a time-bucketed Home Router-CA virtual IPv6 identifier.

The SHA-512 output is a public derivation value, NOT a cryptographic secret,
traffic key, certificate, or proof of peer authentication.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

DEFAULT_METADATA = Path("/var/lib/nls-netos/nls-router-ca/home-ca/home-ca-metadata.json")
DEFAULT_DIGEST = Path("/var/lib/nls-netos/crypto/sha-512/r-ca-vip.key")
DEFAULT_RECORD = Path("/var/lib/nls-netos/nls-router-ca/home-ca/home-ca-vip.json")
BUCKET_SECONDS = 300
DOMAIN = b"NLS-NETOS:ROUTER-CA:HOME-VIP:v1\x00"


def parse_utc(value: str | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("--now must include a timezone (for example, 2026-11-08T15:20:00Z)")
    return parsed.astimezone(timezone.utc)


def stable_metadata(metadata: dict[str, Any]) -> bytes:
    """Canonicalize CA metadata while excluding volatile inspection time."""
    if metadata.get("schema_version") != 1:
        raise ValueError("unsupported or missing CA metadata schema_version")
    canonical = dict(metadata)
    management = canonical.get("management")
    if isinstance(management, dict):
        management = dict(management)
        management.pop("last_inspected", None)
        canonical["management"] = management
    return json.dumps(
        canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def derive(metadata: dict[str, Any], now: datetime) -> tuple[str, str, int, datetime, datetime]:
    canonical = stable_metadata(metadata)
    epoch = int(now.timestamp())
    bucket_id = epoch // BUCKET_SECONDS
    bucket_start_epoch = bucket_id * BUCKET_SECONDS
    bucket_start = datetime.fromtimestamp(bucket_start_epoch, timezone.utc)
    expires_at = bucket_start + timedelta(seconds=BUCKET_SECONDS)

    # Length-prefixing and domain separation prevent ambiguous concatenation
    # and cross-protocol reuse of the same hash input.
    bucket_bytes = bucket_id.to_bytes(8, "big", signed=False)
    digest = hashlib.sha512(
        DOMAIN + len(canonical).to_bytes(8, "big") + canonical + bucket_bytes
    ).hexdigest()

    # Use the RFC 4193 locally assigned ULA prefix (fd/8), then 120 derived
    # bits. This yields a syntactically valid ULA, not a globally routable IP.
    address_hex = "fd" + digest[:30]
    address = ipaddress.IPv6Address(int(address_hex, 16))
    return digest, address.exploded, bucket_id, bucket_start, expires_at


def atomic_write(path: Path, content: str, mode: int = 0o600) -> None:
    parent_existed = path.parent.exists()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not parent_existed:
        os.chmod(path.parent, 0o700)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
        os.chmod(path, mode)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, default=DEFAULT_METADATA)
    parser.add_argument("--digest-output", type=Path, default=DEFAULT_DIGEST)
    parser.add_argument("--record-output", type=Path, default=DEFAULT_RECORD)
    parser.add_argument("--now", help="UTC-aware ISO-8601 time; intended for deterministic tests")
    args = parser.parse_args()

    try:
        if os.geteuid() != 0 and (
            args.digest_output == DEFAULT_DIGEST or args.record_output == DEFAULT_RECORD
        ):
            raise PermissionError("run as root when writing to the system runtime directories")

        with args.metadata.open("r", encoding="utf-8") as stream:
            metadata = json.load(stream)
        if not isinstance(metadata, dict):
            raise ValueError("CA metadata root must be a JSON object")

        now = parse_utc(args.now)
        digest, vip, bucket_id, bucket_start, expires_at = derive(metadata, now)
        metadata_bytes = stable_metadata(metadata)
        record = {
            "schema_version": 1,
            "identifier_type": "home-router-ca-virtual-ipv6",
            "vip": vip,
            "address_scope": "unique-local (RFC 4193); not globally routable",
            "derivation": {
                "algorithm": "SHA-512",
                "domain": "NLS-NETOS:ROUTER-CA:HOME-VIP:v1",
                "input": "canonical home-ca-metadata.json excluding management.last_inspected",
                "time_bucket_seconds": BUCKET_SECONDS,
                "time_bucket_id": bucket_id,
                "time_bucket_started_at": bucket_start.isoformat().replace("+00:00", "Z"),
                "derived_bits": 120,
                "ula_prefix": "fd00::/8"
            },
            "metadata_sha256": hashlib.sha256(metadata_bytes).hexdigest(),
            "created_at": now.isoformat().replace("+00:00", "Z"),
            "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
            "trust_status_at_generation": metadata.get("trust", {}).get("trust_status")
            if isinstance(metadata.get("trust"), dict) else None,
            "authentication_established": False,
            "note": "Identifier only; does not authenticate a router or establish CA trust."
        }

        atomic_write(args.digest_output, digest + "\n")
        atomic_write(args.record_output, json.dumps(record, indent=2) + "\n")
        print(f"[home-ca-vip] VIP: {vip}")
        print(f"[home-ca-vip] Digest: {args.digest_output}")
        print(f"[home-ca-vip] Record: {args.record_output}")
        print(f"[home-ca-vip] Expires: {record['expires_at']}")
        return 0
    except (OSError, json.JSONDecodeError, ValueError, PermissionError) as exc:
        print(f"[home-ca-vip] ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
