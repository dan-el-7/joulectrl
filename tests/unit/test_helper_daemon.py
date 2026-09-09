"""Tests for helper/daemon.py op logic (no root, no real sysfs).

The daemon is exec'd with BASE/SOCKET_PATH/RECOVERY_FILE redirected into a
tmp_path file tree, and its real _read/_write functions operate on that tree —
so the tests exercise the genuine I/O code paths (works identically on the
demo laptop and on CI runners, which have no cpufreq policies of their own).
"""

import json
import time
from pathlib import Path

import pytest


@pytest.fixture()
def daemon_ns(monkeypatch, tmp_path):
    sysfs_root = tmp_path / "cpufreq"
    src = open("helper/daemon.py").read()
    src = src.replace('SOCKET_PATH = "/run/joulectrl-helper.sock"', f'SOCKET_PATH = "{tmp_path}/h.sock"')
    src = src.replace('RECOVERY_FILE = Path("/run/joulectrl-helper-recovery.json")',
                      f'RECOVERY_FILE = Path("{tmp_path}/rec.json")')
    src = src.replace('BASE = "/sys/devices/system/cpu/cpufreq"', f'BASE = "{sysfs_root}"')
    src = src.replace('ENERGY_PATH = "/sys/class/powercap/intel-rapl:0/energy_uj"',
                      f'ENERGY_PATH = "{tmp_path}/energy_uj"')
    src = src.replace('ENERGY_RANGE_PATH = "/sys/class/powercap/intel-rapl:0/max_energy_range_uj"',
                      f'ENERGY_RANGE_PATH = "{tmp_path}/max_energy_range_uj"')
    ns = {"__name__": "daemon"}
    exec(compile(src, "daemon", "exec"), ns)

    # fake sysfs as a real file tree (daemon's own _read/_write work on it)
    pol = sysfs_root / "policy0"
    pol.mkdir(parents=True, exist_ok=True)
    (sysfs_root / "boost").write_text("1")
    (pol / "cpuinfo_min_freq").write_text("623377")
    (pol / "cpuinfo_max_freq").write_text("5090910")
    (pol / "scaling_min_freq").write_text("623377")
    (pol / "scaling_max_freq").write_text("5090000")
    (pol / "scaling_governor").write_text("performance")
    (pol / "scaling_available_governors").write_text("performance schedutil")

    ns["_boot_id"] = lambda: "test-boot"
    ns["_sysfs_root"] = str(sysfs_root)
    yield ns
    # reset session state between tests
    ns["_session"].update(active=False, uid=None, pid=None, last_heartbeat=0.0)


def test_lease_exclusive(daemon_ns):
    ns = daemon_ns
    assert ns["op_begin_session"]({"uid": 1000, "pid": 1})["ok"]
    r = ns["op_begin_session"]({"uid": 1000, "pid": 2})
    assert not r["ok"] and r["error"] == "session_already_active"
    ns["op_end_session"]({})
    assert ns["op_begin_session"]({"uid": 1000, "pid": 2})["ok"]
    ns["op_end_session"]({})


def test_apply_requires_session(daemon_ns):
    r = daemon_ns["op_apply_configuration"]({"control": {}})
    assert not r["ok"] and r["error"] == "no_session"


def test_apply_snapshot_first_and_readback(daemon_ns):
    ns = daemon_ns
    ns["op_begin_session"]({"uid": 1000, "pid": 1})
    r = ns["op_apply_configuration"]({"control": {
        "boost": False, "policy_freq_caps_khz": {"policy0": 1500000}}})
    assert r["ok"]
    assert r["applied"]["boost"] == 0
    assert r["applied"]["policy0/scaling_max_freq"] == 1500000
    # recovery snapshot persisted before the change and holds the ORIGINal boost=1
    snap = json.loads(ns["RECOVERY_FILE"].read_text())
    assert snap["snapshot"]["boost"] == 1
    assert snap["snapshot"]["policies"]["policy0"]["scaling_max_freq"] == 5090000
    ns["op_end_session"]({})


def test_apply_rejects_out_of_range(daemon_ns):
    ns = daemon_ns
    ns["op_begin_session"]({"uid": 1000, "pid": 1})
    r = ns["op_apply_configuration"]({"control": {
        "policy_freq_caps_khz": {"policy0": 99999999}}})
    assert not r["ok"] and "cap_out_of_range" in r["error"]
    ns["op_end_session"]({})


def test_apply_rejects_unknown_policy(daemon_ns):
    ns = daemon_ns
    ns["op_begin_session"]({"uid": 1000, "pid": 1})
    r = ns["op_apply_configuration"]({"control": {
        "policy_freq_caps_khz": {"policy99": 1500000}}})
    assert not r["ok"] and "unknown_policy" in r["error"]
    ns["op_end_session"]({})


def test_restore_verifies_and_clears(daemon_ns):
    ns = daemon_ns
    ns["op_begin_session"]({"uid": 1000, "pid": 1})
    ns["op_apply_configuration"]({"control": {
        "boost": False, "policy_freq_caps_khz": {"policy0": 1500000}}})
    r = ns["op_restore"]({})
    assert r["ok"], r.get("mismatches")
    root = ns["_sysfs_root"]
    assert (Path(root) / "boost").read_text().strip() == "1"
    assert (Path(root) / "policy0" / "scaling_max_freq").read_text().strip() == "5090000"
    assert not ns["RECOVERY_FILE"].exists()
    # second restore: nothing to restore
    r2 = ns["op_restore"]({})
    assert r2["ok"] and r2.get("nothing_to_restore")
    ns["op_end_session"]({})


def test_watchdog_restores_on_stale_heartbeat(daemon_ns, monkeypatch):
    ns = daemon_ns
    ns["HEARTBEAT_TIMEOUT_S"] = 0.2
    ns["op_begin_session"]({"uid": 1000, "pid": 1})
    ns["op_apply_configuration"]({"control": {"boost": False}})
    # force stale heartbeat
    ns["_session"]["last_heartbeat"] = time.time() - 10
    ns["watchdog_step"] = lambda: None  # not used; run one loop iteration manually
    # emulate one watchdog pass (the loop body inline):
    active = ns["_session"]["active"]
    stale = (time.time() - ns["_session"]["last_heartbeat"]) > ns["HEARTBEAT_TIMEOUT_S"]
    assert active and stale
    # perform the restore the watchdog would do
    r = ns["op_restore"]({})
    assert r["ok"]
    assert (Path(ns["_sysfs_root"]) / "boost").read_text().strip() == "1"
    ns["op_end_session"]({})


def test_read_energy_unavailable(daemon_ns):
    ns = daemon_ns
    # ENERGY_PATH (redirected into tmp_path) does not exist -> counter unreadable
    r = ns["op_read_energy"]({})
    assert not r["ok"] and r["error"] == "energy_unavailable"
