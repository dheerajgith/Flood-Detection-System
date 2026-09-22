"""
control/metrics.py — NEERKAAVAL Hydraulic Flood Metrics
=========================================================
Computes civil engineering performance indicators comparing
Control OFF (passive drainage) vs Control ON (active gate management).

Critical flooding threshold: depth > 1.2 m at Velachery_Main
(design bank-full depth from velachery.inp junction specification)
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from typing import Dict, Any

# ── Configuration ─────────────────────────────────────────────────────────────
FLOOD_THRESHOLD_M = 1.2     # metres — Velachery_Main design bank-full depth
PRIMARY_NODE      = "Velachery_Main"
TIME_FIELD        = "time_min"
REPORT_STEP_MIN   = 5       # minutes between records


def compute_metrics(
    df_off: pd.DataFrame,
    df_on:  pd.DataFrame,
    node:   str = PRIMARY_NODE,
    threshold_m: float = FLOOD_THRESHOLD_M,
) -> Dict[str, Any]:
    """
    Compute hydraulic flood metrics for Control OFF and Control ON scenarios.

    Parameters
    ----------
    df_off : pd.DataFrame
        Sensor DataFrame for Control OFF (index = time_min).
    df_on : pd.DataFrame
        Sensor DataFrame for Control ON (index = time_min).
    node : str
        Junction node to evaluate (default: Velachery_Main).
    threshold_m : float
        Flood depth threshold in metres (default: 1.2 m).

    Returns
    -------
    dict with keys:
        peak_depth_off, peak_depth_on, peak_depth_reduction,
        flood_hours_off, flood_hours_on, flood_hours_avoided,
        flood_volume_index_off, flood_volume_index_on,
        pct_volume_mitigated, threshold_m, node
    """
    dt_hours = REPORT_STEP_MIN / 60.0

    # ── Extract depth series ──────────────────────────────────────────────────
    if node in df_off.columns:
        depth_off = df_off[node].fillna(0.0).to_numpy()
    else:
        depth_off = np.zeros(len(df_off))

    if node in df_on.columns:
        depth_on = df_on[node].fillna(0.0).to_numpy()
    else:
        depth_on = np.zeros(len(df_on))

    # ── a) Peak Water Depth (m) ───────────────────────────────────────────────
    peak_off = float(np.max(depth_off)) if len(depth_off) > 0 else 0.0
    peak_on  = float(np.max(depth_on))  if len(depth_on)  > 0 else 0.0
    peak_reduction = max(0.0, peak_off - peak_on)

    # ── b) Flooded-Node-Hours ─────────────────────────────────────────────────
    # Total duration (hours) where depth > threshold
    flood_steps_off = int(np.sum(depth_off > threshold_m))
    flood_steps_on  = int(np.sum(depth_on  > threshold_m))
    flood_hours_off = round(flood_steps_off * dt_hours, 2)
    flood_hours_on  = round(flood_steps_on  * dt_hours, 2)
    flood_hours_avoided = max(0.0, flood_hours_off - flood_hours_on)

    # ── c) Total Flood Overflow Volume Index ──────────────────────────────────
    # Trapezoid integral of (depth - threshold) × dt when depth > threshold
    # Units: m·hours  (volume-proportional index; not absolute volume without
    # cross-section geometry, which requires full SWMM output)
    excess_off = np.maximum(depth_off - threshold_m, 0.0)
    excess_on  = np.maximum(depth_on  - threshold_m, 0.0)
    _trapz = getattr(np, "trapezoid", np.trapz)  # numpy >= 2.0 compat
    vol_idx_off = float(_trapz(excess_off, dx=dt_hours))
    vol_idx_on  = float(_trapz(excess_on,  dx=dt_hours))

    # ── d) % Flood Volume Mitigated ───────────────────────────────────────────
    if vol_idx_off > 0:
        pct_mitigated = round((vol_idx_off - vol_idx_on) / vol_idx_off * 100, 1)
    else:
        pct_mitigated = 100.0 if vol_idx_on == 0 else 0.0

    return {
        # Scenario peaks
        "peak_depth_off":         round(peak_off, 3),
        "peak_depth_on":          round(peak_on, 3),
        "peak_depth_reduction":   round(peak_reduction, 3),
        # Flooded-Node-Hours
        "flood_hours_off":        flood_hours_off,
        "flood_hours_on":         flood_hours_on,
        "flood_hours_avoided":    round(flood_hours_avoided, 2),
        # Volume index
        "flood_volume_index_off": round(vol_idx_off, 4),
        "flood_volume_index_on":  round(vol_idx_on,  4),
        "pct_volume_mitigated":   pct_mitigated,
        # Reference
        "threshold_m":            threshold_m,
        "node":                   node,
    }
