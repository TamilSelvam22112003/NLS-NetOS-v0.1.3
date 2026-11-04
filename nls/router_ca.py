"""Experimental Router-CA X.509 identity helpers.

This is a prototype trust-anchor implementation, not yet a production PKI:
root-key rotation, revocation distribution, hardware-backed storage and
operational ceremony are intentionally outside this module.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.x509.oid import NameOID, ObjectIdentifier

ROUTER_IDENTITY_OID = ObjectIdentifier("1.3.6.1.4.1.55555.1.1")
UTC = timezone.utc


def _write_private_key(path: Path, key: Ed25519PrivateKey) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    path.chmod(0o600)


def create_root_ca(directory: str | Path, common_name: str = "NLS Router Root CA") -> tuple[Path, Path]:
    """Create a self-signed Ed25519 root CA; protect its unencrypted key offline."""
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    key_path, cert_path = root / "root-ca.key", root / "root-ca.crt"
    if key_path.exists() or cert_path.exists():
        raise FileExistsError("CA material already exists; refusing to overwrite it")
    key = Ed25519PrivateKey.generate()
    now = datetime.now(UTC)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, content_commitment=False, key_encipherment=False,
                data_encipherment=False, key_agreement=False, key_cert_sign=True,
                crl_sign=True, encipher_only=None, decipher_only=None,
            ),
            critical=True,
        )
        .sign(key, algorithm=None)
    )
    _write_private_key(key_path, key)
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    cert_path.chmod(0o644)
    return key_path, cert_path


def issue_router_certificate(
    ca_key_path: str | Path,
    ca_cert_path: str | Path,
    router_id: str,
    output_directory: str | Path,
    validity_days: int = 365,
) -> tuple[Path, Path]:
    """Create a router Ed25519 signing key and CA-signed identity certificate."""
    if not router_id or len(router_id) > 128 or any(c.isspace() for c in router_id):
        raise ValueError("router_id must be 1-128 non-whitespace characters")
    if not 1 <= validity_days <= 825:
        raise ValueError("validity_days must be between 1 and 825")
    ca_key = serialization.load_pem_private_key(Path(ca_key_path).read_bytes(), password=None)
    ca_cert = x509.load_pem_x509_certificate(Path(ca_cert_path).read_bytes())
    if not isinstance(ca_key, Ed25519PrivateKey) or not isinstance(ca_cert.public_key(), Ed25519PublicKey):
        raise ValueError("Router-CA must use Ed25519")
    if ca_key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw) != ca_cert.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw):
        raise ValueError("CA private key does not match CA certificate")
    constraints = ca_cert.extensions.get_extension_for_class(x509.BasicConstraints).value
    if not constraints.ca:
        raise ValueError("issuer certificate is not a CA")
    router_key = Ed25519PrivateKey.generate()
    now = datetime.now(UTC)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, router_id)])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_cert.subject)
        .public_key(router_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=validity_days))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.SubjectAlternativeName([x509.UniformResourceIdentifier(f"urn:nls:router:{router_id}")]),
            critical=False,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, content_commitment=False, key_encipherment=False,
                data_encipherment=False, key_agreement=False, key_cert_sign=False,
                crl_sign=False, encipher_only=None, decipher_only=None,
            ),
            critical=True,
        )
        .add_extension(x509.UnrecognizedExtension(ROUTER_IDENTITY_OID, router_id.encode("utf-8")), critical=True)
        .sign(ca_key, algorithm=None)
    )
    out = Path(output_directory)
    out.mkdir(parents=True, exist_ok=True)
    key_path, cert_path = out / f"{router_id}.key", out / f"{router_id}.crt"
    if key_path.exists() or cert_path.exists():
        raise FileExistsError(f"identity files already exist for {router_id}")
    _write_private_key(key_path, router_key)
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    cert_path.chmod(0o644)
    return key_path, cert_path


def verify_router_certificate(
    certificate_path: str | Path,
    ca_certificate_path: str | Path,
    expected_router_id: str,
    now: datetime | None = None,
) -> bool:
    """Validate issuer signature, time, CA constraints and bound router identity."""
    cert = x509.load_pem_x509_certificate(Path(certificate_path).read_bytes())
    ca_cert = x509.load_pem_x509_certificate(Path(ca_certificate_path).read_bytes())
    ca_key = ca_cert.public_key()
    if not isinstance(ca_key, Ed25519PublicKey) or not isinstance(cert.public_key(), Ed25519PublicKey):
        return False
    if cert.issuer != ca_cert.subject:
        return False
    try:
        ca_key.verify(cert.signature, cert.tbs_certificate_bytes)
        constraints = ca_cert.extensions.get_extension_for_class(x509.BasicConstraints).value
        if not constraints.ca:
            return False
        cert.extensions.get_extension_for_oid(ROUTER_IDENTITY_OID)
        identity = cert.extensions.get_extension_for_oid(ROUTER_IDENTITY_OID).value.value.decode("utf-8")
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        uri = san.get_values_for_type(x509.UniformResourceIdentifier)
    except (ValueError, x509.ExtensionNotFound, UnicodeDecodeError):
        return False
    instant = now or datetime.now(UTC)
    before = cert.not_valid_before_utc if hasattr(cert, "not_valid_before_utc") else cert.not_valid_before.replace(tzinfo=UTC)
    after = cert.not_valid_after_utc if hasattr(cert, "not_valid_after_utc") else cert.not_valid_after.replace(tzinfo=UTC)
    return identity == expected_router_id and uri == [f"urn:nls:router:{expected_router_id}"] and before <= instant <= after
