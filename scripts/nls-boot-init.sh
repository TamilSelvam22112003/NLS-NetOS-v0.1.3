#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

readonly STATUS_FILE="/var/lib/nls-netos/system-status.json"
readonly DATA_ROOT="/var/lib/nls-netos"
readonly CRYPTO_ROOT="${DATA_ROOT}/crypto"
readonly CA_ROOT="${DATA_ROOT}/nls-router-ca"
readonly HOME_CA_DIR="${CA_ROOT}/home-ca"
readonly ISP_CA_DIR="${CA_ROOT}/isp-ca"
readonly HOME_CA_CERT="${HOME_CA_DIR}/root-ca.crt"
readonly HOME_CA_METADATA="${HOME_CA_DIR}/root-ca-metadata.json"
readonly LEGACY_HOME_CA_METADATA="${HOME_CA_DIR}/home-ca-metadata.json"
readonly KEYGEN="/usr/lib/nls-netos/generate-keys.sh"

log() { printf '[nls-boot-init] %s\n' "$*"; }
die() { log "ERROR: $*" >&2; exit 1; }

[[ ${EUID} -eq 0 ]] || die "must run as root"
command -v python3 >/dev/null 2>&1 || die "python3 is required"

# Proceed only when system-status.json explicitly enables NLS.
if [[ ! -f "$STATUS_FILE" ]]; then
    log "Status file not found; NLS initialization skipped"
    exit 0
fi

if ! python3 - "$STATUS_FILE" <<'PY'
import json
import sys

try:
    with open(sys.argv[1], "r", encoding="utf-8") as stream:
        status = json.load(stream)
except (OSError, json.JSONDecodeError):
    sys.exit(2)

if not isinstance(status, dict):
    sys.exit(2)
service = status.get("nls_service")
if not isinstance(service, dict):
    sys.exit(1)
sys.exit(0 if service.get("service_enabled") is True else 1)
PY
then
    log "NLS is not explicitly enabled in system-status.json; initialization skipped"
    exit 0
fi

[[ -x "$KEYGEN" ]] || die "key-generation script not installed: $KEYGEN"

# Generate or validate the existing per-machine AES-256 and RSA-2048 keys.
"$KEYGEN"

# CA data is a sibling of crypto/, not a child of crypto/.
install -d -o root -g root -m 0700 "$CA_ROOT" "$HOME_CA_DIR" "$ISP_CA_DIR"

# Create Home CA metadata once; on later boots refresh certificate-derived fields.
python3 - "$HOME_CA_CERT" "$HOME_CA_METADATA" "$LEGACY_HOME_CA_METADATA" <<'PY'
import json
import os
import sys
from datetime import datetime, timezone

cert_path, metadata_path, legacy_metadata_path = sys.argv[1:4]
now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

try:
    with open(metadata_path, "r", encoding="utf-8") as stream:
        metadata = json.load(stream)
    if not isinstance(metadata, dict):
        raise ValueError("metadata root must be a JSON object")
except FileNotFoundError:
    # Migrate the former filename without discarding existing CA metadata.
    if os.path.isfile(legacy_metadata_path):
        try:
            with open(legacy_metadata_path, "r", encoding="utf-8") as stream:
                metadata = json.load(stream)
            if not isinstance(metadata, dict):
                raise ValueError("legacy metadata root must be a JSON object")
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise SystemExit(f"Cannot safely migrate legacy Home CA metadata: {exc}")
    else:
        metadata = {
        "schema_version": 1,
        "ca_id": "HOME-CA-001",
        "ca_type": "HOME",
        "ca_name": "Home Router CA",
        "network": {"ca_url": None, "ca_ipv6_address": None},
        "certificate": {},
        "certificate_files": {
            "root_certificate": "root-ca.crt",
            "certificate_format": "PEM",
            "storage_directory": os.path.dirname(metadata_path) + "/"
        },
        "trust": {
            "trust_status": "PENDING",
            "enabled": False,
            "signature_verified": False,
            "certificate_chain_verified": False,
            "revocation_checked": False,
            "identity_verified": False
        },
        "management": {"added_by": "NLS-NetOS boot initialization"}
        }
except (OSError, json.JSONDecodeError, ValueError) as exc:
    raise SystemExit(f"Cannot safely read existing Home CA metadata: {exc}")

certificate = {
    "present": False,
    "format": "X.509 PEM",
    "version": None,
    "serial_number": None,
    "subject": None,
    "issuer": None,
    "public_key_algorithm": None,
    "public_key_size": None,
    "signature_algorithm": None,
    "valid_from": None,
    "valid_until": None,
    "basic_constraints_ca": None,
    "key_usage": None,
    "subject_key_identifier": None,
    "authority_key_identifier": None,
    "sha256_fingerprint": None
}

