"""Optimizer behavior in the demo laptop's real 2-point control space.

Grounded in fixtures/real/calibration_c2.json (commit b2489b2): under boost=0
the machine ignores sub-base caps, so the effective control space per class is
two points — stock (boost=1) and capped (boost=0). These tests prove the
deterministic selector handles that coarse space honestly: no invented points,
edge states correct, energy-optimal choice real.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.models import ConfigSummary, Configuration, Profile
from core.optimizer import compute_pareto_frontier, select_deadline

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "real" / "calibration_c2.json"


def real_profile() -> Profile:
    """Build a Profile whose config summaries mirror the real C2 measurements
    (fast class, layout A shape): stock 4.24s/106.0J vs capped 10.75s/81.5J."""
    stock = Configuration(id="cfg_fast_stock", layout="A", worker_count=4, boost=True)
    capped = Configuration(id="cfg_fast_capped", layout="A", worker_count=4, boost=False)
    return Profile(
        experiment_id="exp-c2-real",
        workload_name="fixed_compute",
        baseline_config_id="cfg_fast_stock",
        configurations={
            "cfg_fast_stock": ConfigSummary(
                config_id="cfg_fast_stock",
                configuration=stock,
                runtime_samples=[4.24],
                energy_samples=[106.0],
                median_runtime_s=4.24,
                median_energy_j=106.0,
            ),
            "cfg_fast_capped": ConfigSummary(
                config_id="cfg_fast_capped",
                configuration=capped,
                runtime_samples=[10.75],
                energy_samples=[81.5],
                median_runtime_s=10.75,
                median_energy_j=81.5,
            ),
        },
    )


@pytest.mark.skipif(not FIXTURE.exists(), reason="real C2 fixture not present")
def test_real_c2_fixture_matches_test_profile_shape():
    """Guard: the hardcoded profile above must track the real fixture numbers."""
    doc = json.loads(FIXTURE.read_text())
    fast_stock = doc["summary"]["fast"]["stock"]
    assert fast_stock["runtime_s"] == pytest.approx(4.24, abs=0.1)
    assert fast_stock["energy_j"] == pytest.approx(106.0, abs=1.0)
    # All capped rows cluster at one runtime — the 2-point regime.
    capped_rows = [
        r for r in doc["rows"]
        if r["class"] == "fast" and r["requested_control"]["boost"] in (0, False)
    ]
    # All capped runtimes within 0.2s of each other — one effective regime.
    runtimes = [r["runtime_s"] for r in capped_rows]
    assert max(runtimes) - min(runtimes) < 0.2
    energies = [r["package_energy_j"] for r in capped_rows]
    assert pytest.approx(sum(energies) / len(energies), abs=2.0) == 81.5


def test_deadline_tight_keeps_stock():
    selection = select_deadline(list(real_profile().configurations.values()), deadline_s=5.0)
    assert selection.selected_config_id == "cfg_fast_stock"


def test_deadline_loose_picks_energy_optimal_capped():
    selection = select_deadline(list(real_profile().configurations.values()), deadline_s=15.0)
    assert selection.selected_config_id == "cfg_fast_capped"


def test_no_feasible_point_when_deadline_below_everything():
    selection = select_deadline(list(real_profile().configurations.values()), deadline_s=3.0)
    assert selection.selected_config_id is None
    assert selection.status in ("no_feasible_point", "infeasible")


def test_pareto_frontier_is_both_points_in_2_point_space():
    frontier = compute_pareto_frontier(list(real_profile().configurations.values()))
    # stock is fastest, capped is lowest-energy: both are on the frontier.
    assert {c.config_id for c in frontier} == {"cfg_fast_stock", "cfg_fast_capped"}
