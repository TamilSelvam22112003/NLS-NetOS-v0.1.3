#!/usr/bin/env python3
# SPDX-License-Identifier: ISC
"""Project-owned three-router OSPFv3 adjacency and IPv6 route test."""
import os
import sys
from functools import partial

import pytest

CWD = os.path.dirname(os.path.realpath(__file__))
sys.path.append(os.path.join(CWD, "../../../third_party/frr/tests/topotests"))

from lib import topotest
from lib.topogen import Topogen, get_topogen
from lib.topolog import logger

pytestmark = [pytest.mark.ospf6d]


def build_topo(tgen):
    for name in ("r1", "r2", "r3"):
        tgen.add_router(name)
    # Router-to-router transit links, plus one stub LAN per edge router.
    for switch_name, routers in (
        ("s12", ("r1", "r2")),
        ("s23", ("r2", "r3")),
        ("s1lan", ("r1",)),
        ("s3lan", ("r3",)),
    ):
        switch = tgen.add_switch(switch_name)
        for router_name in routers:
            switch.add_link(tgen.gears[router_name])


def setup_module(mod):
    tgen = Topogen(build_topo, mod.__name__)
    tgen.start_topology()
    for router in tgen.routers().values():
        router.load_frr_config()
    tgen.start_router()


def teardown_module():
    tgen = get_topogen()
    tgen.stop_topology()


def test_three_router_adjacencies_reach_full():
    tgen = get_topogen()
    if tgen.routers_have_failure():
        pytest.skip(tgen.errors)
    expected = {
        "r1": ["10.255.0.2"],
        "r2": ["10.255.0.1", "10.255.0.3"],
        "r3": ["10.255.0.2"],
    }
    for router_name, neighbor_ids in expected.items():
        for neighbor_id in neighbor_ids:
            check = partial(
                topotest.router_json_cmp,
                tgen.gears[router_name],
                "show ipv6 ospf6 neighbor json",
                {"neighbors": [{"neighborId": neighbor_id, "state": "Full"}]},
            )
            _, result = topotest.run_and_expect(check, None, count=90, wait=1)
            assert result is None, (
                f"{router_name} did not reach Full with {neighbor_id}: {result}"
            )


def test_remote_loopback_route_installed_in_kernel():
    tgen = get_topogen()
    if tgen.routers_have_failure():
        pytest.skip(tgen.errors)

    def route_present():
        return tgen.gears["r1"].run("ip -6 route show 2001:db8:3::3/128")

    result, output = topotest.run_and_expect(
        lambda: route_present() if "2001:db8:3::3/128" in route_present() else None,
        True,
        count=90,
        wait=1,
    )
    assert result is True, f"r1 did not install r3 loopback route: {output}"


def test_transit_link_failure_withdraws_and_restores_route():
    tgen = get_topogen()
    if tgen.routers_have_failure():
        pytest.skip(tgen.errors)
    r2 = tgen.gears["r2"]
    r2.run("ip link set r2-eth1 down")
    try:
        def withdrawn():
            return "2001:db8:3::3/128" not in tgen.gears["r1"].run(
                "ip -6 route show 2001:db8:3::3/128"
            )
        result, output = topotest.run_and_expect(withdrawn, True, count=60, wait=1)
        assert result is True, f"r1 retained remote route after transit failure: {output}"
    finally:
        r2.run("ip link set r2-eth1 up")
    def restored():
        return "2001:db8:3::3/128" in tgen.gears["r1"].run(
            "ip -6 route show 2001:db8:3::3/128"
        )
    result, output = topotest.run_and_expect(restored, True, count=90, wait=1)
    assert result is True, f"r1 did not relearn r3 loopback after recovery: {output}"
