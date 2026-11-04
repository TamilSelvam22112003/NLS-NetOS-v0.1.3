# NLS-NetOS FRR Debian package

Build FRR into the staging root, then create a Debian package:

```bash
sudo ./scripts/build-frr.sh
./packaging/build-deb.sh
```

The package is written to `build/packages/`. It installs the staged FRR filesystem,
creates the FRR service account and runtime directories, and reloads systemd.
It deliberately does not enable or start routing daemons during package installation.
Inspect `/etc/frr/daemons` and router configuration before enabling the service.

This package currently contains the FRRouting runtime only. It is not a complete
bootable operating-system image and does not include NLS protocol implementation.
