# FRRouting integration and filesystem layout

## Upstream source checkout
FRRouting is linked as a Git submodule at `third_party/frr`, pointing to https://github.com/FRRouting/frr.git. The submodule is pinned to a specific upstream commit in the NetOS Git tree. To initialize it after cloning:

```bash
git submodule update --init --recursive
```

FRR's upstream `master` branch is its primary development branch and is unstable; the NetOS submodule commit remains pinned until intentionally updated.

## Build
```bash
sudo ./scripts/build-frr.sh
```

The build script runs upstream `bootstrap.sh`, configures and compiles FRR, and stages installation under `build/rootfs/`. It does not overwrite the host installation.

## Target filesystem
The staged installation includes:
- `etc/frr/` — daemon selection and configuration
- `usr/bin/` — vtysh and user-facing tools
- `usr/lib/frr/` — Zebra, OSPF and other routing daemons
- `usr/share/doc/frr/` — documentation and examples
- `var/log/frr/` and `var/run/frr/` — logs and runtime sockets
- `lib/systemd/system/frr.service` — project service template

The `usr/sbin/frr/` directory is reserved for helper/legacy commands if supplied by the upstream build.

## OSPF integration validation
The GitHub Actions workflow `.github/workflows/frr-build-ospf.yml` builds upstream FRR, checks that Zebra/OSPFd/vtysh binaries exist, and runs FRR's upstream `ospf_topo1` topotest. This is an actual multi-router OSPF topology test, not merely a configuration syntax check.

## Install on a disposable Ubuntu test VM
After building:
```bash
sudo ./scripts/install-frr.sh
```
Review `/etc/frr/daemons` and router configuration before enabling services. The CI workflow installs only into its disposable runner. The custom systemd unit must be validated against the exact FRR build and target Ubuntu release before production use.

## NLS boundary
FRR provides routing protocols. It does not implement NLS packet encryption. The NLS/FRR integration layer must be developed and tested separately.
