"""Tests for the calibration-sweep sanity cross-check (PLAN §6 consumer)."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from core.sweep_check import (
    C1_SCHEMA,
    C2_SCHEMA,
    check_calibration_c1,
    check_calibration_c2,
    check_calibration_files,
)

C1_DOC = {
    "schema": C1_SCHEMA,
    "params": {"chunks": 16384, "iters": 200000, "reps": 5, "workers": 1},
    "rows": [
        {
            "class": "fast",
            "rep": rep,
            "runtime_s": 8.5,
            "package_energy_j": 75.0,
            "checksum": "0xc2493c07d6b29c85",
        }
        for rep in range(1, 6)
    ],
    "summary": {"fast": {"median_chunks_per_s": 1935}},
}


def c2_row(cls, boost, cap, runtime_s, energy_j=100.0, rep=1):
    return {
        "class": cls,
        "layout": "C2",
        "rep": rep,
        "workers": 4,
        "runtime_s": runtime_s,
        "package_energy_j": energy_j,
        "checksum": "0x4f59b8763583e750",
        "requested_control": {"boost": boost, "cap_khz": cap},
        "accepted_control": {"boost": bool(boost), "cap_khz": cap},
    }


def c2_doc(rows):
    return {
        "schema": C2_SCHEMA,
        "params": {"chunks": 32768, "iters": 200000, "workers": 4, "n_cap_points": 3},
        "rows": rows,
        "summary": {
            cls: {
                "stock": {"runtime_s": 10.0, "energy_j": 100.0},
                "scaling_efficiency": 0.85,
                "n_points": 3,
            }
            for cls in {r["class"] for r in rows}
        },
    }


def good_rows():
    return [
    c2_row("fast", 1, None, 10.0),
    c2_row("fast", 0, 2_000_000, 10.5),
    c2_row("fast", 0, 1_400_000, 14.0),
    c2_row("fast", 0, 700_000, 26.0),
]


def test_good_sweep_passes():
    report = check_calibration_c2(c2_doc(good_rows()), C1_DOC)
    assert report.ok, report.problems
    assert report.classes["fast"]["n_stock"] == 1
    assert report.classes["fast"]["n_sweep"] == 3


def test_checksum_drift_is_a_problem():
    rows = copy.deepcopy(good_rows())
    rows[2]["checksum"] = "0xdeadbeef"
    report = check_calibration_c2(c2_doc(rows))
    assert not report.ok
    assert any("checksum drift" in p for p in report.problems)


def test_missing_energy_is_a_problem_never_zero():
    rows = copy.deepcopy(good_rows())
    rows[1]["package_energy_j"] = None
    report = check_calibration_c2(c2_doc(rows))
    assert not report.ok
    assert any("missing/invalid energy" in p for p in report.problems)


def test_superlinear_scaling_efficiency_is_rejected():
    doc = c2_doc(good_rows())
    doc["summary"]["fast"]["scaling_efficiency"] = 1.4
    report = check_calibration_c2(doc)
    assert not report.ok
    assert any("scaling efficiency" in p for p in report.problems)


def test_accepted_cap_above_verified_clamp_is_rejected():
    rows = copy.deepcopy(good_rows())
    rows[1]["accepted_control"]["cap_khz"] = 5_000_000
    report = check_calibration_c2(c2_doc(rows))
    assert not report.ok
    assert any("clamp" in p for p in report.problems)


def test_higher_cap_much_faster_than_lower_cap_warns_nonmonotone():
    rows = [
        c2_row("fast", 1, None, 10.0),
        c2_row("fast", 0, 700_000, 40.0),
        c2_row("fast", 0, 1_400_000, 10.0),  # 2x cap but 4x throughput -> warn
        c2_row("fast", 0, 2_000_000, 9.5),
    ]
    report = check_calibration_c2(c2_doc(rows))
    assert report.ok  # a warning, not a failure
    assert any("non-monotone" in w for w in report.warnings)


def test_c1_cross_check_flags_work_mismatch_as_warning():
    report = check_calibration_c2(c2_doc(good_rows()), C1_DOC)
    assert report.ok
    assert any("per-worker work" in w for w in report.warnings)


def test_missing_stock_row_is_a_problem():
    rows = [r for r in good_rows() if r["requested_control"]["boost"] != 1]
    report = check_calibration_c2(c2_doc(rows))
    assert not report.ok
    assert any("no stock row" in p for p in report.problems)


def test_check_files_returns_none_when_c2_absent(tmp_path: Path):
    assert check_calibration_files(tmp_path / "nope.json", tmp_path / "c1.json") is None


def test_check_files_roundtrip(tmp_path: Path):
    (tmp_path / "c2.json").write_text(json.dumps(c2_doc(good_rows())))
    (tmp_path / "c1.json").write_text(json.dumps(C1_DOC))
    report = check_calibration_files(tmp_path / "c2.json", tmp_path / "c1.json")
    assert report is not None and report.ok, report.problems


# ---------------------------------------------------------------------------
# C2-effective (real 8-point control space) checks
# ---------------------------------------------------------------------------

from core.sweep_check import C2E_SCHEMA, check_calibration_c2_effective


def c2e_row(cls, control, workers, runtime_s, energy_j=80.0, rep=1, checksum=None):
    return {
        "class": cls, "control": control, "workers": workers, "rep": rep,
        "runtime_s": runtime_s, "package_energy_j": energy_j,
        "kernel_checksum": checksum or ("0xc2" if workers == 1 else "0xc4"),
        "boost": control != "base", "cpus": [0], "chunks": 16384, "boot_id": "b",
    }


def c2e_doc(rows, summary=None):
    return {"schema": C2E_SCHEMA, "rows": rows, "summary": summary or {}}


def c2e_summary(rows):
    import statistics as st
    summary = {}
    for row in rows:
        key = (row["class"], row["control"], row["workers"])
        summary.setdefault(key, []).append(row["runtime_s"])
    out = {}
    for (cname, control, workers), runtimes in summary.items():
        out.setdefault(cname, {})[f"{control}_w{workers}"] = {
            "median_runtime_s": st.median(runtimes), "n": len(runtimes),
        }
    return out


GOOD_C2E = [
    c2e_row("fast", "stock", 1, 8.5, rep=r) for r in (1, 2, 3)
] + [
    c2e_row("fast", "stock", 4, 4.2, rep=r) for r in (1, 2, 3)
] + [
    c2e_row("fast", "base", 4, 10.8, rep=r) for r in (1, 2, 3)
]


def test_c2e_good_passes_with_two_worker_checksums():
    report = check_calibration_c2_effective(c2e_doc(GOOD_C2E, c2e_summary(GOOD_C2E)))
    assert report.ok, report.problems


def test_c2e_checksum_drift_within_same_worker_count_fails():
    rows = [dict(r) for r in GOOD_C2E]
    rows[0]["kernel_checksum"] = "0xdead"
    report = check_calibration_c2_effective(c2e_doc(rows))
    assert not report.ok
    assert any("checksum drift" in p for p in report.problems)


def test_c2e_parallel_slowdown_is_a_problem():
    rows = [
        c2e_row("fast", "stock", 1, 8.5, rep=1),
        c2e_row("fast", "stock", 4, 20.0, rep=1),  # w4 slower than w1 -> problem
    ]
    report = check_calibration_c2_effective(c2e_doc(rows))
    assert not report.ok
    assert any("parallel slowdown" in p for p in report.problems)


def test_c2e_missing_energy_is_a_problem():
    rows = [dict(r) for r in GOOD_C2E]
    rows[1]["package_energy_j"] = None
    report = check_calibration_c2_effective(c2e_doc(rows, c2e_summary(rows)))
    assert not report.ok
    assert any("missing/invalid energy" in p for p in report.problems)


def test_c2e_files_autodetect_by_schema(tmp_path):
    (tmp_path / "c2e.json").write_text(json.dumps(c2e_doc(GOOD_C2E, c2e_summary(GOOD_C2E))))
    report = check_calibration_files(tmp_path / "c2e.json")
    assert report is not None and report.ok, report.problems
