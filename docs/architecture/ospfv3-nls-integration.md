# OSPFv3 as a mandatory NLS-NetOS component

## Status
Architecture and implementation requirements. This document is not evidence that OSPFv3 or NLS integration has passed testing.

## 1. Why OSPFv3 is mandatory
NLS-NetOS uses IPv6 as a foundational network layer. OSPFv3 is therefore a required IPv6 routing protocol for the initial multi-router NLS testbed and a release-gating component. The OSPFv3 baseline must work independently before NLS-specific integration is enabled. This separates routing defects from NLS cryptographic, identity, encapsulation, and forwarding defects.

## 2. Plane separation
1. **Routing plane — FRR ospf6d**: IPv6 neighbor discovery, adjacency state, Link State Database (LSDB), flooding, SPF calculation, and IPv6 route installation through Zebra.
2. **Trust/session plane — NLS components**: Router-CA identity validation, peer metadata exchange, key establishment, session lifecycle, vIP derivation/verification, and replay state.
3. **Secure data plane — NLS packet engine**: packet classification, authenticated encryption/decryption, encapsulation/decapsulation, sequence validation, and forwarding policy.

OSPFv3 provides IPv6 routing. It is not the NLS encryption layer. The first integration must keep OSPFv3 control traffic operational while NLS data-plane processing is developed and tested independently.

## 3. Required baseline
- FRR is built from the repository's pinned upstream submodule commit.
- zebra, ospf6d, and vtysh are present and executable.
- Three or more routers establish OSPFv3 adjacencies over IPv6 links.
- Neighbor state reaches Full where the topology and network type require it.
- LSDB contents converge consistently across routers.
- IPv6 routes are installed in the kernel routing table through Zebra.
- End-to-end IPv6 reachability succeeds across at least two routing hops.
- Adjacency loss and restoration produce expected route withdrawal and reconvergence.
- Tests retain logs, daemon versions, topology information, and failure diagnostics.

## 4. Required NLS integration stages
### Stage A — OSPFv3 baseline
Use upstream FRR ospf6d without NLS changes. Run upstream OSPFv3 topotests and a project-owned three-router IPv6 topology test.

### Stage B — NLS peer identity
Connect the NLS trust/session service to router identity and peer state. Validate Router-CA certificates and peer authorization independently of OSPF packet parsing.

### Stage C — NLS session and vIP lifecycle
Implement and test session establishment, peer metadata exchange, key derivation, vIP computation, expiry, rekey, and replay protection. Define explicit ownership and synchronization between the NLS service and routing manager.

### Stage D — Route and data-plane policy
Specify how authenticated peers and NLS virtual destinations map to IPv6 routes and forwarding policy. Define behavior for unknown peers, expired sessions, duplicate packets, route withdrawal, and daemon restart.

### Stage E — Packet processing
Implement NLS encapsulation and decapsulation in a separately testable component first. Preserve OSPFv3 control packets and other required network-control traffic. Do not encrypt or rewrite OSPFv3 packets as ordinary application payload.

### Stage F — Integrated multi-router validation
Test at least three NLS routers with IPv6 underlay links, OSPFv3 adjacencies, Router-CA identities, NLS sessions, vIP reachability, encrypted data traffic, replay rejection, peer failure, and reconvergence.

## 5. Release gates
| Gate | Pass criteria |
|---|---|
| OSPFv3 build | ospf6d builds and starts |
| OSPFv3 adjacency | Required neighbors reach Full |
| LSDB convergence | Expected LSAs and topology are consistent |
| IPv6 routing | Expected routes installed through Zebra |
| IPv6 forwarding | End-to-end traffic succeeds |
| Failure recovery | Routes withdraw and reconverge correctly |
| NLS identity | Invalid/untrusted router identity is rejected |
| NLS session | Authenticated peers establish valid sessions |
| NLS data plane | Encryption, authentication, and replay checks pass |
| Integrated topology | Three-router NLS traffic passes with OSPFv3 |

A release must not be marked OSPFv3-ready merely because the ospf6d binary exists or an upstream test workflow is defined. The relevant CI runs must pass and their logs must be retained.

## 6. FRR modification policy
Keep the upstream FRR submodule pinned and preserve a clean baseline. Prefer a separate NLS integration daemon or adapter communicating through supported FRR management interfaces before modifying ospf6d internals. If a protocol-level OSPFv3 change is proven necessary, document the exact RFC behavior, affected packet/state-machine path, interoperability implications, and regression tests. Keep the change isolated in a tracked patch or maintained fork and run relevant upstream OSPFv3 topotests.

## 7. Current implementation boundary
The repository currently defines FRR build and OSPFv2/OSPFv3 CI workflows. Those definitions do not establish successful compilation or successful test execution. This document records the required NLS architecture and acceptance criteria; it does not claim that the NLS integration stages have been implemented.
