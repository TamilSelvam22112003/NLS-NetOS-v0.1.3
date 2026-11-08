# NLS-NetOS Runtime State Directory

This directory represents the runtime state location used by an installed NLS-NetOS system:

`/var/lib/nls-netos/`

The health-monitoring service will create and update `system-status.json` here with the router's current component and overall health status.

`system-status.json` is generated on each router; it is intentionally not committed to Git because its contents are machine-specific and change at runtime.

Do not store private keys, AES keys, passwords, or other secret material in this directory's status report. Cryptographic key material belongs in the existing restricted crypto storage path under `/var/lib/nls-netos/crypto/`.

## Router-CA VIP runtime artifacts

The boot initializer creates the time-bucketed Home Router-CA VIP artifacts only on the target system:
- SHA-512 digest: `/var/lib/nls-netos/crypto/sha-512/r-ca-vip.key`
- VIP lifecycle record: `/var/lib/nls-netos/nls-router-ca/home-ca/home-ca-vip.json`

These files are machine/runtime-specific and must not be committed to Git. The digest is a public-data-derived identifier, not a secret cryptographic key. See `docs/CRYPTO-KEY-PROVISIONING.md` for derivation, expiry, and trust limitations.
