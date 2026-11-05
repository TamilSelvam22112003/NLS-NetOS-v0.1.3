# NLS-NetOS cryptographic key provisioning

## Purpose

NLS-NetOS provisions per-machine key material on the target Ubuntu/Debian system. The repository contains only the generation code and systemd unit. **Generated keys must never be committed to Git, placed in a Codespace, or included in a distributable package.** A Codespace is an ephemeral development environment, not the target router's identity/key store.

## Runtime storage

| Material | Runtime path | Permissions |
|---|---|---|
| AES-256 raw key (32 bytes) | `/var/lib/nls-netos/crypto/aes-256/aes256.key` | root:root, 0600 |
| RSA-2048 private key | `/var/lib/nls-netos/crypto/RSA-2048/private_key.pem` | root:root, 0600 |
| RSA-2048 public key | `/var/lib/nls-netos/crypto/RSA-2048/public_key.pem` | root:root, 0644 |

The script validates existing keys and preserves them. It fails closed if an existing AES file has the wrong size, an RSA pair is incomplete, or the RSA public key does not match the private key. It does not silently rotate identity material. Back up private keys securely before recovery, reinstall, or replacement of the storage volume.

## OpenSSL prerequisite

The Debian package declares `openssl` as a runtime dependency. For a manual source checkout on Ubuntu, install it before running the script:

```bash
sudo apt-get update
sudo apt-get install -y openssl
openssl version
```

The boot-time script does not run apt or require network access.

## Package installation and boot activation

The package installs:

- `/usr/lib/nls-netos/generate-keys.sh`
- `/lib/systemd/system/nls-keygen.service`

Its post-installation script reloads systemd and enables the oneshot unit. On boot, systemd runs the unit after local filesystems are mounted. The unit is ordered before `nls-router.service` if that router unit is installed. Key provisioning is not coupled to FRR unless a future component explicitly consumes these keys.

## Manual source-tree test

From the repository root:

```bash
sudo apt-get update
sudo apt-get install -y openssl
sudo install -m 0700 scripts/generate-keys.sh /usr/local/sbin/nls-generate-keys
sudo /usr/local/sbin/nls-generate-keys
sudo find /var/lib/nls-netos/crypto -type f -printf '%M %u:%g %p\\n'
```

For a source-tree boot test, install the unit and script at their package paths:

```bash
sudo install -D -m 0700 scripts/generate-keys.sh /usr/lib/nls-netos/generate-keys.sh
sudo install -D -m 0644 lib/systemd/system/nls-keygen.service /lib/systemd/system/nls-keygen.service
sudo systemctl daemon-reload
sudo systemctl enable --now nls-keygen.service
sudo systemctl status nls-keygen.service
sudo journalctl -u nls-keygen.service -b --no-pager
```

A successful oneshot normally reports `active (exited)`. A manual reboot check can be performed with `sudo reboot`, then repeat the status and journal commands. Existing keys should be validated and preserved rather than regenerated.

## Cryptographic protocol note

The persistent AES key generated here is local machine material, not a fleet-wide traffic key. NLS data-plane traffic should use unique session keys derived through the protocol's authenticated key-establishment procedure and AES-256-GCM with correct nonce management. This provisioning script does not implement key exchange, certificates, rotation, revocation, or hardware-backed key storage.
