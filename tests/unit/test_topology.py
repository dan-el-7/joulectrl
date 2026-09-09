"""Tests for core/topology.py and core/discovery.py.

Uses the real demo-laptop fixtures where they exist; skips sysfs-requiring
assertions on non-Linux. Parsing logic is tested against inline fixture text.
"""

import json
import os
import sys

import pytest

from core.topology import Topology, PolicyInfo, read_core_class_map

IS_LINUX = sys.platform.startswith("linux")


def _fake_topo():
    # demo-laptop shape: 16 cpus, 8 cores, classes by hw_max_freq parity
    policies = []
    for cpu in range(16):
        hwmax = 5090910 if cpu % 2 == 0 else 3506494
        policies.append(PolicyInfo(
            name=f"policy{cpu}", cpus=[cpu], driver="amd-pstate-epp",
            governor="performance", min_freq=623377, max_freq=5090000,
            hw_min_freq=623377, hw_max_freq=hwmax,
        ))
    cores = {c: [c, c + 8] for c in range(8)}
    core_of = {cpu: cpu % 8 for cpu in range(16)}
    return Topology(ncpu=16, cores=cores, sockets={0: list(range(16))},
                    core_of_cpu=core_of, policies=policies)


def test_class_map_two_classes():
    m = read_core_class_map(_fake_topo())
    assert m.n_classes == 2
    fast = next(k for k, v in m.classes.items() if 0 in v)
    eff = next(k for k, v in m.classes.items() if 1 in v)
    assert m.classes[fast] == [0, 2, 4, 6, 8, 10, 12, 14]
    assert m.classes[eff] == [1, 3, 5, 7, 9, 11, 13, 15]
    assert m.hw_max_freq[fast] > m.hw_max_freq[eff]


def test_uniform_is_one_class():
    policies = [PolicyInfo(f"policy{c}", [c], "acpi-cpufreq", "schedutil",
                           None, None, None, 2400000) for c in range(4)]
    cores = {c: [c] for c in range(4)}
    core_of = {c: c for c in range(4)}
    topo = Topology(ncpu=4, cores=cores, sockets={0: [0, 1, 2, 3]},
                    core_of_cpu=core_of, policies=policies)
    m = read_core_class_map(topo)
    assert m.n_classes == 1


def test_smt_siblings():
    topo = _fake_topo()
    assert topo.smt_siblings(0) == [8]
    assert topo.smt_siblings(13) == [5]


@pytest.mark.skipif(not IS_LINUX, reason="needs this Linux machine's sysfs")
def test_real_topology_matches_fixture():
    fixture = os.path.join(os.path.dirname(__file__), "..", "..",
                           "fixtures", "real", "topology.json")
    if not os.path.exists(fixture):
        pytest.skip("fixture not yet committed")
    import json as _json
    fx = _json.load(open(fixture))
    # the fixture describes the demo laptop; on other machines (CI runners,
    # dev laptops) there is nothing to match — skip rather than fail.
    try:
        with open("/proc/sys/kernel/random/boot_id") as f:
            this_boot = f.read().strip()
    except OSError:
        pytest.skip("boot_id unreadable")
    if fx.get("boot_id") and not fx["boot_id"].startswith(this_boot[:8]):
        pytest.skip(f"fixture is from another machine (boot_id mismatch)")
    from core.topology import read_topology
    topo = read_topology()
    assert topo.ncpu == fx["ncpu"]
    assert {str(k): v for k, v in topo.cores.items()} == fx["smt_groups"]