if os.path.isfile(cert_path):
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import rsa, ec, ed25519, ed448
        from cryptography.x509.oid import NameOID

        with open(cert_path, "rb") as stream:
            cert = x509.load_pem_x509_certificate(stream.read())

        def name_value(name, oid):
            values = name.get_attributes_for_oid(oid)
            return values[0].value if values else None

        public_key = cert.public_key()
        if isinstance(public_key, rsa.RSAPublicKey):
            key_algorithm, key_size = "RSA", public_key.key_size
        elif isinstance(public_key, ec.EllipticCurvePublicKey):
            key_algorithm, key_size = "EC", public_key.key_size
        elif isinstance(public_key, ed25519.Ed25519PublicKey):
            key_algorithm, key_size = "Ed25519", 256
        elif isinstance(public_key, ed448.Ed448PublicKey):
            key_algorithm, key_size = "Ed448", 448
        else:
            key_algorithm, key_size = type(public_key).__name__, None

        def iso_utc(value):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

        subject = {
            "common_name": name_value(cert.subject, NameOID.COMMON_NAME),
            "organization": name_value(cert.subject, NameOID.ORGANIZATION_NAME),
            "organizational_unit": name_value(cert.subject, NameOID.ORGANIZATIONAL_UNIT_NAME),
            "country": name_value(cert.subject, NameOID.COUNTRY_NAME)
        }
        issuer = {
            "common_name": name_value(cert.issuer, NameOID.COMMON_NAME),
            "organization": name_value(cert.issuer, NameOID.ORGANIZATION_NAME),
            "organizational_unit": name_value(cert.issuer, NameOID.ORGANIZATIONAL_UNIT_NAME),
            "country": name_value(cert.issuer, NameOID.COUNTRY_NAME),
            "self_signed": cert.subject == cert.issuer
        }

        try:
            basic = cert.extensions.get_extension_for_class(x509.BasicConstraints).value
            is_ca, path_length = basic.ca, basic.path_length
        except x509.ExtensionNotFound:
            is_ca, path_length = None, None

        try:
            usage = cert.extensions.get_extension_for_class(x509.KeyUsage).value
            key_usage = {
                "digital_signature": usage.digital_signature,
                "key_encipherment": usage.key_encipherment,
                "key_cert_sign": usage.key_cert_sign,
                "crl_sign": usage.crl_sign
            }
        except x509.ExtensionNotFound:
            key_usage = None

        try:
            ski = cert.extensions.get_extension_for_class(x509.SubjectKeyIdentifier).value.digest.hex(":").upper()
        except x509.ExtensionNotFound:
            ski = None
        try:
            aki = cert.extensions.get_extension_for_class(x509.AuthorityKeyIdentifier).value.key_identifier
            aki = aki.hex(":").upper() if aki else None
        except x509.ExtensionNotFound:
            aki = None

        try:
            signature_name = cert.signature_algorithm_oid._name
        except AttributeError:
            signature_name = cert.signature_algorithm_oid.dotted_string

        certificate.update({
            "present": True,
            "version": "v3" if cert.version == x509.Version.v3 else str(cert.version),
            "serial_number": format(cert.serial_number, "X"),
            "subject": subject,
            "issuer": issuer,
            "public_key_algorithm": key_algorithm,
            "public_key_size": key_size,
            "signature_algorithm": signature_name,
            "valid_from": iso_utc(getattr(cert, "not_valid_before_utc", cert.not_valid_before)),
            "valid_until": iso_utc(getattr(cert, "not_valid_after_utc", cert.not_valid_after)),
            "basic_constraints_ca": {"ca": is_ca, "path_length": path_length},
            "key_usage": key_usage,
            "subject_key_identifier": ski,
            "authority_key_identifier": aki,
            "sha256_fingerprint": cert.fingerprint(hashes.SHA256()).hex(":").upper()
        })
    except Exception as exc:
        raise SystemExit(f"Home CA certificate exists but could not be parsed: {exc}")

metadata["certificate"] = certificate
metadata.setdefault("certificate_files", {}).update({
    "root_certificate": "root-ca.crt",
    "certificate_format": "PEM",
    "storage_directory": os.path.dirname(metadata_path) + "/"
})
metadata.setdefault("management", {})["last_inspected"] = now

trust = metadata.setdefault("trust", {})
if not certificate["present"]:
    trust["trust_status"] = "PENDING"
    trust["enabled"] = False
else:
    # Parsing a certificate does not establish trust.
    trust.setdefault("trust_status", "PENDING")
    trust.setdefault("enabled", False)

temporary_path = metadata_path + ".tmp"
with open(temporary_path, "w", encoding="utf-8") as stream:
    json.dump(metadata, stream, indent=2)
    stream.write("\n")
os.chmod(temporary_path, 0o600)
os.replace(temporary_path, metadata_path)
PY

chown root:root "$HOME_CA_METADATA"
chmod 0600 "$HOME_CA_METADATA"

# Generate or preserve the time-bound Home Router-CA virtual IPv6 identifier.
VIP_GENERATOR="/usr/lib/nls-netos/generate-router-ca-vip.py"
[[ -x "$VIP_GENERATOR" ]] || die "Router-CA vIP generator not installed: $VIP_GENERATOR"
"$VIP_GENERATOR"

log "NLS boot initialization completed"
log "Crypto directory: $CRYPTO_ROOT"
log "Router CA directory: $CA_ROOT"
log "Home CA metadata: $HOME_CA_METADATA"
log "ISP CA directory: $ISP_CA_DIR"
