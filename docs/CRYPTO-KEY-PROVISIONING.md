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
| Router-CA SHA-512 digest | `/var/lib/nls-netos/crypto/sha-512/r-ca-vip.key` | root:root, 0600 |
| Home CA virtual IPv6 record | `/var/lib/nls-netos/nls-router-ca/home-ca/home-ca-vip.json` | root:root, 0600 |

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
4. If `home-ca/root-ca.crt` exists, reads its X.509 certificate fields into the metadata file. If no certificate exists, certificate fields remain null and trust remains PENDING.
5. Invokes `generate-router-ca-vip.py`. It creates a time-bound SHA-512-derived candidate IPv6 identifier only when a parsed CA certificate and fingerprint are present. It reuses an unexpired identifier for an unchanged metadata snapshot.

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
- `/lib/systemd/system/nls-keygen.service`

Its post-installation script reloads systemd and enables the oneshot unit. The unit runs at boot after local filesystems are mounted and before `nls-router.service` if that service is installed. The initializer checks the status file each time it runs.

## Manual source-tree test

From the repository root:

```bash
sudo apt-get update
sudo apt-get install -y openssl python3-cryptography
sudo install -D -m 0700 scripts/generate-keys.sh /usr/lib/nls-netos/generate-keys.sh
sudo install -D -m 0700 scripts/nls-boot-init.sh /usr/lib/nls-netos/nls-boot-init.sh
sudo install -D -m 0644 lib/systemd/system/nls-keygen.service /lib/systemd/system/nls-keygen.service
sudo systemctl daemon-reload
sudo systemctl enable nls-keygen.service
```

Set `nls_service.service_enabled` to JSON boolean `true` in `/var/lib/nls-netos/system-status.json`, then reboot. Check the result with:

```bash
sudo systemctl status nls-keygen.service
sudo journalctl -u nls-keygen.service -b --no-pager
sudo find /var/lib/nls-netos -maxdepth 4 -type f -printf '%M %u:%g %p\\n'
```

## Cryptographic protocol note

The persistent AES key generated here is local machine material, not a fleet-wide traffic key. NLS data-plane traffic should use unique session keys derived through the protocol's authenticated key-establishment procedure and AES-256-GCM with correct nonce management. This provisioning script does not implement key exchange, certificate issuance, certificate trust validation, rotation, revocation, or hardware-backed key storage.
