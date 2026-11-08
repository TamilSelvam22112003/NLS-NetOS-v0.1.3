# Router-CA SHA-512 Virtual IPv6 Identifier

## Runtime paths

The implementation uses the established NLS-NetOS state root:

- CA metadata input: `/var/lib/nls-netos/nls-router-ca/home-ca/root-ca-metadata.json`
- SHA-512 digest: `/var/lib/nls-netos/crypto/sha-512/r-ca-vip.key`
- vIP record: `/var/lib/nls-netos/nls-router-ca/home-ca/home-ca-vip.json`
- Generator: `/usr/lib/nls-netos/generate-router-ca-vip.py`

The generator reads the Root CA metadata file. The example JSON supplied in the development request matches the existing `system-status.json` health-report schema; it is not treated as CA identity metadata.

The generated record is JSON data, so the runtime filename is `home-ca-vip.json`, not `home-ca-vip.py`. Python code belongs in the generator script.

## Derivation

1. Read and validate the CA metadata JSON object.
2. Canonicalize it using sorted keys and compact JSON separators. Exclude only the volatile `management.last_inspected` field so routine boot inspection does not rotate the vIP.
3. Add the generation timestamp in UTC (ISO-8601 with a trailing `Z`) and a fresh 256-bit nonce from the operating system CSPRNG.
4. Compute a domain-separated SHA-512 digest over the canonical metadata, UTC timestamp, and nonce.
5. Write the complete 512-bit digest as 128 lowercase hexadecimal characters to `r-ca-vip.key`.
6. Use the first 128 digest bits to derive an IPv6 address, constraining its high three bits to the NLS address-policy range `2000::/3`. The record stores the expanded eight-group IPv6 representation.
7. Store the creation time, expiry time, nonce, metadata fingerprint, address, and trust state in `home-ca-vip.json`.

The generator can create a **candidate** vIP from metadata before a CA certificate is present. When the certificate or trust state is not validated, the record remains `PENDING_TRUST`. It becomes `ACTIVE` only if the metadata explicitly records `trust_status: TRUSTED`, `enabled: true`, and `certificate_chain_verified: true`, and contains a certificate fingerprint. This generator does not itself validate those conditions.

## Lifetime and repeat behavior

The default lifetime is 24 hours. Set `NLS_CA_VIP_TTL_HOURS` to an integer from 1 through 168 to change it. The generator preserves the current vIP while its metadata snapshot is unchanged and the record remains unexpired. It generates a replacement when the metadata changes or the lifetime expires.

Timestamps are generated from the router's system clock in UTC. Production routers must have reliable time synchronization enabled; clock rollback can affect expiry decisions.

## Security properties and limitations

- `r-ca-vip.key` contains a SHA-512 digest, **not** a reusable cryptographic secret. The `.key` extension is retained for the requested path only. Do not use it as an AES key, signing key, or authentication credential.
- The vIP is a derived identifier, not proof of possession, identity, authorization, or global IPv6 address allocation.
- `2000::/3` is the NLS policy range already used by the project. A generated address is not automatically assigned or globally routed by an Internet registry. Check address uniqueness and deployment policy before using it on a live network.
- The candidate remains `PENDING_TRUST` until independent Router-CA certificate-chain, identity, policy, and revocation validation succeeds.
- Digest and vIP record files are root-owned with mode `0600`; containing directories are root-owned with mode `0700`.
- A filesystem lock serializes concurrent generator invocations, and files are replaced atomically.
- Runtime digest, nonce, and address are generated on the installed router; no machine-specific output is committed to Git.

## Boot integration

When `nls_service.service_enabled` is exactly JSON boolean `true`, the boot initializer updates Home CA metadata and invokes the vIP generator. If metadata does not exist, generation is skipped. Invalid metadata or unsafe write failures stop initialization rather than producing a partial record.
