# NLS-NetOS local cryptographic key provisioning

The package installs a **key-provisioning script and a systemd unit**. The keys themselves are generated on each target router; no private key or AES secret is stored in Git.

## Runtime locations

- AES-256 key: `/var/lib/nls-netos/crypto/aes-256/aes256.key` (32 raw bytes, root:root, mode 0600)
- RSA-2048 private key: `/var/lib/nls-netos/crypto/RSA-2048/private_key.pem` (root:root, mode 0600)
- RSA-2048 public key: `/var/lib/nls-netos/crypto/RSA-2048/public_key.pem` (root:root, mode 0644)

Existing valid keys are preserved across reboots and package upgrades. An incomplete or invalid pre-existing key set causes the service to fail closed; the script does not silently replace a router identity. Back up private material securely before recovery or reinstall.

## Boot integration

`nls-keygen.service` is a oneshot unit enabled by the Debian package's post-installation script. It executes at boot and before the optional `nls-router.service`, if that service exists. The key-generation unit is independent of FRR's `frr.service`; do not make FRR depend on it unless FRR itself consumes these keys.

OpenSSL must be installed before the service runs. The package declares `openssl` as a dependency; the boot script does not run apt.

## Manual operations

```bash
sudo systemctl status nls-keygen.service
sudo journalctl -u nls-keygen.service -b
sudo systemctl start nls-keygen.service
sudo find /var/lib/nls-netos/crypto -type f -printf '%M %u:%g %p\\n'
```

The service should report `active (exited)` after successful oneshot execution.

## Cryptographic scope

The AES key created here is a persistent local key, not a fleet-wide traffic key. NLS data-plane traffic should use independently derived per-session AES-256-GCM keys from the protocol's authenticated key-establishment procedure. RSA-2048 is provisioned as an identity/keypair artifact only; protocol authentication and certificate policy must define its actual use.
