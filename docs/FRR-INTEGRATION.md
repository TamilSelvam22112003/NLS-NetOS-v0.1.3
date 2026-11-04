# FRRouting integration and filesystem layout

## Upstream source
The build script clones https://github.com/FRRouting/frr.git into a disposable build directory. It uses upstream `master` unless `FRR_REF` is set to a release tag or commit. For reproducible builds, set `FRR_REF` to a tested immutable commit or release tag.

The source checkout is not the installed runtime tree. FRR must be compiled and installed into a staging root.

## Staged filesystem

```text
etc/frr/                 configuration templates
usr/bin/                 user-facing tools (for example vtysh)
usr/sbin/frr/            FRR helper/legacy commands
usr/lib/frr/             routing daemons and internal executables
usr/share/doc/frr/       docs and examples
var/log/frr/             log directory
var/run/frr/             runtime files and VTY sockets
lib/systemd/system/      frr.service
```

The build uses DESTDIR staging at `build/rootfs/`; it does not change the host's live routing installation.

## Build and install
```bash
sudo ./scripts/build-frr.sh
sudo ./scripts/install-frr.sh
```

Set `FRR_REF` to pin an upstream release/tag/commit. Installation is intended for a disposable Ubuntu/Debian test VM. The installer creates the `frr` account, copies the staged root, reloads systemd, and leaves the service stopped.

## Configuration
- `/etc/frr/daemons` controls which daemons are started.
- Zebra is enabled by default; OSPF/BGP are disabled until deliberately enabled.
- Edit interface names, addresses and routing policy for the test topology.
- The service unit is an NLS project template; validate against the exact FRR version and supported Ubuntu/Debian release before production use.

## Security boundary
FRR provides routing protocols; this integration does not implement NLS encryption. NLS/FRR interaction belongs in the separate integration layer.
