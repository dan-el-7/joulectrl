# docs/HELPER.md — privileged helper contract (Agent A owns)

## Op set (frozen — AGENTS.md §5)

```
begin_session        take the exclusive lease (one at a time)
read_energy          powercap package-0 counter (root-only on demo laptop)
apply_configuration  snapshot-first, then apply validated (boost, cap) controls
heartbeat            keep the lease alive
restore              put back the exact pre-apply snapshot, verify readback
end_session          release lease
```

That's all it accepts. No shell, no arbitrary paths, no arbitrary sysfs writes.

## Protocol

- Transport: Unix socket `/run/joulectrl-helper.sock`, JSON request/response,
  one object per line. `chmod 660`, root:root.
- Auth: local connections only (socket permissions). Every op logs uid/pid.
  (SO_PEERCRED peer-credential check to be hardwired in Gate 2 hardening.)
- Recovery snapshot: `/run/joulectrl-helper-recovery.json` (tmpfs — stale by
  construction after reboot; boot_id embedded to detect replay across reboots).
- Watchdog: helper auto-restores and drops the lease if no heartbeat for 30 s.
- Lease exclusivity: second `begin_session` is rejected while one is active.

## Launch (one pkexec prompt)

```
pkexec python3 helper/daemon.py
```

Then all ops are prompt-free through `helper/client.py` (HelperClient).

## Client

```python
from helper.client import HelperClient

c = HelperClient()
c.begin_session()
e1 = c.read_energy()          # {"ok": true, "uj": ..., "t": ...}
r = c.apply_configuration({"boost": False,
                           "policy_freq_caps_khz": {"policy0": 2000000}})
e2 = c.read_energy()
c.heartbeat()
c.restore()                   # returns readback; verify ok: true
c.end_session()
```

## Validation rules (apply_configuration)

- Policy names must exist; cap values are range-checked against that policy's
  `cpuinfo_min_freq`/`cpuinfo_max_freq` — out-of-range → error, no write.
- Write order: boost first, then per-policy `scaling_max_freq`.
- Readback is returned per written knob; mismatches are surfaced, not ignored.
