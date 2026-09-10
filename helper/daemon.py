#!/home/dan-el/.hermes/hermes-agent/venv/bin/python3
"""joulectrl privileged helper — root daemon over a Unix socket (Agent A owns).

Narrow op set (frozen contract, AGENTS.md §5):
    begin_session, read_energy, apply_configuration, heartbeat, restore, end_session

Rules honored:
- No shell, no arbitrary paths, no arbitrary sysfs writes — only the exact paths
  the capability report verified, with values validated against policy bounds.
- Peer-credential auth: SO_PEERCRED is resolved on every connection and the
  kernel-provided uid/pid are authoritative (client-supplied uid/pid args are
  ignored). Access is restricted to ALLOWED_UIDS (default: invoking user 1000
  and root); other local users are refused before any op runs.
- Snapshot-restore: apply_configuration persists a recovery snapshot BEFORE writing;
  restore puts it back; heartbeat-loss watchdog auto-restores.
- read_energy: powercap package-0 counter (root-only on this machine).

Wire protocol: one JSON request per line, one JSON response per line.
Run as root (pkexec). One pkexec prompt at launch, then prompt-free ops.
"""

from __future__ import annotations

import json
import os
import socket
import struct
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

SOCKET_PATH = "/run/joulectrl-helper.sock"
# Kernel-verified peer credentials gate every connection (SO_PEERCRED).
# Only these uids may talk to the daemon; root is always allowed. The invoking
# user is taken from PKEXEC_UID (set by pkexec) when present.
_pkexec_uid = os.environ.get("PKEXEC_UID", "")
ALLOWED_UIDS = {0, int(_pkexec_uid) if _pkexec_uid.isdigit() else 1000}
RECOVERY_FILE = Path("/run/joulectrl-helper-recovery.json")  # tmpfs: cleared on reboot
HEARTBEAT_TIMEOUT_S = 30.0
OP_SET = ["begin_session", "read_energy", "apply_configuration",
          "heartbeat", "restore", "end_session"]

BASE = "/sys/devices/system/cpu/cpufreq"
ENERGY_PATH = "/sys/class/powercap/intel-rapl:0/energy_uj"
ENERGY_RANGE_PATH = "/sys/class/powercap/intel-rapl:0/max_energy_range_uj"
PSTATE_STATUS_PATH = "/sys/devices/system/cpu/amd_pstate/status"

_orig_state: Dict[str, Any] = {}
_session: Dict[str, Any] = {"active": False, "uid": None, "pid": None,
                            "last_heartbeat": 0.0, "began_at": None}
_lock = threading.Lock()


def _policy_dirs() -> list:
    return sorted(Path(BASE).glob("policy*"),
                  key=lambda p: int("".join(c for c in p.name if c.isdigit())))


def _read_int(path: str) -> Optional[int]:
    try:
        with open(path) as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


def _write_int(path: str, value: int) -> bool:
    try:
        with open(path, "w") as f:
            f.write(str(value))
        return True
    except OSError:
        return False


def snapshot_state() -> Dict[str, Any]:
    """Read-only capture of all knobs the helper may touch."""
    snap: Dict[str, Any] = {"time": time.time(), "policies": {}}
    for pd in _policy_dirs():
        name = pd.name
        snap["policies"][name] = {
            "scaling_min_freq": _read_int(f"{pd}/scaling_min_freq"),
            "scaling_max_freq": _read_int(f"{pd}/scaling_max_freq"),
            "scaling_governor": _read_str(f"{pd}/scaling_governor"),
        }
    boost = Path(f"{BASE}/boost")
    if boost.exists():
        snap["boost"] = _read_int(str(boost))
    # amd_pstate mode (active|guided|passive) — EXPERIMENTAL dev knob; restored
    # with everything else. Only present on AMD pstate systems.
    if Path(PSTATE_STATUS_PATH).exists():
        snap["pstate_mode"] = _read_str(PSTATE_STATUS_PATH)
    return snap


