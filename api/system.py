"""api/system.py — Background process noise detection and quieting for Joulectrl."""

import logging
import os
import signal
import subprocess
import time
from typing import Any, Optional

logger = logging.getLogger("joulectrl.system")

KNOWN_APP_PATTERNS = [
    ("brave", "Brave Browser", ["brave", "chrome_crashpad"]),
    ("chrome", "Google Chrome", ["chrome", "chromium", "google-chrome"]),
    ("firefox", "Mozilla Firefox", ["firefox", "firefox-bin"]),
    ("edge", "Microsoft Edge", ["msedge"]),
    ("discord", "Discord", ["discord", "discord-canary", "vesktop"]),
    ("slack", "Slack", ["slack"]),
    ("spotify", "Spotify", ["spotify"]),
    ("telegram", "Telegram", ["telegram-desktop", "telegram"]),
    ("teams", "Microsoft Teams", ["teams", "teams-for-linux"]),
    ("zoom", "Zoom", ["zoom"]),
    ("steam", "Steam", ["steam", "steamwebhelper"]),
    ("vlc", "VLC Media Player", ["vlc"]),
    ("mpv", "MPV Media Player", ["mpv"]),
]

PROTECTED_NAMES = {
    "systemd", "kthreadd", "gnome-shell", "mutter", "wayland", "xorg",
    "pipewire", "pipewire-pulse", "wireplumber", "dbus-daemon", "dbus-broker",
    "polkitd", "networkmanager", "gdm", "gdm3", "login", "sshd", "ssh",
    "bash", "sh", "zsh", "fish", "tmux", "screen",
    "warp-svc", "init",
}


def _get_ancestor_pids() -> set[int]:
    """Return PIDs of current process and all its ancestors."""
    ancestors = set()
    pid = os.getpid()
    while pid > 1:
        ancestors.add(pid)
        try:
            with open(f"/proc/{pid}/stat", "r") as f:
                ppid = int(f.read().split()[3])
                if ppid == pid:
                    break
                pid = ppid
        except Exception:
            break
    return ancestors


def is_process_protected(pid: int, comm: str, args: str, ancestors: Optional[set[int]] = None) -> bool:
    """True if process is part of system core, Joulectrl, or the active IDE/terminal."""
    if pid <= 2:
        return True
    if ancestors and pid in ancestors:
        return True
    
    comm_lower = comm.lower()
    args_lower = args.lower()

    if comm_lower in PROTECTED_NAMES:
        return True

    # Never kill Joulectrl, Antigravity, or Language Server
    if any(sig in comm_lower or sig in args_lower for sig in [
        "joulectrl", "antigravity", "language_server"
    ]):
        return True

    return False


def get_system_noise() -> dict[str, Any]:
    """Scan running processes for non-essential desktop apps and heavy CPU consumers."""
    ancestors = _get_ancestor_pids()
    try:
        output = subprocess.check_output(
            ["ps", "-eo", "pid,ppid,user,%cpu,%mem,comm,args", "--no-headers"],
            text=True,
            timeout=3.0,
        )
    except Exception as exc:
        logger.warning("Failed to inspect processes via ps: %s", exc)
        return {
            "is_quiet": True,
            "total_noise_cpu_pct": 0.0,
            "detected_apps": [],
            "unclassified_processes": [],
        }

    app_map: dict[str, dict[str, Any]] = {}
    unclassified: list[dict[str, Any]] = []
    total_noise_cpu = 0.0

    for line in output.strip().split("\n"):
        parts = line.strip().split(None, 6)
        if len(parts) < 7:
            continue
        pid_s, ppid_s, user, cpu_s, mem_s, comm, args = parts
        try:
            pid = int(pid_s)
            ppid = int(ppid_s)
            cpu = float(cpu_s)
            mem = float(mem_s)
        except ValueError:
            continue

        if pid <= 2 or ppid == 2 or comm.startswith("kworker") or comm.startswith("irq/"):
            continue

        if is_process_protected(pid, comm, args, ancestors):
            continue

        comm_lower = comm.lower()
        args_lower = args.lower()

        # Match known app patterns
        matched_app = None
        for key, name, tokens in KNOWN_APP_PATTERNS:
            if any(t in comm_lower or t in args_lower for t in tokens):
                matched_app = (key, name)
                break

        if matched_app:
            key, name = matched_app
            ent = app_map.setdefault(key, {
                "key": key,
                "name": name,
                "pids": [],
                "process_count": 0,
                "total_cpu_pct": 0.0,
                "total_mem_pct": 0.0,
            })
            ent["pids"].append(pid)
            ent["process_count"] += 1
            ent["total_cpu_pct"] = round(ent["total_cpu_pct"] + cpu, 1)
            ent["total_mem_pct"] = round(ent["total_mem_pct"] + mem, 1)
            total_noise_cpu += cpu
        elif cpu >= 1.5:
            unclassified.append({
                "pid": pid,
                "name": comm,
                "cpu_pct": cpu,
                "mem_pct": mem,
                "cmdline": args[:80],
            })
            total_noise_cpu += cpu

    detected_apps = list(app_map.values())
    is_quiet = len(detected_apps) == 0 and len(unclassified) == 0

    return {
        "is_quiet": is_quiet,
        "total_noise_cpu_pct": round(total_noise_cpu, 1),
        "detected_apps": detected_apps,
        "unclassified_processes": unclassified,
    }


