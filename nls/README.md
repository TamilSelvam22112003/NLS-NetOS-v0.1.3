# NLS protocol primitives (experimental)

This package is an initial, independently testable foundation. It is **not** a
complete NLS protocol implementation and must not be deployed on production
networks.

Implemented:
- X25519 ephemeral key agreement and HKDF-SHA-256 derivation with caller-supplied
  salt and protocol context.
- AES-256-GCM with 96-bit nonces and associated data.
- Thread-safe bounded sliding-window replay rejection.
- Experimental Ed25519 Router-CA root creation, router identity certificate
  issuance, and pinned-root certificate verification.

Router-CA limitations: the root private key is written unencrypted with mode
0600 and must be protected offline; there is no revocation/CRL or OCSP,
certificate distribution, rotation ceremony, hardware-backed key storage,
peer authorization policy, or integration with the NLS handshake. Treat this
as a lab-only prototype.

Not implemented: NLS M1-M4 handshake; vIP derivation/verification; key rotation
and crash-safe nonce persistence; packet wire format; Linux TUN/netlink
integration; routing-manager adapter; daemon lifecycle; or end-to-end OSPFv3
integration.

Before production use, define and review a versioned wire protocol,
domain-separated directional keys, nonce uniqueness across restarts,
authenticated handshake transcript, certificate policy, resource limits, and
interoperability tests. This API does not invent those missing protocol rules.

Run `python3 -m pytest -q tests/unit` after installing `cryptography` and
`pytest`.
