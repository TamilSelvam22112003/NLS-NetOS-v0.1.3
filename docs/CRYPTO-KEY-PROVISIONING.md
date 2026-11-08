# NLS-NetOS cryptographic key provisioning

## Purpose

NLS-NetOS provisions per-machine cryptographic material and Router-CA metadata on the target Ubuntu/Debian system. Generated keys and machine-specific CA metadata are created on the target system; they are never committed to Git or included in a distributable package.

## Runtime storage

| Material | Runtime path | Permissions |
|---|---|---|
| AES-256 raw key (32 bytes) | `/var/lib/nls-netos/crypto/aes-256/aes256.key` | root:root, 0600 |
| RSA-2048 private key | `/var/lib/nls-netos/crypto/RSA-2048/private_key.pem` | root:root, 0600 |
| RSA-2048 public key | `/var/lib/nls-netos/crypto/RSA-2048/public_key.pem` | root:root, 0644 |
| Home CA metadata | `/var/lib/nls-netos/nls-router-ca/home-ca/home-ca-metadata.json` | root:root, 0600 |
| Home CA certificate (when provisioned) | `/var/lib/nls-netos/nls-router-ca/home-ca/root-ca.crt` | public certificate |
| ISP CA directory | `/var/lib/nls-netos/nls-router-ca/isp-ca/` | root-owned directory |
| Router-CA SHA-512 derivation digest | `/var/lib/nls-netos/crypto/sha-512/r-ca-vip.key` | root:root, 0600 |
| Generated Home CA VIP module | `/var/lib/nls-netos/nls-router-ca/home-ca/home-ca-vip.py` | root:root, 0600 |

Router-CA data is a sibling of `crypto/`, not a child of it:

```text
/var/lib/nls-netos/
├── crypto/
│   ├── aes-256/
│   │   └── aes256.key
│   └── RSA-2048/
│       ├── private_key.pem
│       └── public_key.pem
└── nls-router-ca/
    ├── home-ca/
    │   └── home-ca-metadata.json
    └── isp-ca/
```

The key-generation script validates existing keys and preserves them. It does not silently rotate identity material.

## Router-CA time-bucketed virtual IPv6 address

The canonical source is the runtime metadata file `home-ca-metadata.json` (the current implementation does not use a `root-ca-metadata.json` filename). The generator canonicalizes the complete JSON object and computes SHA-512 over a domain separator, the canonical metadata bytes, and the current UTC five-minute bucket. It does not randomly sample the digest: deterministic derivation is required so two systems with identical metadata and synchronized clocks can reproduce the same address. The first 120 digest-derived bits are placed in the RFC 4193 ULA `fd00::/8` space.

`r-ca-vip.key` contains the 512-bit hexadecimal SHA-512 derivation digest; despite the `.key` suffix, this is not a secret or an encryption/authentication key. The generated `home-ca-vip.py` module contains the IPv6 address, digest, metadata fingerprint, generation time, bucket start, and expiry. `management.last_inspected` is excluded from canonicalization because it is volatile inspection telemetry; other metadata fields participate. The five-minute address is a locator, not proof of identity or trust. Do not use it as an authentication credential. Cross-router derivation requires identical CA metadata and synchronized UTC clocks. This local Home-CA VIP is distinct from the NLS per-handshake/session vIP described by the protocol handshake specification; it does not replace that two-router, nonce-bound derivation. This implementation does not yet add the address to an interface or routing table.

## Boot-time activation gate

The enabled `nls-keygen.service` runs `/usr/lib/nls-netos/nls-boot-init.sh` during boot. The initializer reads:

`/var/lib/nls-netos/system-status.json`

It proceeds only when this exact JSON value is boolean true:

```json
{
  "nls_service": {
    "service_enabled": true
  }
}
```

If the status file is missing, invalid, or the value is false/null, initialization is skipped. When enabled, the initializer:

1. Runs the existing per-machine AES-256 and RSA-2048 generation/validation script under `/var/lib/nls-netos/crypto/`.
2. Creates `/var/lib/nls-netos/nls-router-ca/home-ca/` and `/var/lib/nls-netos/nls-router-ca/isp-ca/`.
3. Creates `home-ca-metadata.json` if absent.
4. If `home-ca/root-ca.crt` exists, reads its X.509 certificate fields into the metadata file. If no certificate exists, certificate fields remain null and trust remains PENDING.\n5. Derives the time-bucketed Home-CA VIP, writes the SHA-512 digest and generated Python state module, and refreshes it periodically through `nls-vip-refresh.timer`.

The metadata inspector does not download certificates, contact a CA endpoint, or mark a certificate trusted. Certificate presence and parsing alone do not establish trust; chain, identity, policy, and revocation validation are separate operations.

## OpenSSL prerequisite

The Debian package declares `openssl` as a runtime dependency. For a manual source checkout on Ubuntu, install it before running the key-generation script:

```bash
sudo apt-get update
sudo apt-get install -y openssl python3-cryptography
```

## Package installation and boot activation

The package installs:

- `/usr/lib/nls-netos/generate-keys.sh`
- `/usr/lib/nls-netos/nls-boot-init.sh`
- `/usr/lib/nls-netos/derive-router-ca-vip.py`
- `/lib/systemd/system/nls-keygen.service`
- `/lib/systemd/system/nls-vip-refresh.service`
- `/lib/systemd/system/nls-vip-refresh.timer`

Its post-installation script reloads systemd and enables the oneshot unit. The unit runs at boot after local filesystems are mounted and before `nls-router.service` if that service is installed. The initializer checks the status file each time it runs.

## Manual source-tree test

From the repository root:

```bash
sudo apt-get update
sudo apt-get install -y openssl python3-cryptography
sudo install -D -m 0700 scripts/generate-keys.sh /usr/lib/nls-netos/generate-keys.sh
sudo install -D -m 0700 scripts/nls-boot-init.sh /usr/lib/nls-netos/nls-boot-init.sh
sudo install -D -m 0700 scripts/derive-router-ca-vip.py /usr/lib/nls-netos/derive-router-ca-vip.py
sudo install -D -m 0644 lib/systemd/system/nls-keygen.service /lib/systemd/system/nls-keygen.service
sudo install -D -m 0644 lib/systemd/system/nls-vip-refresh.service /lib/systemd/system/nls-vip-refresh.service
sudo install -D -m 0644 lib/systemd/system/nls-vip-refresh.timer /lib/systemd/system/nls-vip-refresh.timer
sudo systemctl daemon-reload
sudo systemctl enable nls-keygen.service
sudo systemctl enable --now nls-vip-refresh.timer
```

Set `nls_service.service_enabled` to JSON boolean `true` in `/var/lib/nls-netos/system-status.json`, then reboot. Check the result with:

```bash
sudo systemctl status nls-keygen.service nls-vip-refresh.timer
sudo systemctl status nls-vip-refresh.service
sudo journalctl -u nls-keygen.service -u nls-vip-refresh.service -b --no-pager
sudo find /var/lib/nls-netos -maxdepth 4 -type f -printf '%M %u:%g %p\\n'
```

## Cryptographic protocol note

The persistent AES key generated here is local machine material, not a fleet-wide traffic key. NLS data-plane traffic should use unique session keys derived through the protocol's authenticated key-establishment procedure and AES-256-GCM with correct nonce management. This provisioning script does not implement key exchange, certificate issuance, certificate trust validation, rotation, revocation, or hardware-backed key storage.
