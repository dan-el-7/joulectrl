"""Sanity cross-check on calibration sweep numbers (PLAN §6 consumer, Agent B).

Validates ``fixtures/real/calibration_c2.json`` (and C1) against physical
plausibility rules so bad sweep data can never silently feed selection:

- one invariant kernel checksum across every row (work must be fixed);
- every row has positive runtime and non-negative energy, and energy is
  explicitly present (never ``None`` treated as zero);
- stock rows exist for every class and boost=0 sweep points carry an accepted
  cap at or below the verified machine clamp;
- scaling efficiency is in (0, 1] — parallel throughput can approach but never
  exceed workers x single-core throughput;
- lower caps must not yield *higher* median throughput beyond a tolerance
  (thermal/boost artifacts allowed a small margin), i.e. the perf/watt curve is
  monotone-ish per class.

The checker is read-only and side-effect free; it returns a report rather than
raising, so the dashboard can render failures as first-class states.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

C1_SCHEMA = "joulectrl.calibration_c1/1"
C2_SCHEMA = "joulectrl.calibration_c2/1"
C2E_SCHEMA = "joulectrl.calibration_c2_effective/1"
# Throughput may exceed a lower cap's by up to this fraction before we flag it.
MONOTONICITY_TOLERANCE = 0.10


@dataclass
class SweepCheckReport:
    ok: bool = True
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    classes: dict[str, dict] = field(default_factory=dict)

    def problem(self, message: str) -> None:
        self.ok = False
        self.problems.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)


def check_calibration_c1(doc: dict) -> SweepCheckReport:
    """Structural checks on the C1 fixture the sweep's efficiency divides by."""
    report = SweepCheckReport()
    if doc.get("schema") != C1_SCHEMA:
        report.problem(f"C1 schema {doc.get('schema')!r} != {C1_SCHEMA!r}")
        return report
    rows = doc.get("rows") or []
    if not rows:
        report.problem("C1 has no rows")
        return report
    checksums = {r["checksum"] for r in rows if r.get("checksum")}
    if len(checksums) != 1:
        report.problem(f"C1 checksum drift: {sorted(checksums)}")
    for row in rows:
        if not row.get("runtime_s") or row["runtime_s"] <= 0:
            report.problem(f"C1 row rep{row.get('rep')} has non-positive runtime")
        energy = row.get("package_energy_j")
        if energy is None or energy < 0:
            report.problem(f"C1 row rep{row.get('rep')} missing/invalid energy")
    return report


def check_calibration_c2(
    c2_doc: dict, c1_doc: Optional[dict] = None, *, cap_max_khz: int = 2_000_000
) -> SweepCheckReport:
    """Plausibility cross-check on the dense sweep fixture."""
    report = SweepCheckReport()
    if c2_doc.get("schema") != C2_SCHEMA:
        report.problem(f"C2 schema {c2_doc.get('schema')!r} != {C2_SCHEMA!r}")
        return report
    rows = c2_doc.get("rows") or []
    if not rows:
        report.problem("C2 has no rows")
        return report

    checksums = {r["checksum"] for r in rows if r.get("checksum")}
    if len(checksums) != 1:
        report.problem(f"C2 checksum drift: {sorted(checksums)}")

    classes = sorted({r["class"] for r in rows})
    for cname in classes:
        class_rows = [r for r in rows if r["class"] == cname]
        stock = [r for r in class_rows if r.get("requested_control", {}).get("boost") in (1, True)]
        sweep = [r for r in class_rows if r.get("requested_control", {}).get("boost") in (0, False)]
        if not stock:
            report.problem(f"{cname}: no stock row (scaling-efficiency baseline missing)")
        if not sweep:
            report.warn(f"{cname}: no swept control points recorded")
        for row in class_rows:
            if not row.get("runtime_s") or row["runtime_s"] <= 0:
                report.problem(f"{cname} rep{row.get('rep')}: non-positive runtime")
            energy = row.get("package_energy_j")
            if energy is None or energy < 0:
                report.problem(f"{cname} rep{row.get('rep')}: missing/invalid energy")
            accepted = (row.get("accepted_control") or {}).get("cap_khz")
            requested_boost = row.get("requested_control", {}).get("boost")
            if requested_boost in (0, False) and accepted is not None and accepted > cap_max_khz:
                report.problem(
                    f"{cname} rep{row.get('rep')}: accepted cap {accepted} kHz exceeds "
                    f"verified boost=0 clamp {cap_max_khz} kHz"
                )

        # Median throughput per cap, then monotone-ish check.
        by_cap: dict[int, list[float]] = {}
        for row in sweep:
            cap = (row.get("accepted_control") or {}).get("cap_khz")
            if cap is not None:
                by_cap.setdefault(cap, []).append(1.0 / row["runtime_s"])
        medians = {cap: statistics.median(throughputs) for cap, throughputs in sorted(by_cap.items())}
        caps_sorted = sorted(medians)
        for lower, higher in zip(caps_sorted, caps_sorted[1:]):
            if medians[higher] > medians[lower] * (1 + MONOTONICITY_TOLERANCE):
                report.warn(
                    f"{cname}: throughput at cap {higher} kHz exceeds cap {lower} kHz by "
                    f">{MONOTONICITY_TOLERANCE:.0%} (non-monotone curve)"
                )
        report.classes[cname] = {
            "n_stock": len(stock),
            "n_sweep": len(sweep),
            "median_throughput_per_cap": medians,
        }

    summary = c2_doc.get("summary") or {}
    for cname in classes:
        entry = summary.get(cname) or {}
        efficiency = entry.get("scaling_efficiency")
        if efficiency is None:
            report.problem(f"{cname}: summary missing scaling_efficiency")
        elif not (0 < efficiency <= 1):
            report.problem(
                f"{cname}: scaling efficiency {efficiency} outside (0, 1] — "
                "parallel throughput exceeded workers x single-core throughput"
            )

    if c1_doc is not None:
        c1_report = check_calibration_c1(c1_doc)
        report.problems.extend(c1_report.problems)
        report.warnings.extend(c1_report.warnings)
        report.ok = report.ok and c1_report.ok
        # Cross-check: C1 kernel params must match C2's per-worker work for the
        # efficiency number to be meaningful.
        c1_params = (c1_doc.get("params") or {})
        c2_params = (c2_doc.get("params") or {})
        c1_work = (c1_params.get("chunks"), c1_params.get("iters"))
        c2_work = (c2_params.get("chunks"), c2_params.get("iters"))
        if c1_work != c2_work and set(c1_work) != {None} and set(c2_work) != {None}:
            report.warn(
                f"C1 work {c1_work} != C2 work {c2_work}: scaling efficiency assumes "
                "equal per-worker work; verify the sweep uses 2x-per-worker as intended"
            )
    return report


