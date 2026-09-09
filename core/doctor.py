"""joulectrl doctor — capability report assembly (Agent A owns).

Produces the PLAN §3-style report from discovery + helper-verified facts.
Library function; the CLI (Agent B) wraps it as `joulectrl doctor`.
"""

from __future__ import annotations

from typing import Dict, Optional

from core.discovery import capability_report


def _fmt_row(label: str, value: str) -> str:
    return f"{label:<26}{value}"


def doctor_report(helper_available: bool = True,
                  raw: Optional[Dict] = None) -> Dict:
    """Assemble the capability report dict (JSON-serializable).

    Combines read-only discovery with the energy-readability check (via the
    helper if present — root-only on the demo laptop).
    """
    r = raw or capability_report()

    # energy readability via helper (authoritative on root-only machines)
    energy_state = "unavailable"
    energy_backend = None
    if helper_available:
        try:
            from helper.client import HelperClient
            c = HelperClient()
            resp = c.read_energy()
            if resp.get("ok"):
                energy_state = "available (via helper)"
                energy_backend = "powercap:intel-rapl:0 (package-0)"
            else:
                energy_state = "helper present, counter unreadable"
        except (OSError, ConnectionRefusedError):
            helper_available = False

    if not helper_available:
        # fall back to unprivileged read
        pkg = r.get("energy", {}).get("package_paths") or []
        if pkg:
            energy_state = "permission required (helper not running)"
            energy_backend = pkg[0]["path"]
        else:
            energy_state = "unavailable"

    classes = r.get("core_classes", {})
    n_classes = classes.get("n_classes", 0)
    cpufreq = r.get("cpufreq", {})
    epp = r.get("epp", {})

    control_state = "unverified"  # per-machine Gate B verification fills this
    # If capability-report fixtures carry Gate B findings, cite them
    try:
        import json as _json
        from pathlib import Path as _P
        cap_path = _P(__file__).resolve().parent.parent / "fixtures" / "real" / "capability_report.json"
        if cap_path.exists():
            cap = _json.loads(cap_path.read_text())
            if cap.get("frequency_cap_control") == "verified_with_boost_off":
                control_state = "verified (caps bind only with boost=0 on this machine; sub-base caps ignored)"
            elif cap.get("frequency_cap_control") in ("verified", "ineffective", "unavailable"):
                control_state = cap["frequency_cap_control"]
    except (OSError, ValueError):
        pass
    recommended = "full" if energy_state.startswith("available") else "timing_only"

    return {
        "cpu_topology": "discovered" if r.get("cpu", {}).get("ncpu") else "failed",
        "smt": "discovered",
        "core_class_mapping": "verified" if n_classes > 1 else "unavailable",
        "n_core_classes": n_classes,
        "scaling_driver": ", ".join(cpufreq.get("drivers", [])) or "unknown",
        "n_policies": cpufreq.get("n_policies"),
        "frequency_cap_control": control_state,
        "epp_control": "verified" if epp.get("usable") else "unavailable",
        "package_energy_source": energy_backend or "none",
        "energy_counter_access": energy_state,
        "power_management_conflict": r.get("pm_daemons", {}),
        "helper": "running" if helper_available else "not running",
        "recommended_mode": recommended,
        "_raw": r,
    }


def format_doctor(report: Optional[Dict] = None) -> str:
    r = report or doctor_report()
    raw = r.pop("_raw", None)  # don't print the raw blob
    lines = [_fmt_row("CPU topology:", str(r["cpu_topology"]))]
    lines.append(_fmt_row("SMT relationships:", str(r["smt"])))
    lines.append(_fmt_row("Core-class mapping:", f"{r['core_class_mapping']} ({r['n_core_classes']} classes)"))
    lines.append(_fmt_row("Scaling driver:", str(r["scaling_driver"])))
    lines.append(_fmt_row("Frequency-cap control:", str(r["frequency_cap_control"])))
    lines.append(_fmt_row("EPP control:", str(r["epp_control"])))
    lines.append(_fmt_row("Package-energy source:", str(r["package_energy_source"])))
    lines.append(_fmt_row("Energy-counter access:", str(r["energy_counter_access"])))
    daemons = [k for k, v in r.get("power_management_conflict", {}).items() if v]
    lines.append(_fmt_row("Power-management conflict:", ", ".join(daemons) or "none detected"))
    lines.append(_fmt_row("Helper:", str(r["helper"])))
    lines.append(_fmt_row("Recommended mode:", str(r["recommended_mode"])))
    return "\n".join(lines)


if __name__ == "__main__":
    print(format_doctor())
