"""
sensors/virtual.py — NEERKAAVAL Virtual Telemetry Layer
========================================================
Wraps raw simulation records from twin/runner.py:
  - Gaussian noise  ±0.02 m  (σ = 0.02)
  - 2% random sensor dropout  (returns None for dropped readings)
  - Exposes VirtualSensor class and get_sensor_dataframe() helper
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Any

# ── Sensor configuration ──────────────────────────────────────────────────────
NOISE_SIGMA_M   = 0.02      # Gaussian standard deviation (meters)
DROPOUT_PROB    = 0.02      # Probability any single reading is dropped
DEPTH_NODES     = ["Velachery_Main", "Pallikaranai", "Outfall_Gate"]
FLOW_FIELD      = "outfall_flow_cms"
TIME_FIELD      = "time_min"


class VirtualSensor:
    """
    Simulates an IoT depth sensor with Gaussian noise and random dropouts.

    Parameters
    ----------
    rng_seed : int | None
        Seed for reproducibility. None → random each run.
    """

    def __init__(self, rng_seed: Optional[int] = None):
        self._rng = np.random.default_rng(rng_seed)

    def read(self, raw_record: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply sensor imperfections to a single raw simulation record.

        Returns a new dict with:
          - time_min preserved exactly
          - depth fields noisy / None on dropout
          - outfall_flow_cms preserved (modelled as a flow meter, less noisy)
        """
        out: Dict[str, Any] = {TIME_FIELD: raw_record.get(TIME_FIELD, 0.0)}

        for node in DEPTH_NODES:
            if node not in raw_record:
                out[node] = None
                continue
            # 2% dropout
            if self._rng.random() < DROPOUT_PROB:
                out[node] = None
            else:
                noise = self._rng.normal(0.0, NOISE_SIGMA_M)
                out[node] = max(0.0, raw_record[node] + noise)

        # Flow meter: 1% noise, no dropout (ultrasonic — more reliable)
        if FLOW_FIELD in raw_record:
            flow_noise = self._rng.normal(0.0, NOISE_SIGMA_M * 0.5)
            out[FLOW_FIELD] = max(0.0, raw_record[FLOW_FIELD] + flow_noise)

        return out


def get_sensor_dataframe(
    raw_records: List[Dict[str, Any]],
    rng_seed: Optional[int] = 42,
) -> pd.DataFrame:
    """
    Convert raw simulation records → sensor-noisy Pandas DataFrame.

    Dropped readings become NaN (interpolated forward for dashboard display).
    """
    sensor = VirtualSensor(rng_seed=rng_seed)
    noisy = [sensor.read(rec) for rec in raw_records]
    df = pd.DataFrame(noisy)
    df.set_index(TIME_FIELD, inplace=True)

    # Forward-fill short dropouts (≤ 1 step) to avoid chart gaps
    # Note: use "index" (numeric) interpolation since index is time_min (float), not DatetimeIndex
    df = df.infer_objects(copy=False).interpolate(method="index", limit=2)

    return df


# ── Legacy function-based API (backward compatible) ────────────────────────────
_legacy_sensor = VirtualSensor(rng_seed=None)


def apply_sensor_noise(depth_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Backward-compatible wrapper used by old app.py."""
    return _legacy_sensor.read(depth_dict)