def _read_str(path: str) -> Optional[str]:
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None


_GOVERNORS: Optional[set] = None


def _allowed_governors(pd: Path) -> set:
    """Governors this policy accepts (from scaling_available_governors)."""
    global _GOVERNORS
    if _GOVERNORS is None:
        v = _read_str(f"{pd}/scaling_available_governors") or ""
        _GOVERNORS = set(v.split())
    return _GOVERNORS


def _read_int_retry(path: str, want: Optional[int], tries: int = 10, delay: float = 0.1) -> Optional[int]:
    """Read a knob; amd-pstate applies writes asynchronously, so retry briefly
    until the readback matches the intended value (or tries run out)."""
    v = _read_int(path)
    for _ in range(tries):
        if v is None or (want is not None and v != want):
            time.sleep(delay)
            v = _read_int(path)
        else:
            break
    return v


def apply_snapshot(snap: Dict[str, Any]) -> Dict[str, Any]:
    """Restore a snapshot. Order matters: boost FIRST (re-enabling boost raises
    cpuinfo_max before high caps are written; boost=0 clamps cpuinfo_max to
    ~2 GHz on this machine and would silently clamp the restore)."""
    if snap.get("pstate_mode"):
        _write_str(PSTATE_STATUS_PATH, snap["pstate_mode"])
        time.sleep(0.3)  # mode switch re-inits policy attributes; let them settle
    if snap.get("boost") is not None:
        _write_int(f"{BASE}/boost", snap["boost"])
        _read_int_retry(f"{BASE}/boost", snap["boost"])
    for name, vals in snap.get("policies", {}).items():
        pd = Path(BASE) / name
        if vals.get("scaling_max_freq") is not None:
            _write_int(f"{pd}/scaling_max_freq", vals["scaling_max_freq"])
            _read_int_retry(f"{pd}/scaling_max_freq", vals["scaling_max_freq"])
        if vals.get("scaling_min_freq") is not None:
            _write_int(f"{pd}/scaling_min_freq", vals["scaling_min_freq"])
            _read_int_retry(f"{pd}/scaling_min_freq", vals["scaling_min_freq"])
        if vals.get("scaling_governor") is not None:
            _write_str(f"{pd}/scaling_governor", vals["scaling_governor"])
    return snapshot_state()  # readback


def _write_str(path: str, value: str) -> bool:
    try:
        with open(path, "w") as f:
            f.write(value)
        return True
    except OSError:
        return False


