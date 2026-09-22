"""
tests/test_golden.py — NEERKAAVAL Golden Test Suite
====================================================
Validates that the physics engine produces physically correct outputs
and that hydraulic metrics meet the "Control ON always beats Control OFF"
invariants required for the digital twin demonstration.
"""

import pytest
from twin.runner import run_swmm_simulation, FLOOD_THRESHOLD
from sensors.virtual import get_sensor_dataframe, VirtualSensor
from control.metrics import compute_metrics


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def sim_off():
    return run_swmm_simulation(control_on=False)

@pytest.fixture(scope="module")
def sim_on():
    return run_swmm_simulation(control_on=True)

@pytest.fixture(scope="module")
def df_off(sim_off):
    return get_sensor_dataframe(sim_off, rng_seed=42)

@pytest.fixture(scope="module")
def df_on(sim_on):
    return get_sensor_dataframe(sim_on, rng_seed=42)

@pytest.fixture(scope="module")
def metrics_result(df_off, df_on):
    return compute_metrics(df_off, df_on)


# ── Runner tests ──────────────────────────────────────────────────────────────

class TestRunner:
    def test_returns_non_empty_list(self, sim_off):
        assert isinstance(sim_off, list)
        assert len(sim_off) > 0

    def test_all_required_keys_present(self, sim_off):
        required = {"time_min", "Velachery_Main", "Pallikaranai", "Outfall_Gate"}
        for rec in sim_off:
            assert required.issubset(rec.keys()), f"Missing keys in record: {rec}"

    def test_time_is_monotonically_increasing(self, sim_off):
        times = [r["time_min"] for r in sim_off]
        for a, b in zip(times, times[1:]):
            assert b > a, f"Non-monotonic times: {a} → {b}"

    def test_depths_non_negative(self, sim_off):
        for rec in sim_off:
            for node in ("Velachery_Main", "Pallikaranai", "Outfall_Gate"):
                assert rec[node] >= 0.0, f"Negative depth at {node}: {rec[node]}"

    def test_control_off_exceeds_flood_threshold(self, sim_off):
        """Control OFF must overflow — otherwise the twin has no demonstration value."""
        depths = [r["Velachery_Main"] for r in sim_off]
        assert max(depths) > FLOOD_THRESHOLD, (
            f"Control OFF peak {max(depths):.3f}m must exceed threshold {FLOOD_THRESHOLD}m"
        )

    def test_control_on_stays_below_threshold(self, sim_on):
        """Control ON must keep Velachery_Main below flood threshold."""
        depths = [r["Velachery_Main"] for r in sim_on]
        assert max(depths) < FLOOD_THRESHOLD, (
            f"Control ON peak {max(depths):.3f}m must be below threshold {FLOOD_THRESHOLD}m"
        )

    def test_control_on_peak_lower_than_off(self, sim_off, sim_on):
        peak_off = max(r["Velachery_Main"] for r in sim_off)
        peak_on  = max(r["Velachery_Main"] for r in sim_on)
        assert peak_on < peak_off, (
            f"Control ON peak ({peak_on:.3f}m) must be less than OFF ({peak_off:.3f}m)"
        )


# ── Sensor layer tests ────────────────────────────────────────────────────────

class TestVirtualSensor:
    def test_dataframe_has_correct_columns(self, df_off):
        expected = {"Velachery_Main", "Pallikaranai", "Outfall_Gate"}
        assert expected.issubset(df_off.columns)

    def test_no_negative_depths_after_noise(self, df_off):
        for col in ("Velachery_Main", "Pallikaranai", "Outfall_Gate"):
            assert (df_off[col].dropna() >= 0).all(), f"Negative values in {col}"

    def test_noise_within_range(self, sim_off):
        """Verify Gaussian noise stays within ±5σ (virtually certain)."""
        sensor = VirtualSensor(rng_seed=0)
        for raw in sim_off:
            noisy = sensor.read(raw)
            for node in ("Velachery_Main", "Pallikaranai", "Outfall_Gate"):
                if noisy.get(node) is not None:
                    diff = abs(noisy[node] - raw[node])
                    assert diff < 0.15, f"Noise too large at {node}: {diff:.4f}m"

    def test_dropout_returns_none(self):
        """Force rng to always dropout and verify None is returned."""
        import numpy as np
        sensor = VirtualSensor(rng_seed=0)
        # Patch rng to always return < 0.02
        sensor._rng = type('FakeRNG', (), {'random': lambda s: 0.01, 'normal': lambda s,a,b: 0.0})()
        raw = {"time_min": 0, "Velachery_Main": 1.0, "Pallikaranai": 0.5, "Outfall_Gate": 0.3}
        result = sensor.read(raw)
        assert result.get("Velachery_Main") is None


# ── Metrics tests ─────────────────────────────────────────────────────────────

class TestMetrics:
    def test_returns_all_required_keys(self, metrics_result):
        required = {
            "peak_depth_off", "peak_depth_on", "peak_depth_reduction",
            "flood_hours_off", "flood_hours_on", "flood_hours_avoided",
            "flood_volume_index_off", "flood_volume_index_on", "pct_volume_mitigated",
        }
        assert required.issubset(metrics_result.keys())

    def test_peak_depth_reduction_positive(self, metrics_result):
        assert metrics_result["peak_depth_reduction"] >= 0.0

    def test_flood_hours_avoided_positive(self, metrics_result):
        assert metrics_result["flood_hours_avoided"] >= 0.0

    def test_pct_volume_mitigated_in_range(self, metrics_result):
        pct = metrics_result["pct_volume_mitigated"]
        assert 0.0 <= pct <= 100.0, f"% mitigated out of range: {pct}"

    def test_control_on_fewer_flood_hours(self, metrics_result):
        assert metrics_result["flood_hours_on"] <= metrics_result["flood_hours_off"]

    def test_control_on_lower_volume_index(self, metrics_result):
        assert metrics_result["flood_volume_index_on"] <= metrics_result["flood_volume_index_off"]
