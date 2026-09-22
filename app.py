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
from alerts.broadcast import broadcast_all

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
  /* ── Import fonts ── */
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=Space+Grotesk:wght@400;600;700&display=swap');

  /* ── Root variables ── */
  :root {
    --bg-primary:    #0a0e1a;
    --bg-card:       #111827;
    --bg-card2:      #1a2236;
    --accent-blue:   #3b82f6;
    --accent-cyan:   #06b6d4;
    --accent-red:    #ef4444;
    --accent-green:  #22c55e;
    --accent-orange: #f59e0b;
    --text-primary:  #f1f5f9;
    --text-muted:    #94a3b8;
    --border:        #1e293b;
    --glow-blue:     0 0 20px rgba(59,130,246,0.3);
    --glow-red:      0 0 20px rgba(239,68,68,0.3);
  }

  /* ── Global base ── */
  html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
    background-color: var(--bg-primary) !important;
    color: var(--text-primary) !important;
  }
  .stApp { background-color: var(--bg-primary) !important; }

  /* ── Map Iframe Smooth Fade-In ── */
  iframe {
    background-color: var(--bg-primary) !important;
    animation: mapFadeIn 0.8s ease-in-out;
  }

  @keyframes mapFadeIn {
    0%   { opacity: 0;   }
    20%  { opacity: 0.9; }
    100% { opacity: 1;   }
  }

  /* ── Sidebar ── */
  [data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0d1425 0%, #0a1020 100%) !important;
    border-right: 1px solid var(--border) !important;
  }
  [data-testid="stSidebar"] .stMarkdown h1,
  [data-testid="stSidebar"] .stMarkdown h2,
  [data-testid="stSidebar"] .stMarkdown h3 {
    color: var(--accent-cyan) !important;
  }

  /* ── Metric cards ── */
  [data-testid="metric-container"] {
    background: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    border-radius: 12px !important;
    padding: 16px 20px !important;
    box-shadow: var(--glow-blue);
    transition: transform 0.2s ease, box-shadow 0.2s ease;
  }
  [data-testid="metric-container"]:hover {
    transform: translateY(-2px);
    box-shadow: 0 0 30px rgba(59,130,246,0.45);
  }
  [data-testid="stMetricLabel"] { color: var(--text-muted) !important; font-size: 0.78rem !important; }
  [data-testid="stMetricValue"] { color: var(--text-primary) !important; font-size: 1.8rem !important; font-weight: 700 !important; }
  [data-testid="stMetricDelta"] { font-size: 0.82rem !important; }

  /* ── Headers ── */
  h1, h2, h3 { font-family: 'Space Grotesk', sans-serif !important; }
  h1 { font-size: 2.2rem !important; font-weight: 700 !important;
       background: linear-gradient(90deg, #06b6d4, #3b82f6);
       -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
  h2 { font-size: 1.35rem !important; color: var(--accent-cyan) !important; }
  h3 { font-size: 1.1rem !important; color: var(--text-muted) !important; font-weight: 500 !important; }

  /* ── Dividers ── */
  hr { border-color: var(--border) !important; }

  /* ── Status banner ── */
  .status-banner {
    background: linear-gradient(135deg, #0f1f3d, #0a1428);
    border: 1px solid var(--border);
    border-left: 4px solid var(--accent-blue);
    border-radius: 8px;
    padding: 12px 20px;
    margin-bottom: 1rem;
    font-size: 0.9rem;
    color: var(--text-muted);
  }

  /* ── Alert banners ── */
  .flood-alert {
    background: linear-gradient(135deg, rgba(239,68,68,0.15), rgba(239,68,68,0.05));
    border: 1px solid rgba(239,68,68,0.4);
    border-left: 4px solid var(--accent-red);
    border-radius: 8px;
    padding: 14px 20px;
    animation: pulse-red 2s ease-in-out infinite;
  }
  @keyframes pulse-red {
    0%, 100% { box-shadow: 0 0 10px rgba(239,68,68,0.2); }
    50%       { box-shadow: 0 0 25px rgba(239,68,68,0.5); }
  }
  .safe-banner {
    background: linear-gradient(135deg, rgba(34,197,94,0.12), rgba(34,197,94,0.04));
    border: 1px solid rgba(34,197,94,0.4);
    border-left: 4px solid var(--accent-green);
    border-radius: 8px;
    padding: 14px 20px;
  }

  /* ── Section card ── */
  .section-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 16px;
  }

  /* ── Broadcast button labels ── */
  .broadcast-label {
    font-size: 0.75rem;
    color: var(--text-muted);
    margin-top: 4px;
    text-align: center;
  }

  /* ── Scrollbar ── */
  ::-webkit-scrollbar { width: 6px; }
  ::-webkit-scrollbar-track { background: #0a0e1a; }
  ::-webkit-scrollbar-thumb { background: #1e293b; border-radius: 3px; }

  /* ── Tooltip / expander ── */
  [data-testid="stExpander"] {
    background: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    border-radius: 10px !important;
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

st.markdown("# 🌊 NEERKAAVAL")

status_color = "#22c55e" if control_on else "#ef4444"
status_text  = "🟢 ACTIVE CONTROL — Smart gates engaged" if control_on else "🔴 NO CONTROL — Passive drainage (flood risk)"
st.markdown(
    f'<div class="status-banner">'
    f'<span style="color:{status_color};font-weight:600">{status_text}</span>'
    f' &nbsp;|&nbsp; Design Storm: Chennai 100-yr · Peak 02:00 AM · Duration 6 hr'
    f'</div>',
    unsafe_allow_html=True,
)

st.divider()


# ══════════════════════════════════════════════════════════════════════════════
# FLOOD ALERT BANNER
# ══════════════════════════════════════════════════════════════════════════════

peak_active = df_active["Velachery_Main"].max() if "Velachery_Main" in df_active.columns else 0.0

if peak_active > FLOOD_THRESHOLD_M:
    st.markdown(
        f'<div class="flood-alert">'
        f'🚨 <strong>CRITICAL FLOOD ALERT</strong> — Velachery_Main peak depth: '
        f'<strong>{peak_active:.2f} m</strong> &gt; 1.2 m threshold. '
        f'Downstream roads inundated. Activate emergency protocols.'
        f'</div>',
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        f'<div class="safe-banner">'
        f'✅ <strong>Within Safe Limits</strong> — Velachery_Main peak held at '
        f'<strong>{peak_active:.2f} m</strong> (threshold 1.2 m). '
        f'Smart gate control successfully mitigated flood surge.'
        f'</div>',
        unsafe_allow_html=True,
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

col_tg, col_em, col_push = st.columns(3)

def _render_channel_result(result: dict):
    if result.get("demo"):
        st.info(f"📤 Demo mode — {result.get('message','configure env vars')}", icon="ℹ️")
    elif result.get("success"):
        st.success("✅ Alert dispatched successfully", icon="✅")
    else:
        st.error(f"❌ Failed: {result.get('error','unknown error')}", icon="🚨")

with col_tg:
    st.markdown("### 📱 Telegram")
    st.caption("Instant push to engineers' group")
    if st.button("Send Telegram Alert", use_container_width=True, type="primary",
                  key="btn_telegram"):
        with st.spinner("Sending…"):
            res = broadcast_all(
                node="Velachery_Main", peak_depth=peak_for_alert,
                lat=12.98, lon=80.22,
                bot_token=tg_token, chat_id=tg_chat,
            )
            _render_channel_result(res.get("telegram", {}))

with col_em:
    st.markdown("### 📧 Email")
    st.caption("SMTP alert to operations team")
    if st.button("Send Email Alert", use_container_width=True,
                  key="btn_email"):
        with st.spinner("Sending…"):
            res = broadcast_all("Velachery_Main", peak_for_alert, 12.98, 80.22)
            _render_channel_result(res.get("email", {}))

with col_push:
    st.markdown("### 📲 Push Notification")
    st.caption("ntfy.sh push notification · subscribe to topic set in NTFY_TOPIC env var")
    if st.button("Send Push Notification", use_container_width=True,
                  key="btn_push"):
        with st.spinner("Sending…"):
            res = broadcast_all("Velachery_Main", peak_for_alert, 12.98, 80.22)
            _render_channel_result(res.get("push", {}))

st.caption(
    "Configure TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, SMTP_HOST, SMTP_USER, SMTP_PASS, "
    "ALERT_EMAIL as environment variables to enable real dispatch. "
    "Push alerts (ntfy.sh) also require NTFY_TOPIC to be set — subscribers join that topic "
    "on the ntfy app. Absent vars → demo mode (toast only)."
)


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