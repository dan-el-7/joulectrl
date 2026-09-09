import pytest
from unittest.mock import patch
from core.clock_checker import check_clock_holdable, probe_hardware_clock_caps


def test_probe_hardware_clock_caps():
    caps = probe_hardware_clock_caps(force_refresh=True)
    assert isinstance(caps, dict)
    assert "hw_min_khz" in caps
    assert "hw_max_khz" in caps
    assert "base_khz" in caps
    assert caps["hw_max_khz"] >= caps["hw_min_khz"]


def test_stock_config_holdable():
    result = check_clock_holdable(None, boost=True)
    assert result["holdable"] is True
    assert result["requires_passive_mode"] is False
    assert result["clamped"] is False
    assert result["adapted_control"]["boost"] is True


def test_high_clock_boost_disabled_amd_adaptation():
    with patch("core.clock_checker.probe_hardware_clock_caps") as mock_probe:
        mock_probe.return_value = {
            "is_linux": True,
            "driver": "amd-pstate-epp",
            "has_amd_pstate": True,
            "amd_pstate_status": "active",
            "hw_min_khz": 600000,
            "hw_max_khz": 5090000,
            "base_khz": 2000000,
            "has_boost_toggle": True,
        }
        res = check_clock_holdable(4000000, boost=False, cpu_affinity=[0, 2, 4, 6])
        assert res["holdable"] is True
        assert res["requires_passive_mode"] is True
        assert res["adapted_control"]["pstate_mode"] == "passive"
        assert res["adapted_control"]["boost"] is True
        assert res["adapted_control"]["policy_freq_caps_khz"]["policy0"] == 4000000


def test_low_clock_within_base_frequency():
    with patch("core.clock_checker.probe_hardware_clock_caps") as mock_probe:
        mock_probe.return_value = {
            "is_linux": True,
            "driver": "amd-pstate-epp",
            "has_amd_pstate": True,
            "amd_pstate_status": "active",
            "hw_min_khz": 600000,
            "hw_max_khz": 5090000,
            "base_khz": 2000000,
            "has_boost_toggle": True,
        }
        res = check_clock_holdable(1800000, boost=False, cpu_affinity=[1, 3])
        assert res["holdable"] is True
        assert res["requires_passive_mode"] is False
        assert res["adapted_control"]["boost"] is False
        assert res["adapted_control"]["policy_freq_caps_khz"]["policy1"] == 1800000


def test_exceeding_max_clamped():
    with patch("core.clock_checker.probe_hardware_clock_caps") as mock_probe:
        mock_probe.return_value = {
            "is_linux": True,
            "driver": "intel_pstate",
            "has_amd_pstate": False,
            "amd_pstate_status": None,
            "hw_min_khz": 800000,
            "hw_max_khz": 4500000,
            "base_khz": 2400000,
            "has_boost_toggle": True,
        }
        res = check_clock_holdable(6000000, boost=True, cpu_affinity=[0])
        assert res["clamped"] is True
        assert res["effective_khz"] == 4500000
        assert res["adapted_control"]["policy_freq_caps_khz"]["policy0"] == 4500000
