# NLS protocol primitives (experimental)

This package is an initial, independently testable cryptographic foundation. It is **not** a complete NLS protocol implementation and must not be deployed on production networks.

Implemented: X25519 ephemeral key agreement; HKDF-SHA-256 derivation with caller-supplied salt and protocol context; AES-256-GCM with 96-bit random nonces and associated data; thread-safe bounded sliding-window replay rejection.

Not implemented: Router-CA certificate issuance, chain validation, revocation, or peer authorization; NLS M1-M4 handshake; vIP derivation/verification; key rotation and crash-safe nonce persistence; packet wire format; Linux TUN/netlink integration; routing-manager adapter; daemon lifecycle; or OSPFv3 integration.

Before production use, define and review a versioned wire protocol, domain-separated directional keys, nonce uniqueness across restarts, authenticated handshake transcript, certificate policy, resource limits, and interoperability tests. This API does not invent those missing protocol rules.

Run `python3 -m pytest -q tests/unit` after installing `cryptography` and `pytest`.
