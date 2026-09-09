"""Unit tests for energy/synthetic.py synthetic energy backend."""

import pytest
from energy.synthetic import DEFAULT_MAX_ENERGY_RANGE_UJ, SyntheticEnergyBackend


def test_normal_accumulation_and_delta():
    backend = SyntheticEnergyBackend(initial_uj=10_000_000)
    uj1, t1 = backend.read()
    assert uj1 == 10_000_000

    backend.advance_j(5.0)  # 5 Joules = 5,000,000 uJ
    uj2, t2 = backend.read()
    assert uj2 == 15_000_000

    delta_uj = backend.compute_delta_uj(uj1, uj2)
    assert delta_uj == 5_000_000

    delta_j = backend.compute_delta_j(uj1, uj2)
    assert delta_j == pytest.approx(5.0)


def test_modulo_wrap_handling():
    backend = SyntheticEnergyBackend()
    # Trigger wrap near boundary: 100,000 uJ before wrap, advance 500,000 uJ
    start_uj, end_uj = backend.trigger_wrap(margin_uj=100_000, step_uj=500_000)
    assert start_uj == DEFAULT_MAX_ENERGY_RANGE_UJ - 100_000
    assert end_uj == 400_000

    # Wrap delta must equal exactly 500,000 uJ (0.5 J)
    delta_uj = backend.compute_delta_uj(start_uj, end_uj)
    assert delta_uj == 500_000

    delta_j = backend.compute_delta_j(start_uj, end_uj)
    assert delta_j == pytest.approx(0.5)


def test_unavailability_never_reports_zero():
    backend = SyntheticEnergyBackend(initial_uj=5_000_000)
    uj1 = backend.read_energy_uj()
    assert uj1 == 5_000_000

    # Simulate counter going offline / read error
    backend.set_available(False)
    uj2 = backend.read_energy_uj()
    assert uj2 is None
    assert uj2 != 0  # Invariant: never report missing energy as zero!

    # Delta with missing sample is None
    delta_uj = backend.compute_delta_uj(uj1, uj2)
    assert delta_uj is None

    delta_j = backend.compute_delta_j(uj1, uj2)
    assert delta_j is None


def test_scripted_power_profile():
    backend = SyntheticEnergyBackend()
    backend.setup_standard_watch_profile()

    # Step 1: In initial idle segment (10 W)
    uj_0, p_0, t_0 = backend.step(1.0)
    assert p_0 == pytest.approx(10.0)
    assert t_0 == pytest.approx(1.0)

    # Fast forward through initial idle (remaining 29s)
    for _ in range(29):
        backend.step(1.0)

    # Step into task_active_1 (50 W)
    uj_active, p_active, t_active = backend.step(1.0)
    assert p_active == pytest.approx(50.0)
    assert t_active == pytest.approx(31.0)