def quiet_system(app_keys: Optional[list[str]] = None, pids: Optional[list[int]] = None) -> dict[str, Any]:
    """Terminate requested noisy applications/processes to establish a quiet baseline."""
    current_noise = get_system_noise()
    target_pids: set[int] = set()
    closed_apps: list[str] = []

    # Map requested app keys
    keys_set = set(app_keys) if app_keys is not None else None
    for app in current_noise["detected_apps"]:
        if keys_set is None or app["key"] in keys_set:
            target_pids.update(app["pids"])
            closed_apps.append(app["name"])

    # Add explicitly requested PIDs or all unclassified if none specified
    if pids is not None:
        target_pids.update(pids)
    elif keys_set is None:
        for proc in current_noise["unclassified_processes"]:
            target_pids.add(proc["pid"])

    ancestors = _get_ancestor_pids()
    terminated_pids = []

    # Phase 1: SIGTERM
    for pid in list(target_pids):
        # Final safety check before signal dispatch
        if pid <= 2 or pid in ancestors:
            continue
        try:
            os.kill(pid, signal.SIGTERM)
            terminated_pids.append(pid)
        except ProcessLookupError:
            pass
        except PermissionError as err:
            logger.warning("Permission denied terminating PID %d: %s", pid, err)
        except Exception as err:
            logger.warning("Failed to SIGTERM PID %d: %s", pid, err)

    if terminated_pids:
        time.sleep(0.3)

    # Phase 2: SIGKILL remaining
    for pid in terminated_pids:
        try:
            # Check if still alive
            os.kill(pid, 0)
            # If so, force kill
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except Exception:
            pass

    return {
        "ok": True,
        "terminated_pids": terminated_pids,
        "closed_apps": closed_apps,
        "remaining_noise": get_system_noise(),
    }


def get_thermal_status() -> dict[str, Any]:
    """Inspect sysfs hwmon sensors for CPU temperature and thermal throttling risk."""
    import glob

    tctl_c: Optional[float] = None
    acpitz_c: Optional[float] = None
    source = "unavailable"

    for hwmon in sorted(glob.glob("/sys/class/hwmon/hwmon*")):
        name_path = os.path.join(hwmon, "name")
        if not os.path.exists(name_path):
            continue
        try:
            name = open(name_path).read().strip()
        except Exception:
            continue

        if name == "k10temp":
            source = "k10temp"
            for temp_in in sorted(glob.glob(os.path.join(hwmon, "temp*_input"))):
                try:
                    val = int(open(temp_in).read().strip()) / 1000.0
                    label_path = temp_in.replace("_input", "_label")
                    lbl = open(label_path).read().strip() if os.path.exists(label_path) else "Tctl"
                    if lbl == "Tctl" or tctl_c is None:
                        tctl_c = val
                except Exception:
                    pass
        elif name == "acpitz" and acpitz_c is None:
            for temp_in in sorted(glob.glob(os.path.join(hwmon, "temp*_input"))):
                try:
                    acpitz_c = int(open(temp_in).read().strip()) / 1000.0
                except Exception:
                    pass

    cpu_temp = tctl_c if tctl_c is not None else acpitz_c
    is_throttling = False
    warning_level = "normal"  # normal, elevated, critical
    message = "CPU temperature is normal."

    if cpu_temp is not None:
        if cpu_temp >= 95.0:
            is_throttling = True
            warning_level = "critical"
            message = f"CPU temperature is critical ({cpu_temp:.1f}°C). Thermal throttling is active."
        elif cpu_temp >= 85.0:
            warning_level = "elevated"
            message = f"CPU temperature is elevated ({cpu_temp:.1f}°C). Thermal throttling may occur under sustained load."
        else:
            message = f"CPU temperature is {cpu_temp:.1f}°C (normal)."

    return {
        "cpu_temp_c": cpu_temp,
        "is_throttling": is_throttling,
        "warning_level": warning_level,
        "message": message,
        "source": source,
    }

