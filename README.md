# NLS-NetOS v0.1.3

NLS Network Operating System repository with an upstream FRRouting (FRR) integration and deployment layout.

## FRRouting integration

FRR upstream source: https://github.com/FRRouting/frr.git (upstream default branch: master).

This repository does not vendor a second copy of the complete FRR source tree. The build script clones upstream into a temporary build directory, builds it, and stages the installed files under the requested filesystem layout.

See [docs/FRR-INTEGRATION.md](docs/FRR-INTEGRATION.md).

## Build and stage

On a supported Debian/Ubuntu build host:

```bash
sudo ./scripts/build-frr.sh
```

The script builds and stages the installation in `build/rootfs/`. It does not install into the host root filesystem.

To install the staged tree onto a disposable test system:

```bash
sudo ./scripts/install-frr.sh
```

Review scripts and configurations before use on a production router. Routing daemons are disabled by default except zebra.

## Cryptographic key provisioning

NLS-NetOS installs a boot-time systemd oneshot service that generates and validates per-machine AES-256 and RSA-2048 key material. OpenSSL is installed as a declared package dependency. Private keys are generated on the target router and are never stored in this repository or embedded in the Debian package.

See [docs/CRYPTO-KEY-PROVISIONING.md](docs/CRYPTO-KEY-PROVISIONING.md) for the runtime paths, permissions, manual test procedure, and boot activation details.

Compiled FRR binaries and generated cryptographic keys are not committed.
