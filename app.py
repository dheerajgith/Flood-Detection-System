"""
app.py — NEERKAAVAL Digital Twin Dashboard
==========================================
Physics-backed stormwater digital twin for the Velachery catchment, Chennai.
Demonstrates Control OFF (passive drainage failure) vs Control ON (active gate management).

Run with:
    streamlit run app.py
"""

from __future__ import annotations
import os
import json
import math
import time

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import folium
from streamlit_folium import st_folium

from twin.runner import run_swmm_simulation
from sensors.virtual import get_sensor_dataframe
from control.metrics import compute_metrics, FLOOD_THRESHOLD_M
from alerts.broadcast import (
    broadcast_all,
    send_telegram,
    send_email,
    send_push_alert,
    _get_setting,
)

# ══════════════════════════════════════════════════════════════════════════════
# PAGE CONFIG & GLOBAL STYLES
# ══════════════════════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="NEERKAAVAL · Velachery Digital Twin",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "About": "NEERKAAVAL — Closed-Loop Stormwater Digital Twin | Velachery, Chennai",
    },
)

st.markdown("""
<style>
    /* Deep Dark Gradient Background for Main App Area */
    [data-testid="stAppViewContainer"] {
        background: linear-gradient(135deg, #0A0E17 0%, #1A2035 100%);
    }
    
    /* Hide footer */
    footer { visibility: hidden; }

    /* Make header and toolbar transparent instead of hidden so the expand button survives */
    header[data-testid="stHeader"] { 
        background-color: transparent !important; 
        z-index: 1000 !important;
    }
    [data-testid="stToolbar"] {
        background-color: transparent !important;
        visibility: visible !important;
        display: flex !important;
    }
    
    /* Hide only the Deploy button and default Main Menu to keep the UI clean */
    .stAppDeployButton, 
    [data-testid="stAppDeployButton"],
    #MainMenu,
    [data-testid="stMainMenu"] { 
        display: none !important; 
    }

    /* Style the Expand (>>) and Collapse (<<) buttons to match the theme and always stay visible */
    [data-testid="stSidebarCollapseButton"],
    [data-testid="stExpandSidebarButton"],
    [data-testid="collapsedControl"],
    button[data-testid="stSidebarCollapseButton"],
    button[data-testid="stExpandSidebarButton"],
    header button {
        visibility: visible !important;
        display: inline-flex !important;
        opacity: 1 !important;
        color: #87CEEB !important; /* Sky Blue */
        background-color: rgba(10, 14, 23, 0.85) !important; /* Dark glassy box */
        border: 1px solid #1E3A8A !important;
        border-radius: 6px !important;
        z-index: 999999 !important;
        cursor: pointer !important;
    }
    [data-testid="stSidebarCollapseButton"]:hover,
    [data-testid="stExpandSidebarButton"]:hover {
        background-color: rgba(30, 58, 138, 0.7) !important;
        border-color: #87CEEB !important;
    }
    [data-testid="stSidebarCollapseButton"] svg,
    [data-testid="stExpandSidebarButton"] svg,
    [data-testid="collapsedControl"] svg {
        fill: #87CEEB !important;
        stroke: #87CEEB !important;
        color: #87CEEB !important;
    }

    /* SKY BLUE Frosted Glass Sidebar */
    [data-testid="stSidebar"] > div:first-child {
        background-color: rgba(135, 206, 235, 0.90) !important; /* Sky Blue */
        backdrop-filter: blur(15px) !important;
        -webkit-backdrop-filter: blur(15px) !important;
        border-right: 2px solid #1E3A8A;
    }

    /* STARRY BLUE Text inside the Sidebar */
    [data-testid="stSidebar"] * {
        color: #0A1128 !important; /* Deep Starry Blue */
    }

    /* DARK Toggle/Checkbox inside Sidebar for visibility */
    [data-testid="stSidebar"] div[data-baseweb="checkbox"] > div {
        background-color: #0A1128 !important;
        border: 1px solid #0A1128 !important;
    }
    [data-testid="stSidebar"] div[data-baseweb="checkbox"] div[data-testid="stTickBar"] {
        background-color: #87CEEB !important; /* Sky blue tick inside dark box */
    }

    /* DARK BLUE Dividing Lines */
    hr { 
        border-bottom: 2px solid #1E3A8A !important; 
    }

    /* Keep Glassmorphism Metric Cards in Main Area */
    [data-testid="stMetric"] {
        background-color: rgba(255, 255, 255, 0.05) !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        backdrop-filter: blur(12px) !important;
        -webkit-backdrop-filter: blur(12px) !important;
        border-radius: 12px;
        padding: 15px;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
    }

    /* Sleek Cyan-to-Blue Gradient Buttons */
    .stButton > button {
        background: linear-gradient(90deg, #00E5FF 0%, #0072FF 100%) !important;
        color: white !important;
        border: none !important;
        border-radius: 8px;
        padding: 10px 24px;
        font-weight: 600;
        transition: all 0.3s ease;
        box-shadow: 0 4px 15px rgba(0, 114, 255, 0.3);
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(0, 114, 255, 0.5);
    }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown("## 🌊 NEERKAAVAL")
    st.markdown("**Closed-Loop Stormwater Digital Twin**")
    st.markdown("_Velachery–Pallikaranai Catchment, Chennai_")
    st.divider()

    st.markdown("### 🧭 Navigation")
    st.page_link("app.py", label="Digital Twin Dashboard (Home)", icon="🌊")
    st.page_link("pages/1_Tidal_Boundary.py", label="Tidal Boundary Telemetry", icon="📊")
    st.divider()

    control_on = st.toggle(
        "⚡ Enable Smart Gate Control",
        value=False,
        help="Activates proactive tidal gate management:\n"
             "• Pre-drain phase (00:00–01:30): gate fully open\n"
             "• Storm peak (01:30–02:00): throttle to 30%\n"
             "• Recession (03:00+): gradual reopen",
    )

    st.divider()
    st.markdown("### 🔧 Alert Credentials")
    tg_token = st.text_input("Telegram Bot Token", value="", type="password",
                              placeholder="Leave blank → demo mode")
    tg_chat  = st.text_input("Telegram Chat ID",   value="",
                              placeholder="e.g. -100123456789")

    st.divider()
    st.markdown("### ℹ️ About")
    st.markdown(
        "<span style='font-size:0.8rem;color:#64748b'>"
        "Physics engine: EPA SWMM 5.1 (pyswmm) with Saint-Venant "
        "mathematical fallback.<br>Design storm: Chennai 100-yr 6-hr event "
        "(peak ~123 mm/hr at 02:00 AM).</span>",
        unsafe_allow_html=True,
    )


# ══════════════════════════════════════════════════════════════════════════════
# DATA LOADING  (cached to avoid re-running on every widget interaction)
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_data(show_spinner=False, ttl=600)
def load_simulation_data():
    """Run both OFF and ON scenarios and return sensor DataFrames + raw records."""
    raw_off = run_swmm_simulation(control_on=False)
    raw_on  = run_swmm_simulation(control_on=True)
    df_off  = get_sensor_dataframe(raw_off, rng_seed=42)
    df_on   = get_sensor_dataframe(raw_on,  rng_seed=99)
    return df_off, df_on, raw_off, raw_on

with st.spinner("⚙️ Running SWMM physics engine…"):
    df_off, df_on, raw_off, raw_on = load_simulation_data()

# ── Compute metrics ───────────────────────────────────────────────────────────
metrics = compute_metrics(df_off, df_on)

# ── Current active scenario for spatial map ───────────────────────────────────
df_active = df_on if control_on else df_off


# ══════════════════════════════════════════════════════════════════════════════
# PAGE HEADER
# ══════════════════════════════════════════════════════════════════════════════

hcol1, hcol2 = st.columns([3, 1])
with hcol1:
    st.markdown("# 🌊 NEERKAAVAL")
with hcol2:
    st.page_link("pages/1_Tidal_Boundary.py", label="🌊 Live Tidal Boundary →", icon="📊")

status_color = "#22c55e" if control_on else "#ef4444"
status_text  = "🟢 ACTIVE CONTROL — Smart gates engaged" if control_on else "🔴 NO CONTROL — Passive drainage (flood risk)"
st.info(
    f"{status_text}  |  Design Storm: Chennai 100-yr · Peak 02:00 AM · Duration 6 hr"
)

st.divider()


# ══════════════════════════════════════════════════════════════════════════════
# FLOOD ALERT BANNER
# ══════════════════════════════════════════════════════════════════════════════

peak_active = df_active["Velachery_Main"].max() if "Velachery_Main" in df_active.columns else 0.0

if peak_active > FLOOD_THRESHOLD_M:
    st.error(
        f"🚨 **CRITICAL FLOOD ALERT** — Velachery_Main peak depth: "
        f"**{peak_active:.2f} m** > 1.2 m threshold. "
        f"Downstream roads inundated. Activate emergency protocols."
    )
else:
    st.success(
        f"✅ **Within Safe Limits** — Velachery_Main peak held at "
        f"**{peak_active:.2f} m** (threshold 1.2 m). "
        f"Smart gate control successfully mitigated flood surge."
    )


# ══════════════════════════════════════════════════════════════════════════════
# KPI METRIC CARDS
# ══════════════════════════════════════════════════════════════════════════════

st.markdown("## 📊 Hydraulic Performance Metrics")
c1, c2, c3, c4 = st.columns(4)

with c1:
    st.metric(
        label="🔴 Peak Depth — Control OFF",
        value=f"{metrics['peak_depth_off']:.2f} m",
        delta=f"{'OVERFLOW' if metrics['peak_depth_off'] > FLOOD_THRESHOLD_M else 'OK'}",
        delta_color="inverse" if metrics['peak_depth_off'] > FLOOD_THRESHOLD_M else "normal",
        help="Maximum water depth at Velachery_Main junction without gate control.",
    )

with c2:
    st.metric(
        label="🔵 Peak Depth — Control ON",
        value=f"{metrics['peak_depth_on']:.2f} m",
        delta=f"−{metrics['peak_depth_reduction']:.2f} m reduction",
        delta_color="normal",
        help="Maximum water depth at Velachery_Main junction with proactive gate management.",
    )

with c3:
    st.metric(
        label="⏱️ Flood Hours Avoided",
        value=f"{metrics['flood_hours_avoided']:.1f} hrs",
        delta=f"{metrics['flood_hours_off']:.1f}h → {metrics['flood_hours_on']:.1f}h",
        delta_color="normal",
        help="Reduction in Flooded-Node-Hours (time depth > 1.2 m at Velachery_Main).",
    )

with c4:
    st.metric(
        label="💧 Flood Volume Mitigated",
        value=f"{metrics['pct_volume_mitigated']:.1f}%",
        delta=f"Excess vol index: {metrics['flood_volume_index_off']:.3f} → {metrics['flood_volume_index_on']:.3f}",
        delta_color="normal",
        help="Percentage of overflow volume index avoided by gate actuation (trapezoidal integral of depth-excess).",
    )


# ══════════════════════════════════════════════════════════════════════════════
# PLOTLY COMPARATIVE DEPTH CHART
# ══════════════════════════════════════════════════════════════════════════════

st.divider()
st.markdown("## 📈 Depth Hydrograph — Control OFF vs Control ON")

time_axis = df_off.index.to_numpy()
depth_off = df_off["Velachery_Main"].to_numpy() if "Velachery_Main" in df_off.columns else []
depth_on  = df_on["Velachery_Main"].to_numpy()  if "Velachery_Main" in df_on.columns  else []

fig = go.Figure()

# ── Flood danger zone fill ────────────────────────────────────────────────────
fig.add_hrect(
    y0=FLOOD_THRESHOLD_M, y1=4.0,
    fillcolor="rgba(239,68,68,0.07)",
    line_width=0,
    annotation_text="⚠️ Flood Zone (>1.2 m)",
    annotation_position="top right",
    annotation_font_color="#ef4444",
    annotation_font_size=11,
)

# ── Control OFF — red dotted ──────────────────────────────────────────────────
fig.add_trace(go.Scatter(
    x=time_axis,
    y=depth_off,
    mode="lines",
    name="Control OFF (Passive)",
    line=dict(color="#ef4444", width=2.5, dash="dot"),
    hovertemplate="<b>Control OFF</b><br>Time: %{x:.0f} min<br>Depth: %{y:.3f} m<extra></extra>",
))

# ── Control ON — blue solid ───────────────────────────────────────────────────
fig.add_trace(go.Scatter(
    x=time_axis,
    y=depth_on,
    mode="lines",
    name="Control ON (Active Gates)",
    line=dict(color="#3b82f6", width=2.5),
    hovertemplate="<b>Control ON</b><br>Time: %{x:.0f} min<br>Depth: %{y:.3f} m<extra></extra>",
    fill="tonexty" if len(depth_off) > 0 else None,
    fillcolor="rgba(59,130,246,0.06)",
))

# ── Flood threshold — red dashed horizontal ───────────────────────────────────
fig.add_hline(
    y=FLOOD_THRESHOLD_M,
    line=dict(color="#ef4444", width=1.5, dash="dash"),
    annotation_text=f"Flood Threshold {FLOOD_THRESHOLD_M} m",
    annotation_position="bottom right",
    annotation_font_color="#ef4444",
    annotation_font_size=11,
)

# ── Gate actuation annotations ────────────────────────────────────────────────
fig.add_vrect(x0=0,   x1=90,  fillcolor="rgba(34,197,94,0.06)",  line_width=0,
              annotation_text="Pre-drain", annotation_position="top left",
              annotation_font_size=10, annotation_font_color="#22c55e")
fig.add_vrect(x0=120, x1=180, fillcolor="rgba(245,158,11,0.06)", line_width=0,
              annotation_text="Storm Peak", annotation_position="top left",
              annotation_font_size=10, annotation_font_color="#f59e0b")

# ── Layout ────────────────────────────────────────────────────────────────────
fig.update_layout(
    paper_bgcolor="#0d1425",
    plot_bgcolor="#0a1020",
    font=dict(family="Inter", color="#94a3b8", size=12),
    legend=dict(
        bgcolor="rgba(17,24,39,0.85)",
        bordercolor="#1e293b",
        borderwidth=1,
        font=dict(color="#f1f5f9"),
        orientation="h",
        yanchor="bottom", y=1.02,
        xanchor="right",  x=1,
    ),
    xaxis=dict(
        title="Time (minutes from midnight)",
        showgrid=True, gridcolor="#1e293b", gridwidth=1,
        zeroline=False,
        tickvals=list(range(0, 370, 30)),
        ticktext=[f"{h//60:02d}:{h%60:02d}" for h in range(0, 370, 30)],
        color="#64748b",
    ),
    yaxis=dict(
        title="Water Depth at Velachery_Main (m)",
        showgrid=True, gridcolor="#1e293b", gridwidth=1,
        zeroline=True, zerolinecolor="#1e293b",
        range=[-0.05, max(2.2, (max(depth_off) if len(depth_off) else 2.2) + 0.2)],
        color="#64748b",
    ),
    hovermode="x unified",
    margin=dict(l=60, r=30, t=60, b=60),
    height=430,
)

# ── Render with camera/PNG export enabled ─────────────────────────────────────
st.plotly_chart(
    fig,
    use_container_width=True,
    config={
        "displayModeBar": True,
        "modeBarButtonsToAdd": ["toImage"],
        "toImageButtonOptions": {
            "format": "png",
            "filename": "neerkaaval_depth_hydrograph",
            "height": 800,
            "width": 1400,
            "scale": 2,
        },
        "displaylogo": False,
    },
)
st.caption("📷 Use the camera icon in the chart toolbar to export a high-resolution PNG for slides.")


# ══════════════════════════════════════════════════════════════════════════════
# OUTFALL FLOW CHART
# ══════════════════════════════════════════════════════════════════════════════

with st.expander("📉 Gate Outfall Flow (m³/s) — expand to view", expanded=False):
    flow_off = [r.get("outfall_flow_cms", 0) for r in raw_off]
    flow_on  = [r.get("outfall_flow_cms", 0) for r in raw_on]
    t_flow   = [r.get("time_min", 0)         for r in raw_off]

    fig_flow = go.Figure()
    fig_flow.add_trace(go.Scatter(x=t_flow, y=flow_off, mode="lines",
                                  name="Control OFF", line=dict(color="#ef4444", width=2, dash="dot")))
    fig_flow.add_trace(go.Scatter(x=t_flow, y=flow_on,  mode="lines",
                                  name="Control ON",  line=dict(color="#3b82f6", width=2)))
    fig_flow.update_layout(
        paper_bgcolor="#0d1425", plot_bgcolor="#0a1020",
        font=dict(family="Inter", color="#94a3b8"),
        xaxis=dict(title="Time (min)", showgrid=True, gridcolor="#1e293b"),
        yaxis=dict(title="Gate_01 Outfall Flow (m³/s)", showgrid=True, gridcolor="#1e293b"),
        height=300, margin=dict(l=60, r=20, t=30, b=50),
        legend=dict(bgcolor="rgba(17,24,39,0.85)", bordercolor="#1e293b"),
    )
    st.plotly_chart(fig_flow, use_container_width=True,
                    config={"displayModeBar": True, "displaylogo": False})


# ══════════════════════════════════════════════════════════════════════════════
# SPATIAL MAP — DUAL-MODE ANIMATED SIMULATION
# Auto-Play: frame-by-frame loop | Manual Scrub: slider-driven
# ══════════════════════════════════════════════════════════════════════════════

st.divider()
st.markdown("## 🗺️ Live Spatial Map — Flood Extent")

# ── Shared helpers (depth lookup, radius, colour) ──────────────────────────────────
def safe_depth(df: pd.DataFrame, node: str, idx: int) -> float:
    if node in df.columns and idx < len(df):
        val = df[node].iloc[idx]
        return float(val) if pd.notna(val) else 0.0
    return 0.0

def flood_radius(depth: float, threshold: float = FLOOD_THRESHOLD_M, base=8, max_r=50) -> float:
    ratio = depth / threshold
    return min(base + (ratio - 0.5) * 25, max_r) if ratio > 0.5 else base

def depth_color(depth: float, threshold: float = FLOOD_THRESHOLD_M) -> str:
    if depth > threshold:
        return "#ef4444"   # Red — flooded
    elif depth > threshold * 0.8:
        return "#f59e0b"   # Orange — warning
    else:
        return "#22c55e"   # Green — safe

# ── Controls row: Auto-Play button  |  Manual Scrub slider ────────────────────
map_ctrl_left, map_ctrl_right = st.columns([1, 4])

with map_ctrl_left:
    autoplay = st.button(
        "▶️ Auto-Play",
        use_container_width=True,
        help="Animate flood progression frame-by-frame (steps 0–99)",
        key="btn_autoplay",
    )

with map_ctrl_right:
    scrub_t = st.slider(
        "Scrub Timeline (Minutes)",
        min_value=0,
        max_value=99,
        value=24,
        step=1,
        help="Drag to manually scrub to any simulation timestep.",
        key="map_scrub",
    )

# ── Persistent placeholders (declared before draw_map_frame so animation
# can update them independently, preventing UI jumping) ────────────────────────
status_area = st.empty()   # holds the timestep / depth status bar
map_area    = st.empty()   # holds the Folium iframe


def draw_map_frame(t: int) -> None:
    """
    Render a single Folium map frame at simulation minute `t` (0–99)
    into the shared `map_area` placeholder.
    """
    # Clamp t to valid DataFrame index range
    max_idx = len(df_active) - 1
    idx = min(int(t), max_idx)

    # ── Retrieve sensor depths at this timestep ───────────────────────────
    d_v = safe_depth(df_active, "Velachery_Main", idx)
    d_p = safe_depth(df_active, "Pallikaranai",   idx)
    d_o = safe_depth(df_active, "Outfall_Gate",   idx)

    # Actual time label from DataFrame index
    t_min   = int(df_active.index[idx]) if idx < len(df_active) else t
    t_label = f"{t_min // 60:02d}:{t_min % 60:02d}"

    # Velachery radius: spec formula  5 + depth * 30
    v_radius = 5 + d_v * 30
    v_color  = "#ef4444" if d_v > FLOOD_THRESHOLD_M else "#3b82f6"

    # Pre-compute all colours & radii before any rendering
    pl_color  = depth_color(d_p)
    pl_radius = flood_radius(d_p, threshold=2.5, base=14, max_r=55)
    og_color  = depth_color(d_o, threshold=1.8)
    og_radius = flood_radius(d_o, threshold=1.8, base=7, max_r=30)

    # ── 1. Update status bar (independent of iframe, no layout shift) ──────────
    flood_status = "🔴 FLOODED" if d_v > FLOOD_THRESHOLD_M else "🟢 Safe"
    status_area.markdown(
        f"<div style='color:#64748b;font-size:0.85rem;min-height:40px;"
        f"margin-bottom:6px;padding:4px 0;'>"
        f"⏱ <strong style='color:#06b6d4'>Timestep {t} &mdash; {t_label}</strong>"
        f" &nbsp;|&thinsp;&nbsp; "
        f"Velachery_Main: <strong style='color:{v_color}'>{d_v:.2f} m</strong>"
        f" &nbsp;|&thinsp;&nbsp; "
        f"Pallikaranai: <strong style='color:{pl_color}'>{d_p:.2f} m</strong>"
        f" &nbsp;|&thinsp;&nbsp; "
        f"Outfall: <strong style='color:{og_color}'>{d_o:.2f} m</strong>"
        f" &nbsp;|&thinsp;&nbsp; "
        f"<strong style='color:{v_color}'>{flood_status}</strong>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # ── Build Folium map ──────────────────────────────────────────────────────
    m = folium.Map(
        location=[12.96, 80.22],
        zoom_start=13,
        tiles="OpenStreetMap",
        prefer_canvas=True,
    )

    # Velachery_Main — dynamic radius + colour
    folium.CircleMarker(
        location=[12.9800, 80.2200],
        radius=v_radius,
        color=v_color,
        fill=True,
        fill_color=v_color,
        fill_opacity=0.45,
        weight=2,
        popup=folium.Popup(
            f"<b>Velachery Main Drain</b><br>"
            f"Depth: {d_v:.3f} m<br>"
            f"Time: {t_label}<br>"
            f"Status: {'🔴 FLOODED' if d_v > FLOOD_THRESHOLD_M else '🟢 Safe'}",
            max_width=220,
        ),
        tooltip=f"Velachery_Main · {d_v:.2f}m",
    ).add_to(m)

    # Outer glow ring when flooding
    if d_v > FLOOD_THRESHOLD_M:
        folium.CircleMarker(
            location=[12.9800, 80.2200],
            radius=v_radius + 10,
            color="#ef4444",
            fill=False,
            weight=1,
            opacity=0.3,
        ).add_to(m)

    # Pallikaranai Marsh
    folium.CircleMarker(
        location=[12.9300, 80.2100],
        radius=pl_radius,
        color=pl_color,
        fill=True,
        fill_color=pl_color,
        fill_opacity=0.35,
        weight=2,
        popup=folium.Popup(
            f"<b>Pallikaranai Marsh Storage</b><br>"
            f"Depth: {d_p:.3f} m<br>"
            f"Time: {t_label}",
            max_width=220,
        ),
        tooltip=f"Pallikaranai · {d_p:.2f}m",
    ).add_to(m)

    # Outfall_Gate
    folium.CircleMarker(
        location=[12.9500, 80.2500],
        radius=og_radius,
        color=og_color,
        fill=True,
        fill_color=og_color,
        fill_opacity=0.5,
        weight=2,
        popup=folium.Popup(
            f"<b>Outfall Gate (Gate_01)</b><br>"
            f"Depth: {d_o:.3f} m<br>"
            f"Gate: {'THROTTLED' if control_on else 'PASSIVE'}<br>"
            f"Time: {t_label}",
            max_width=220,
        ),
        tooltip=f"Outfall Gate · {d_o:.2f}m",
    ).add_to(m)

    # Buckingham Canal boundary marker
    folium.Marker(
        location=[12.9550, 80.2650],
        popup="Buckingham Canal Outfall",
        tooltip="Buckingham Canal",
        icon=folium.Icon(color="blue", icon="water", prefix="fa"),
    ).add_to(m)

    # Map legend
    legend_html = f"""
    <div style="position:fixed;bottom:20px;left:20px;z-index:9999;
         background:#111827;border:1px solid #1e293b;border-radius:8px;
         padding:12px 16px;font-size:12px;color:#94a3b8;font-family:Inter,sans-serif;">
      <b style="color:#f1f5f9">Legend</b><br>
      <span style="color:#ef4444">●</span> Flooded (>{FLOOD_THRESHOLD_M}m)<br>
      <span style="color:#f59e0b">●</span> Warning (>{FLOOD_THRESHOLD_M*0.8:.1f}m)<br>
      <span style="color:#22c55e">●</span> Safe<br>
      <span style="color:#3b82f6">●</span> Controlled / Buckingham Canal<br>
      <i style="font-size:10px">Circle size ∝ flood depth</i>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))

    # ── 2. Render pre-built map object into isolated placeholder ──────────────
    # `m` is fully constructed above this point; writing to map_area only here
    # keeps the previous iframe visible for as long as possible → less white flash.
    with map_area.container():
        st_folium(
            m,
            use_container_width=True,
            height=430,
            key=f"map_{t}",
            returned_objects=[],   # suppresses return data → faster re-render
        )


