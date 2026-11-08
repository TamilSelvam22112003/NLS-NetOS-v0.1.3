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
| Router-CA SHA-512 derivation digest | `/var/lib/nls-netos/crypto/sha-512/r-ca-vip.key` | root:root, 0600; derived identifier material, not a secret |
| Home CA VIP record | `/var/lib/nls-netos/nls-router-ca/home-ca/home-ca-vip.json` | root:root, 0600 |
| Home CA certificate (when provisioned) | `/var/lib/nls-netos/nls-router-ca/home-ca/root-ca.crt` | public certificate |
| ISP CA directory | `/var/lib/nls-netos/nls-router-ca/isp-ca/` | root-owned directory |

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
5. Runs `/usr/lib/nls-netos/home-ca-vip.py` to derive a time-bucketed Home Router-CA virtual IPv6 identifier. It writes the SHA-512 hex digest to `crypto/sha-512/r-ca-vip.key` and structured lifecycle metadata to `home-ca/home-ca-vip.json`.

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
- `/usr/lib/nls-netos/home-ca-vip.py`
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

## Home Router-CA VIP derivation

The installed `home-ca-vip.py` utility canonicalizes the Home CA metadata JSON (excluding the volatile `management.last_inspected` field), combines it with a domain-separated UTC time-bucket identifier, and computes SHA-512. The default bucket is five minutes. Repeated derivations using identical metadata and the same bucket produce the same identifier; a later bucket produces a different identifier.

The first 120 digest bits are combined with the RFC 4193 `fd/8` Unique Local Address prefix to produce an expanded eight-hextet IPv6 ULA. This is intentionally not a globally routable address. The utility writes:

- `/var/lib/nls-netos/crypto/sha-512/r-ca-vip.key`: the 512-bit digest as one hexadecimal line.
- `/var/lib/nls-netos/nls-router-ca/home-ca/home-ca-vip.json`: the derived IPv6 identifier, metadata fingerprint, algorithm/domain, bucket start, generation time, expiry time, and explicit unauthenticated status.

The VIP record expires at the end of its five-minute bucket. Peers must use the same canonical CA metadata and bucket rules to reproduce it. A deployment protocol must define clock-skew tolerance and session rollover before using this value for routing. The digest is derived from public metadata and time: despite the requested `.key` filename, it is **not secret key material**, must not be used as an encryption/MAC key, and does not prove certificate trust or peer authentication. The VIP is an identifier only. Authentication still requires certificate-chain and identity validation plus an authenticated session handshake.

For a deterministic local test:
```bash
python3 scripts/home-ca-vip.py \
  --metadata /path/to/home-ca-metadata.json \
  --digest-output /tmp/r-ca-vip.key \
  --record-output /tmp/home-ca-vip.json \
  --now 2026-11-08T15:20:00Z
python3 -m unittest discover -s tests -p 'test_router_ca_vip.py' -v
```
