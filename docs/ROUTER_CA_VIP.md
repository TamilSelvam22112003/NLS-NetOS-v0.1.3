# Router-CA SHA-512 Virtual IPv6 Identifier

## Runtime paths

The implementation follows the existing NLS-NetOS state root:

- CA input metadata: `/var/lib/nls-netos/nls-router-ca/home-ca/home-ca-metadata.json`
- SHA-512 digest: `/var/lib/nls-netos/crypto/sha-512/r-ca-vip.key`
- Generated vIP record: `/var/lib/nls-netos/nls-router-ca/home-ca/home-ca-vip.json`
- Generator: `/usr/lib/nls-netos/generate-router-ca-vip.py`

The current repository calls the CA metadata file `home-ca-metadata.json`; it does not currently use a `root-ca-metadata.json` filename. The generator consumes that existing metadata file rather than introducing a second competing metadata source. `home-ca-vip.py` is intentionally not used as a data filename: generated state is JSON, while executable logic belongs in the generator script.

## Derivation

1. Read and validate the Home CA metadata JSON.
2. Require a parsed CA certificate and its SHA-256 certificate fingerprint. If no CA certificate exists yet, skip vIP generation without failing boot.
3. Canonicalize the metadata (sorted JSON keys and compact separators). The volatile `management.last_inspected` field is excluded so routine boot-time inspection does not rotate the address.
4. Add an ISO-8601 UTC generation timestamp and a fresh 256-bit cryptographic nonce.
5. Compute a domain-separated SHA-512 digest over the canonical metadata, timestamp, and nonce.
6. Store the 512-bit digest as 128 hexadecimal characters in `r-ca-vip.key`.
7. Derive the address from the first 128 digest bits and constrain the top three bits to the NLS global-unicast policy range `2000::/3`. Store the expanded eight-group IPv6 form in `home-ca-vip.json`.

The nonce and timestamp are recorded so the derivation inputs can be audited. A new address is generated when the metadata snapshot changes or the current record expires. The default lifetime is 24 hours; set `NLS_CA_VIP_TTL_HOURS` to an integer from 1 to 168 to change it.

## Security properties and limitations

- `r-ca-vip.key` is a SHA-512 digest, **not** a cryptographic secret key. The `.key` filename is retained to match the requested path, but it must not be used as an AES key, signing key, or authentication credential.
- A hash-derived IPv6 address is an identifier, not proof of possession or identity. Router-CA authentication must independently verify certificates, signatures, and trust.
- The record is marked `PENDING_TRUST` unless the CA metadata explicitly reports `trust_status: TRUSTED`, `enabled: true`, and `certificate_chain_verified: true`. Generation does not itself establish trust.
- Both generated files are root-owned with mode `0600`; the containing directories are root-owned with mode `0700`.
- Runtime digest and vIP state are generated on the installed Ubuntu system. No per-machine digest, nonce, or address is committed to Git.

## Boot integration

After the boot initializer has updated Home CA metadata, it invokes the generator. Missing certificates cause a logged skip. Malformed metadata or unsafe generation failures cause boot initialization to fail closed rather than writing a partial record.
