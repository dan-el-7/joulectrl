"""Tests for the watch-mode suggested-budget computation (§6b)."""

from __future__ import annotations

import pytest

from core.budget import suggest_budget
from core.watch import WatchSegment


def seg(start, end, poll=1.0):
    return WatchSegment(
        start_ts=start,
        end_ts=end,
        start_energy_uj=1_000_000,
        end_energy_uj=1_100_000,
        energy_range_uj=65_500_000,
        baseline_w=8.0,
        spread_w=0.5,
        poll_interval_s=poll,
    )


def test_canonical_api_example_matches_frozen_contract():
    # API.md: duration 47.0 s -> suggested_budget_s 49.35
    segment = seg(0.0, 47.0, poll=0.35)
    assert suggest_budget([segment]) == pytest.approx(49.35, abs=0.01)


def test_no_segments_returns_none_never_a_guess():
    assert suggest_budget([]) is None


def test_zero_length_segments_are_ignored():
    assert suggest_budget([seg(5.0, 5.0)]) is None


def test_multi_segment_uses_median_not_max():
    segments = [seg(0, 40), seg(100, 141), seg(200, 300)]  # one 100s outlier
    budget = suggest_budget(segments, slack=0.0)
    # median of [40, 41, 100] = 41
    assert budget == pytest.approx(41.0, abs=0.01)


def test_budget_is_rounded_and_positive():
    budget = suggest_budget([seg(0, 33.333)])
    assert budget > 33.0
    assert budget == round(budget, 2)


def test_energy_unavailability_does_not_block_suggestion():
    segment = seg(0, 50)
    segment.energy_available = False
    segment.start_energy_uj = None
    segment.end_energy_uj = None
    assert suggest_budget([segment]) is not None
