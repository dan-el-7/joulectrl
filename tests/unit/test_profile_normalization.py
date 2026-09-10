"""Unit tests verifying workload chunk normalization, config ID consistency,
stock baseline selection, and explanation grounding.
"""

from __future__ import annotations

import pytest
from core.models import Configuration, Selection
from api.engine import LiveEngine, make_config_id
from explain.facts import extract_explanation_facts


def test_make_config_id_deterministic():
    assert make_config_id(8, True, None, [0, 1, 2, 3]) == "cfg_8w_stock_0,1"
    assert make_config_id(4, False, 2000000, [0, 2, 4, 6]) == "cfg_4w_base_cap2000m_0,2"
    assert make_config_id(4, False, None, [0, 2, 4, 6]) == "cfg_4w_base_0,2"
    assert make_config_id(16, True, None, list(range(16))) == "cfg_16w_stock_0,1"


def test_profile_rows_chunk_normalization():
    """Verify that rows with variable chunk counts are scaled to invariant 65536 chunks."""
    engine = LiveEngine(bus=None, store_bridge_mod=None)
    cal = {
        "rows": [
            # 4-worker run with only 32768 chunks (half work)
            {
                "cpus": [0, 2, 4, 6],
                "boost": 0,
                "workers": 4,
                "freq_cap_khz": None,
                "chunks": 32768,
                "runtime_s": 10.78,
                "package_energy_j": 52.0,
            },
            # 8-worker run with full 65536 chunks
            {
                "cpus": [0, 1, 2, 3, 4, 5, 6, 7],
                "boost": 0,
                "workers": 8,
                "freq_cap_khz": None,
                "chunks": 65536,
                "runtime_s": 10.80,
                "package_energy_j": 75.9,
            },
        ]
    }

    rows = engine._profile_rows(cal, [], None, "fixed_compute")
    row_map = {tuple(r["cpus"]): r for r in rows}

    # 4w row must be scaled by 65536 / 32768 = 2.0
    r4 = row_map[(0, 2, 4, 6)]
    assert r4["median_runtime_s"] == pytest.approx(10.78 * 2.0, rel=1e-3)
    assert r4["median_energy_j"] == pytest.approx(52.0 * 2.0, rel=1e-3)

    # 8w row with 65536 chunks remains scale = 1.0
    r8 = row_map[(0, 1, 2, 3, 4, 5, 6, 7)]
    assert r8["median_runtime_s"] == pytest.approx(10.80, rel=1e-3)
    assert r8["median_energy_j"] == pytest.approx(75.9, rel=1e-3)


def test_select_guarantees_stock_baseline():
    """Verify that _select picks a stock boost configuration as baseline."""
    engine = LiveEngine(bus=None, store_bridge_mod=None)
    rows = [
        {
            "cpus": [0, 2, 4, 6],
            "boost": 0,
            "workers": 4,
            "freq_cap_khz": None,
            "median_runtime_s": 21.5,
            "median_energy_j": 104.0,
            "guarded_runtime_s": 22.5,
            "n": 1,
            "sources": ["calibration"],
        },
        {
            "cpus": [0, 1, 2, 3, 4, 5, 6, 7],
            "boost": 0,
            "workers": 8,
            "freq_cap_khz": None,
            "median_runtime_s": 10.8,
            "median_energy_j": 75.9,
            "guarded_runtime_s": 11.4,
            "n": 1,
            "sources": ["calibration"],
        },
        {
            "cpus": [0, 1, 2, 3, 4, 5, 6, 7],
            "boost": 1,
            "workers": 8,
            "freq_cap_khz": None,
            "median_runtime_s": 5.6,
            "median_energy_j": 158.0,
            "guarded_runtime_s": 5.9,
            "n": 1,
            "sources": ["calibration"],
        },
    ]

    sel = engine._select(rows, objective="deadline", budget=23.0, preference={}, exp_id="exp_test")
    # Baseline must be the stock configuration (5.6s, boost=1)
    assert sel.baseline_config_id == "cfg_8w_stock_0,1"
    # Selected candidate meeting 23s budget with lowest energy should be 8w base (75.9 J), NOT 4w base (104 J)
    assert sel.selected_config_id == "cfg_8w_base_0,1"


def test_facts_grounded_selected_config_id():
    """Verify facts extractor uses real configuration ID rather than fallback 'config'."""
    cfg = Configuration(id="config", layout="B", worker_count=8, boost=False)
    sel = Selection(
        experiment_id="exp-123",
        objective_mode="deadline",
        status="selected",
        status_message="OK",
        deadline_s=23.0,
        selected_config_id="cfg_8w_base_0,1",
        baseline_config_id="cfg_8w_stock_0,1",
        selected_configuration=cfg,
        selected_median_energy_j=75.9,
        selected_median_runtime_s=10.8,
        selected_guarded_runtime_s=11.4,
        baseline_median_energy_j=158.0,
        baseline_median_runtime_s=5.6,
        energy_reduction_pct=52.0,
        runtime_increase_pct=92.8,
    )

    facts = extract_explanation_facts(sel)
    assert facts["selected_config"]["id"] == "cfg_8w_base_0,1"
    assert facts["baseline_config"]["id"] == "cfg_8w_stock_0,1"
