"""Tests for energy/base.py — wrap math, reset detection, never-zero."""

import pytest

from energy.base import (
    EnergyAccumulator, PowercapBackend, Reading,
    EnergyResetError, EnergyUnavailableError,
)


class FakeBackend:
    def __init__(self, values, max_range=1_000_000):
        self.values = list(values)
        self.name = "fake"
        self._max = max_range

    def read_uj(self):
        return self.values.pop(0) if self.values else None

    def max_range_uj(self):
        return self._max


def test_single_wrap():
    # e1=990k, e2=10k with R=1e6 -> delta = 20k
    b = FakeBackend([990_000, 10_000])
    acc = EnergyAccumulator(b)
    d = acc.delta(Reading(0.0, 990_000), Reading(2.0, 10_000))
    assert d.uj == 20_000
    assert d.joules == pytest.approx(0.02)


def test_no_wrap():
    b = FakeBackend([100_000, 300_000])
    acc = EnergyAccumulator(b)
    d = acc.delta(Reading(0.0, 100_000), Reading(1.0, 300_000))
    assert d.uj == 200_000


def test_reset_detected():
    # delta exceeds plausible power: 200 W * 1 s = 200 J = 2e8 uJ; 5e8 > that
    b = FakeBackend([0, 500_000_000], max_range=1_000_000_000)
    acc = EnergyAccumulator(b, plausible_max_watts=200.0)
    with pytest.raises(EnergyResetError):
        acc.delta(Reading(0.0, 0), Reading(1.0, 500_000_000))


def test_unavailable_never_zero():
    b = FakeBackend([])
    acc = EnergyAccumulator(b)
    with pytest.raises(EnergyUnavailableError):
        acc.begin()


def test_multiple_incremental_reads():
    b = FakeBackend([100_000, 300_000, 500_000, 700_000])
    acc = EnergyAccumulator(b)
    total = 0
    prev = Reading(0.0, b.read_uj())
    for t in (1.0, 2.0, 3.0):
        cur = Reading(t, b.read_uj())
        total += acc.delta(prev, cur).uj
        prev = cur
    assert total == 600_000


def test_negative_without_range_is_reset():
    b = FakeBackend([500_000, 100_000], max_range=None)
    acc = EnergyAccumulator(b)
    with pytest.raises(EnergyResetError):
        acc.delta(Reading(0.0, 500_000), Reading(1.0, 100_000))


def test_powercap_backend_missing_file():
    b = PowercapBackend("/nonexistent/energy_uj")
    assert b.read_uj() is None
    assert b.max_range_uj() is None


def test_powercap_backend_reads(tmp_path):
    d = tmp_path / "domain"
    d.mkdir()
    (d / "energy_uj").write_text("123456\n")
    (d / "max_energy_range_uj").write_text("65532610987\n")
    b = PowercapBackend(str(d / "energy_uj"))
    assert b.read_uj() == 123456
    assert b.max_range_uj() == 65532610987