# ── Dual-mode logic ────────────────────────────────────────────────────────────
if autoplay:
    # Auto-Play: animate frames 0 → 98 in steps of 2
    progress = st.progress(0, text="🎥 Rendering flood animation…")
    for step in range(0, 100, 2):
        draw_map_frame(step)
        progress.progress(
            (step + 2) / 100,
            text=f"🎥 Animating… timestep {step}/99",
        )
        time.sleep(0.75)
    progress.empty()
    st.success("✅ Animation complete — drag the scrub slider to inspect any frame.")
else:
    # Manual Scrub: render the single frame bound to the slider
    draw_map_frame(scrub_t)



# ══════════════════════════════════════════════════════════════════════════════
# EMERGENCY BROADCAST PANEL
# ══════════════════════════════════════════════════════════════════════════════

st.divider()
st.markdown("## 📡 Emergency Broadcast System")

peak_for_alert = metrics["peak_depth_off"]   # Alert based on worst-case scenario

ntfy_topic = _get_setting("NTFY_TOPIC", "neerkaaval_alerts_demo")
ntfy_server = _get_setting("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
ntfy_url = f"{ntfy_server}/{ntfy_topic}"

col_tg, col_em, col_push = st.columns(3)

def _render_channel_result(result: dict):
    if result.get("demo"):
        st.info(f"📤 Demo mode — {result.get('message','configure credentials')}", icon="ℹ️")
    elif result.get("success"):
        st.success("✅ Alert dispatched successfully", icon="✅")
    else:
        st.error(f"❌ Failed: {result.get('error','unknown error')}", icon="🚨")

with col_tg:
    st.markdown("### 📱 Telegram")
    st.caption("Instant push to engineers' group via Telegram Bot")
    tg_configured = bool(_get_setting("TELEGRAM_BOT_TOKEN") and _get_setting("TELEGRAM_CHAT_ID"))
    if not tg_configured:
        st.caption("Credentials need a telegram group")
    if st.button("Send Telegram Alert", use_container_width=True, type="primary",
                  key="btn_telegram"):
        with st.spinner("Sending…"):
            res = send_telegram(
                node="Velachery_Main", peak_depth=peak_for_alert,
                lat=12.98, lon=80.22,
            )
            _render_channel_result(res)

with col_em:
    st.markdown("### 📧 Email")
    st.caption("SMTP alert to operations & disaster management team")
    em_configured = bool(_get_setting("SMTP_USER") and _get_setting("SMTP_PASS") and _get_setting("ALERT_EMAIL"))
    if not em_configured:
        st.caption("⚠️ SMTP not configured (runs in demo mode)")
    if st.button("Send Email Alert", use_container_width=True,
                  key="btn_email"):
        with st.spinner("Sending…"):
            res = send_email("Velachery_Main", peak_for_alert, 12.98, 80.22)
            _render_channel_result(res)

with col_push:
    st.markdown("### 📲 Push Notification")
    st.caption("Live mobile/desktop push via ntfy.sh (No signup needed)")
    st.markdown(f"🔔 **Channel:** [`{ntfy_topic}`]({ntfy_url}) *(click to open)*")
    if st.button("Send Push Notification", use_container_width=True,
                  key="btn_push"):
        with st.spinner("Sending…"):
            res = send_push_alert("Velachery_Main", peak_for_alert, 12.98, 80.22)
            if res.get("success"):
                st.success(f"✅ Alert sent to `{ntfy_topic}`! Check [{ntfy_topic}]({ntfy_url})", icon="✅")
            else:
                _render_channel_result(res)

with st.expander("⚙️ Alert Channels Setup & Credentials Guide", expanded=False):
    st.markdown(f"""
    ### 1. 📲 Push Notifications (ntfy.sh — Free & Instant)
    - **No accounts or API keys required.**
    - Current topic: **[`{ntfy_topic}`]({ntfy_url})**
    - **How to test now:** Open [`{ntfy_url}`]({ntfy_url}) in a new browser tab and click **"Subscribe" / "Allow Notifications"**. Then click the **Send Push Notification** button above to hear the siren/alert instantly!
    - On mobile, install the free **ntfy** app (Android/iOS) and subscribe to `{ntfy_topic}`.

    ---
    ### 2. 📧 Email Notifications (Gmail SMTP)
    Email runs in demo mode until SMTP credentials are provided. Create a `.env` file in the project folder with:
    ```ini
    SMTP_HOST=smtp.gmail.com
    SMTP_PORT=587
    SMTP_USER=your_email@gmail.com
    SMTP_PASS=xxxx xxxx xxxx xxxx
    ALERT_EMAIL=recipient_email@gmail.com
    ```
    *(Note: Gmail requires a 16-character **App Password** created at [Google Account > App Passwords](https://myaccount.google.com/apppasswords), not your regular password).*

    ---
    ### 3. 📱 Telegram Bot Alerts
    Telegram runs in demo mode until bot credentials are provided:
    1. Create a bot with **@BotFather** on Telegram to receive your bot token.
    2. Message your bot, then get your chat ID using **@userinfobot**.
    3. Add them to your `.env` file:
    ```ini
    TELEGRAM_BOT_TOKEN=123456789:ABCdefGHI...
    TELEGRAM_CHAT_ID=123456789
    ```
    """)


# ══════════════════════════════════════════════════════════════════════════════
# RAW DATA EXPANDER
# ══════════════════════════════════════════════════════════════════════════════

with st.expander("🔬 Raw Sensor Data — Control OFF / Control ON", expanded=False):
    tab_off, tab_on = st.tabs(["Control OFF", "Control ON"])
    with tab_off:
        st.dataframe(
            df_off.style.highlight_between(
                subset=["Velachery_Main"] if "Velachery_Main" in df_off.columns else [],
                left=FLOOD_THRESHOLD_M, right=999,
                color="rgba(239,68,68,0.25)",
            ),
            use_container_width=True,
        )
    with tab_on:
        st.dataframe(
            df_on.style.highlight_between(
                subset=["Velachery_Main"] if "Velachery_Main" in df_on.columns else [],
                left=FLOOD_THRESHOLD_M, right=999,
                color="rgba(59,130,246,0.25)",
            ),
            use_container_width=True,
        )