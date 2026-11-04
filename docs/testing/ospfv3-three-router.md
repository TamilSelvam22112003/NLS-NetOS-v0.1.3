# Three-router OSPFv3 regression test

The project-owned test uses FRR's topotest framework to build a linear
R1--R2--R3 IPv6 topology. It checks:

1. OSPFv3 adjacencies reach Full on both transit links.
2. R1 installs R3's advertised loopback prefix in its Linux IPv6 FIB.
3. Taking down the R2--R3 transit interface withdraws that route.
4. Restoring the interface causes the route to be learned again.

## Run in CI or a prepared Ubuntu host

The test must run as root because FRR topotests create network namespaces and
virtual links. First build and stage FRR with the repository build script,
then install the staged FRR runtime and the Python/networking dependencies
listed in `.github/workflows/frr-build-ospfv3.yml`.

From the repository root:

```sh
cd third_party/frr/tests/topotests
sudo -E python3 -m pytest -v -s ../../../../tests/topotests/nls_ospfv3_three_router/test_nls_ospfv3_three_router.py
```

Logs are written under `/tmp/topotests/`. The GitHub Actions workflow uploads
these logs even when a test fails.

This is an underlay OSPFv3 regression test only. It does not test Router-CA,
NLS handshake/session establishment, vIP routing, encrypted packet forwarding,
or NLS route-adapter behavior.
