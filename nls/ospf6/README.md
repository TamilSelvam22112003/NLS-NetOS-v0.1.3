# OSPFv3 / NLS adapter boundary

This directory defines the intended integration boundary; it is not yet a running routing adapter.

The first adapter milestone must consume authenticated NLS peer/session events and interact with FRR through a supported management interface (preferably FRR northbound/gRPC or a carefully constrained vtysh/VTY integration). It must not parse or rewrite OSPFv3 packets.

Required adapter contract:
- Input: authenticated peer identity, validated peer IPv6 endpoint, session state, assigned vIP/prefix, and monotonically versioned event.
- Output: explicit route add/delete request with validated prefix, next hop, interface, and ownership tag.
- Fail closed: no route installation for unauthenticated, expired, revoked, or replayed peer events.
- Reconcile: after restart, compare NLS-owned routes against active authenticated sessions and remove stale routes.
- Safety: never alter OSPFv3 protocol packets or install a route that overrides protected underlay/control-plane prefixes.

Before enabling route programming, implement schema validation, authorization, idempotency, route ownership, rollback, and network-namespace integration tests.