def op_begin_session(args: Dict[str, Any], peer: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    with _lock:
        if _session["active"]:
            return {"ok": False, "error": "session_already_active",
                    "held_by_uid": _session["uid"], "held_by_pid": _session["pid"]}
        # Kernel-verified credentials are authoritative; args uid/pid are ignored.
        # (peer=None only in direct unit-test invocation; the socket path always supplies it.)
        creds = peer or {"uid": args.get("uid"), "pid": args.get("pid")}
        _session.update(active=True, uid=creds["uid"], pid=creds["pid"],
                        began_at=time.time(), last_heartbeat=time.time())
        return {"ok": True, "session": {k: _session[k] for k in
                ("active", "uid", "pid", "began_at")}}


def op_read_energy(args: Dict[str, Any], peer: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    uj = _read_int(ENERGY_PATH)
    if uj is None:
        return {"ok": False, "error": "energy_unavailable"}
    return {"ok": True, "uj": uj, "t": time.time()}


def op_apply_configuration(args: Dict[str, Any], peer: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    with _lock:
        if not _session["active"]:
            return {"ok": False, "error": "no_session"}
        global _orig_state
        # persist recovery snapshot BEFORE first change (once per session)
        if not _orig_state:
            _orig_state = snapshot_state()
            RECOVERY_FILE.write_text(json.dumps({"snapshot": _orig_state,
                                                 "boot_id": _boot_id(),
                                                 "saved_at": time.time()}))
            os.chmod(RECOVERY_FILE, 0o600)
        requested = args.get("control", {})
        applied = {}
        # EXPERIMENTAL dev option: switch amd_pstate mode (e.g. passive, where
        # frequency caps bind WITH boost on). Written first so subsequent cap
        # writes take effect under the new mode. Restore puts the original mode
        # back. Off by default; only honored when explicitly requested.
        pstate_mode = requested.get("pstate_mode")
        if pstate_mode in ("active", "guided", "passive"):
            if Path(PSTATE_STATUS_PATH).exists():
                _write_str(PSTATE_STATUS_PATH, pstate_mode)
                applied["pstate_mode"] = _read_str(PSTATE_STATUS_PATH)
        # Order matters: boost first, then per-policy caps.
        # NOTE machine fact (demo laptop): boost=0 clamps cpuinfo_max to ~2 GHz,
        # so caps are validated AFTER the boost write against post-toggle bounds.
        boost = requested.get("boost")
        if boost is not None:
            _write_int(f"{BASE}/boost", 1 if boost else 0)
            applied["boost"] = _read_int(f"{BASE}/boost")
        caps = requested.get("policy_freq_caps_khz") or {}
        clamp_caps = bool(requested.get("clamp_out_of_range", False))
        # Validate ALL requests before writing any (no partial application):
        # policy names must exist, caps resolved against post-boost hw bounds.
        resolved_caps = []
        for pname, khz in caps.items():
            pd = Path(BASE) / str(pname)
            if not pd.exists():
                return {"ok": False, "error": f"unknown_policy:{pname}"}
            hw_min = _read_int(f"{pd}/cpuinfo_min_freq")
            hw_max = _read_int(f"{pd}/cpuinfo_max_freq")
            target_khz = int(khz)
            if hw_max is not None and not (hw_min is None or hw_min <= target_khz <= hw_max):
                if clamp_caps:
                    if hw_max is not None and target_khz > hw_max:
                        target_khz = hw_max
                    if hw_min is not None and target_khz < hw_min:
                        target_khz = hw_min
                else:
                    return {"ok": False, "error": f"cap_out_of_range:{pname}:{khz}"}
            resolved_caps.append((pname, pd, target_khz))
        governors = requested.get("policy_governors") or {}
        resolved_governors = []
        for pname, gov in governors.items():
            pd = Path(BASE) / str(pname)
            if not pd.exists():
                return {"ok": False, "error": f"unknown_policy:{pname}"}
            if gov not in _allowed_governors(pd):
                return {"ok": False, "error": f"governor_not_allowed:{pname}:{gov}"}
            resolved_governors.append((pname, pd, gov))
        # Validation passed — now write everything.
        for pname, pd, target_khz in resolved_caps:
            _write_int(f"{pd}/scaling_max_freq", target_khz)
            applied[f"{pname}/scaling_max_freq"] = _read_int_retry(
                f"{pd}/scaling_max_freq", target_khz)
        for pname, pd, gov in resolved_governors:
            _write_str(f"{pd}/scaling_governor", gov)
            applied[f"{pname}/scaling_governor"] = _read_str(f"{pd}/scaling_governor")
        return {"ok": True, "applied": applied}


def op_heartbeat(args: Dict[str, Any], peer: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    with _lock:
        if not _session["active"]:
            return {"ok": False, "error": "no_session"}
        _session["last_heartbeat"] = time.time()
        return {"ok": True, "t": _session["last_heartbeat"]}


def op_restore(args: Dict[str, Any], peer: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    with _lock:
        global _orig_state
        if not _orig_state:
            readback = snapshot_state()
            return {"ok": True, "nothing_to_restore": True, "state": readback}
        expected = {k: v for k, v in _orig_state.items() if k != "time"}
        readback = apply_snapshot(_orig_state)
        readback_cmp = {k: v for k, v in readback.items() if k != "time"}
        restored_ok = readback_cmp == expected
        _orig_state = {}
        RECOVERY_FILE.unlink(missing_ok=True)
        _session.update(active=False)
        return {"ok": restored_ok, "restored": readback_cmp,
                "mismatches": [k for k in expected
                               if expected[k] != readback_cmp.get(k)] if not restored_ok else []}


def op_end_session(args: Dict[str, Any], peer: Optional[Dict[str, Any]] = None) -> Dict[str, All] | Dict[str, Any]:
    with _lock:
        was_active = _session["active"]
        _session.update(active=False, uid=None, pid=None)
    return {"ok": True, "ended": was_active}


def _boot_id() -> str:
    try:
        with open("/proc/sys/kernel/random/boot_id") as f:
            return f.read().strip()
    except OSError:
        return ""


def watchdog() -> None:
    """Auto-restore if heartbeat is lost (session crash insurance)."""
    while True:
        time.sleep(5.0)
        with _lock:
            active = _session["active"]
            stale = (time.time() - _session["last_heartbeat"]) > HEARTBEAT_TIMEOUT_S
        if active and stale:
            with _lock:
                global _orig_state
                if _orig_state:
                    apply_snapshot(_orig_state)
                    _orig_state = {}
                    RECOVERY_FILE.unlink(missing_ok=True)
                _session.update(active=False)
            print(f"[helper] watchdog restored state (heartbeat lost at {time.time():.0f})", flush=True)


OPS = {"begin_session": op_begin_session, "read_energy": op_read_energy,
       "apply_configuration": op_apply_configuration, "heartbeat": op_heartbeat,
       "restore": op_restore, "end_session": op_end_session}


def _peer_credentials(conn: socket.socket) -> Optional[Dict[str, int]]:
    """Resolve SO_PEERCRED — the kernel's authoritative uid/pid for this connection."""
    try:
        creds = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
        pid, uid, gid = struct.unpack("3i", creds)
        return {"pid": pid, "uid": uid, "gid": gid}
    except OSError:
        return None


def handle_conn(conn: socket.socket) -> None:
    peer = _peer_credentials(conn)
    if peer is None or peer["uid"] not in ALLOWED_UIDS:
        # Refuse before reading anything: untrusted local users get no protocol access.
        print(f"[helper] refused connection peer={peer}", flush=True)
        return
    with conn:
        f = conn.makefile("rw")
        op = None
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
                op = req.get("op")
                if op not in OPS:
                    resp = {"ok": False, "error": f"unknown_op:{op}"}
                else:
                    resp = OPS[op](req.get("args", {}), peer)
            except json.JSONDecodeError as e:
                resp = {"ok": False, "error": f"bad_json:{e}"}
            f.write(json.dumps(resp) + "\n")
            f.flush()
            if op == "end_session":
                break


def main() -> None:
    if os.geteuid() != 0:
        raise SystemExit("must run as root (pkexec)")
    if os.path.exists(SOCKET_PATH):
        os.unlink(SOCKET_PATH)
    threading.Thread(target=watchdog, daemon=True).start()
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(SOCKET_PATH)
    # Owner-group the socket to the first allowed non-root uid so that user can
    # connect; SO_PEERCRED gate in handle_conn refuses everyone else.
    try:
        import pwd
        for uid in sorted(ALLOWED_UIDS - {0}):
            os.chown(SOCKET_PATH, uid, pwd.getpwuid(uid).pw_gid)
            break
    except (KeyError, ImportError, OSError):
        pass
    os.chmod(SOCKET_PATH, 0o660)
    print(f"[helper] listening on {SOCKET_PATH}", flush=True)
    srv.listen(4)
    while True:
        conn, _ = srv.accept()
        threading.Thread(target=handle_conn, args=(conn,), daemon=True).start()


if __name__ == "__main__":
    main()
