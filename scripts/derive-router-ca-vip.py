#!/usr/bin/env python3
"""Derive a time-bucketed Home Router-CA IPv6 VIP from CA metadata.

The SHA-512 output is a public derivation digest, not a private cryptographic key.
Runtime artifacts are written atomically and are never stored in the Git repository.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import stat
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

DATA_ROOT = Path("/var/lib/nls-netos")
STATUS_FILE = DATA_ROOT / "system-status.json"
METADATA_FILE = DATA_ROOT / "nls-router-ca/home-ca/home-ca-metadata.json"
DIGEST_FILE = DATA_ROOT / "crypto/sha-512/r-ca-vip.key"
VIP_MODULE_FILE = DATA_ROOT / "nls-router-ca/home-ca/home-ca-vip.py"
TIME_BUCKET_SECONDS = 300
DOMAIN_SEPARATOR = b"NLS-NetOS|Router-CA-vIP|v1\x00"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def bucket_start(now: datetime) -> datetime:
    if now.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    epoch = int(now.astimezone(timezone.utc).timestamp())
    return datetime.fromtimestamp(
        epoch - (epoch % TIME_BUCKET_SECONDS), tz=timezone.utc
    )


def iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def canonical_metadata(metadata: dict[str, Any]) -> bytes:
    """Canonicalize metadata, excluding the volatile inspection timestamp.

    management.last_inspected is operational telemetry, not CA identity. Excluding
    it prevents a boot-time inspection from changing the VIP within the same bucket.
    All other metadata fields participate in the derivation.
    """
    stable = json.loads(json.dumps(metadata))
    management = stable.get("management")
    if isinstance(management, dict):
        management.pop("last_inspected", None)
    return json.dumps(
        stable, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def derive_vip(metadata: dict[str, Any], now: datetime) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        raise ValueError("Home CA metadata root must be a JSON object")

    start = bucket_start(now)
    expiry = start + timedelta(seconds=TIME_BUCKET_SECONDS)
    canonical = canonical_metadata(metadata)
    metadata_sha256 = hashlib.sha256(canonical).hexdigest()
    bucket_text = iso_z(start).encode("ascii")

    digest = hashlib.sha512(
        DOMAIN_SEPARATOR + canonical + b"\nUTC_BUCKET=" + bucket_text
    ).digest()

    # Use 120 digest-derived bits in RFC 4193 Unique Local Address space (fd00::/8).
    # The remaining 8 bits are fixed to the ULA prefix; do not randomly sample bits.
    address_bytes = b"\xfd" + digest[1:16]
    address = str(ipaddress.IPv6Address(address_bytes))

    return {
        "schema_version": 1,
        "vip_ipv6_address": address,
        "hash_algorithm": "SHA-512",
        "derivation_domain": "NLS-NetOS|Router-CA-vIP|v1",
        "time_bucket_seconds": TIME_BUCKET_SECONDS,
        "valid_from_utc": iso_z(start),
        "expires_at_utc": iso_z(expiry),
        "generated_at_utc": iso_z(now),
        "source_metadata_sha256": metadata_sha256,
        "sha512_digest_hex": digest.hex(),
    }


def atomic_write(path: Path, content: bytes, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    if path.is_symlink():
        raise OSError(f"refusing to replace symlink: {path}")
    if path.exists() and not stat.S_ISREG(path.stat().st_mode):
        raise OSError(f"refusing to replace non-regular file: {path}")

    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        os.chmod(path, mode)
    except Exception:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


def nls_is_enabled() -> bool:
    try:
        with STATUS_FILE.open("r", encoding="utf-8") as stream:
            status = json.load(stream)
    except FileNotFoundError:
        return False
    if not isinstance(status, dict):
        return False
    service = status.get("nls_service")
    return isinstance(service, dict) and service.get("service_enabled") is True


def render_python_module(result: dict[str, Any]) -> bytes:
    fields = (
        "schema_version",
        "vip_ipv6_address",
        "hash_algorithm",
        "derivation_domain",
        "time_bucket_seconds",
        "valid_from_utc",
        "expires_at_utc",
        "generated_at_utc",
        "source_metadata_sha256",
        "sha512_digest_hex",
    )
    lines = [
        '"""Generated Home Router-CA VIP state. Do not edit by hand."""',
        "",
    ]
    for field in fields:
        lines.append(f"{field.upper()} = {json.dumps(result[field])}")
    lines.append("")
    return ("\n".join(lines)).encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-disabled",
        action="store_true",
        help="permit a manual derivation when NLS is disabled (testing only)",
    )
    args = parser.parse_args()

    if os.geteuid() != 0:
        print("ERROR: must run as root", file=sys.stderr)
        return 1
    if not args.allow_disabled and not nls_is_enabled():
        print("NLS is not explicitly enabled; Router-CA VIP derivation skipped")
        return 0
    if METADATA_FILE.is_symlink() or not METADATA_FILE.is_file():
        print(f"ERROR: Home CA metadata missing or unsafe: {METADATA_FILE}", file=sys.stderr)
        return 1

    try:
        with METADATA_FILE.open("r", encoding="utf-8") as stream:
            metadata = json.load(stream)
        result = derive_vip(metadata, utc_now())
        atomic_write(DIGEST_FILE, (result["sha512_digest_hex"] + "\n").encode("ascii"))
        atomic_write(VIP_MODULE_FILE, render_python_module(result))
        os.chown(DIGEST_FILE, 0, 0)
        os.chown(VIP_MODULE_FILE, 0, 0)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: Router-CA VIP derivation failed: {exc}", file=sys.stderr)
        return 1

    print(
        "Router-CA VIP refreshed: "
        f"{result['vip_ipv6_address']} "
        f"(valid until {result['expires_at_utc']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