def check_calibration_c2_effective(doc: dict) -> SweepCheckReport:
    """Check the C2-effective fixture (the real 8-point control space).

    Rows carry (class, control in {stock, base}, workers in {1, 4}, rep).
    Rules: runtime/energy present and positive per row; a single kernel
    checksum *per worker count* (w1 and w4 do different total work, so two
    checksums are expected — but never more); every class/control/workers
    cell has >= 2 reps; medians in summary match the rows; w4 runtime must
    be <= w1 runtime for the same class+control (parallelism cannot slow
    fixed work through 4x more cores beyond tolerance).
    """
    report = SweepCheckReport()
    if doc.get("schema") != C2E_SCHEMA:
        report.problem(f"C2-effective schema {doc.get('schema')!r} != {C2E_SCHEMA!r}")
        return report
    rows = doc.get("rows") or []
    if not rows:
        report.problem("C2-effective has no rows")
        return report

    checksums_by_workers: dict[int, set[str]] = {}
    for row in rows:
        if not row.get("runtime_s") or row["runtime_s"] <= 0:
            report.problem(f"{row.get('class')}/{row.get('control')}/w{row.get('workers')} rep{row.get('rep')}: non-positive runtime")
        energy = row.get("package_energy_j")
        if energy is None or energy < 0:
            report.problem(f"{row.get('class')}/{row.get('control')}/w{row.get('workers')} rep{row.get('rep')}: missing/invalid energy")
        checksums_by_workers.setdefault(int(row.get("workers", 0)), set()).add(row.get("kernel_checksum", ""))
    for workers, checksums in checksums_by_workers.items():
        if len(checksums) > 1:
            report.problem(f"kernel checksum drift at workers={workers}: {sorted(checksums)}")

    cells: dict[tuple, list[float]] = {}
    for row in rows:
        key = (row["class"], row["control"], int(row["workers"]))
        cells.setdefault(key, []).append(row["runtime_s"])
    for key, runtimes in sorted(cells.items()):
        if len(runtimes) < 2:
            report.warn(f"{key}: only {len(runtimes)} rep(s) — medians are fragile")
        cname, control, workers = key
        if workers > 1:
            single = cells.get((cname, control, 1))
            if single:
                if min(runtimes) > min(single) * (1 + MONOTONICITY_TOLERANCE):
                    report.problem(
                        f"{cname}/{control}: w{workers} slower than w1 (parallel slowdown beyond tolerance)"
                    )

    summary = doc.get("summary") or {}
    for (cname, control, workers), runtimes in sorted(cells.items()):
        cell_key = f"{control}_w{workers}"
        entry = (summary.get(cname) or {}).get(cell_key)
        if not entry:
            report.problem(f"summary missing {cname}.{cell_key}")
            continue
        import statistics as _stats

        row_median = _stats.median(runtimes)
        if abs(entry.get("median_runtime_s", row_median) - row_median) > 0.05:
            report.warn(
                f"{cname}.{cell_key}: summary median runtime {entry.get('median_runtime_s')} "
                f"!= row median {row_median:.4f}"
            )
        if int(entry.get("n", len(runtimes))) != len(runtimes):
            report.problem(f"{cname}.{cell_key}: summary n={entry.get('n')} != {len(runtimes)} rows")
    return report


def check_calibration_files(
    c2_path: str | Path, c1_path: str | Path | None = None
) -> Optional[SweepCheckReport]:
    """Load and check fixture files; return None when the C2 fixture is absent."""
    c2_path = Path(c2_path)
    if not c2_path.exists():
        return None
    doc = json.loads(c2_path.read_text())
    if doc.get("schema") == C2E_SCHEMA:
        return check_calibration_c2_effective(doc)
    c1_doc = None
    if c1_path is not None and Path(c1_path).exists():
        c1_doc = json.loads(Path(c1_path).read_text())
    return check_calibration_c2(doc, c1_doc)
