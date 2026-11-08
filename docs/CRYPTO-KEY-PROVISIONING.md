# NLS-NetOS cryptographic key provisioning

## Purpose

NLS-NetOS provisions per-machine cryptographic material and Router-CA metadata on the target Ubuntu/Debian system. Generated keys, digest material, nonces, and machine-specific vIP records are created on the target system; they are never committed to Git or included in a distributable package.

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
│   ├── RSA-2048/
│   │   ├── private_key.pem
│   │   └── public_key.pem
│   └── sha-512/
│       └── r-ca-vip.key
└── nls-router-ca/
    ├── home-ca/
    │   ├── home-ca-metadata.json
    │   └── home-ca-vip.json
    └── isp-ca/
```

The key-generation script validates existing AES/RSA keys and preserves them. It does not silently rotate identity material.

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

1. Runs the per-machine AES-256 and RSA-2048 generation/validation script under `/var/lib/nls-netos/crypto/`.
2. Creates the Home CA and ISP CA runtime directories.
3. Creates `home-ca-metadata.json` if absent.
4. If `home-ca/root-ca.crt` exists, reads its X.509 certificate fields into the metadata file. If no certificate exists, certificate fields remain null and trust remains PENDING.
5. Runs `generate-router-ca-vip.py` to derive a time-bound candidate IPv6 identifier from canonical CA metadata, a UTC timestamp, and a fresh 256-bit nonce. The candidate is marked `PENDING_TRUST` until trust is independently validated.

The current repository uses `home-ca-metadata.json` as its Home/Root CA metadata source. The example JSON in the development request matches `system-status.json`; that health report is not used as CA identity input. The generated vIP data is stored as JSON in `home-ca-vip.json`, not in a `.py` file.

The metadata inspector does not download certificates, contact a CA endpoint, or mark a certificate trusted. Certificate presence and parsing alone do not establish trust; chain, identity, policy, and revocation validation are separate operations.

## Router-CA vIP details

The generator writes a 512-bit SHA-512 digest as 128 hexadecimal characters to `crypto/sha-512/r-ca-vip.key`. It derives the candidate IPv6 address from the first 128 digest bits, constrained to the project's `2000::/3` policy range. The vIP record includes UTC `created_at` and `expires_at` timestamps, a 24-hour default lifetime, the nonce, metadata fingerprint, and trust state. Configure `NLS_CA_VIP_TTL_HOURS` to an integer from 1 to 168 to change the lifetime.

The digest file is an identifier derivation output, **not** a secret key and not an authentication credential. A generated address is not proof of router identity or an Internet registry allocation. Review `docs/ROUTER_CA_VIP.md` before using the candidate address in a live network.

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
- `/usr/lib/nls-netos/generate-router-ca-vip.py`
- `/lib/systemd/system/nls-keygen.service`

Its post-installation script reloads systemd and enables the oneshot unit. The unit runs at boot after local filesystems are mounted and before `nls-router.service` if that service is installed. The initializer checks the status file each time it runs.

## Manual source-tree test

From the repository root:

```bash
sudo apt-get update
sudo apt-get install -y openssl python3-cryptography
sudo install -D -m 0700 scripts/generate-keys.sh /usr/lib/nls-netos/generate-keys.sh
sudo install -D -m 0700 scripts/nls-boot-init.sh /usr/lib/nls-netos/nls-boot-init.sh
sudo install -D -m 0700 scripts/generate-router-ca-vip.py /usr/lib/nls-netos/generate-router-ca-vip.py
sudo install -D -m 0644 lib/systemd/system/nls-keygen.service /lib/systemd/system/nls-keygen.service
sudo systemctl daemon-reload
sudo systemctl enable nls-keygen.service
```

Set `nls_service.service_enabled` to JSON boolean `true` in `/var/lib/nls-netos/system-status.json`, then reboot. Check the result with:

```bash
sudo systemctl status nls-keygen.service
sudo journalctl -u nls-keygen.service -b --no-pager
sudo find /var/lib/nls-netos -maxdepth 5 -type f -printf '%M %u:%g %p\\n'
```

## Cryptographic protocol note

The persistent AES key generated here is local machine material, not a fleet-wide traffic key. NLS data-plane traffic should use unique session keys derived through the protocol's authenticated key-establishment procedure and AES-256-GCM with correct nonce management. This provisioning script does not implement key exchange, certificate issuance, certificate trust validation, rotation, revocation, or hardware-backed key storage.
