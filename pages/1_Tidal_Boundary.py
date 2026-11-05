import streamlit as st
import pandas as pd
import numpy as np
import requests
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables for the secure API key
load_dotenv()

st.set_page_config(page_title="Live Tidal Telemetry", page_icon="🌊", layout="wide")

# UI CSS INJECTION
st.markdown("""
<style>
    [data-testid="stAppViewContainer"] { background: linear-gradient(135deg, #0A0E17 0%, #1A2035 100%); }
    header[data-testid="stHeader"] { background-color: transparent !important; }
    .stAppDeployButton, #MainMenu, [data-testid="stMainMenu"] { display: none !important; }
    [data-testid="collapsedControl"],
    [data-testid="stExpandSidebarButton"] {
        color: #87CEEB !important; 
        background-color: rgba(10, 14, 23, 0.7) !important;
        border: 1px solid #1E3A8A !important;
        border-radius: 6px;
        margin-top: 15px; margin-left: 10px; z-index: 9999;
    }
    [data-testid="stSidebar"] > div:first-child {
        background-color: rgba(135, 206, 235, 0.90) !important;
        backdrop-filter: blur(15px) !important;
        -webkit-backdrop-filter: blur(15px) !important;
        border-right: 2px solid #1E3A8A;
    }
    [data-testid="stSidebar"] * { color: #0A1128 !important; }
    hr { border-bottom: 2px solid #1E3A8A !important; }
    [data-testid="stMetric"] {
        background-color: rgba(255, 255, 255, 0.05) !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        backdrop-filter: blur(12px) !important;
        -webkit-backdrop-filter: blur(12px) !important;
        border-radius: 12px;
        padding: 15px;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
    }
</style>
""", unsafe_allow_html=True)

st.title("🌊 Live Tidal Boundary Telemetry")
st.markdown("Real-time Bay of Bengal sea-level monitoring for Velachery outfall backflow prediction.")
st.markdown("---")

def get_mock_data():
    now = datetime.now()
    times = [now - timedelta(minutes=5 * i) for i in range(144)]
    times.reverse()
    amplitudes = [(0.8 * np.sin((i / 144) * 2 * np.pi)) + np.random.normal(0, 0.02) for i in range(len(times))]
    return pd.DataFrame({"Time": times, "Sea Level (m)": amplitudes}).set_index("Time"), "Simulation Fallback"

@st.cache_data(ttl=3600)
def fetch_real_tidal_data():
    api_key = os.environ.get("STORMGLASS_API_KEY")
    if not api_key:
        return get_mock_data()
        
    lat, lng = 13.0, 80.3
    start_time = int((datetime.now() - timedelta(hours=12)).timestamp())
    end_time = int(datetime.now().timestamp())
    url = f"https://api.stormglass.io/v2/weather/point?lat={lat}&lng={lng}&params=seaLevel&start={start_time}&end={end_time}"
    
    try:
        response = requests.get(url, headers={"Authorization": api_key}, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        times = []
        levels = []
        for item in data['hours']:
            dt = datetime.fromisoformat(item['time'].replace('Z', '+00:00'))
            ist_time = dt + timedelta(hours=5, minutes=30)
            times.append(ist_time)
            levels.append(item['seaLevel'].get('sg', 0))
            
        df = pd.DataFrame({"Time": times, "Sea Level (m)": levels}).set_index("Time")
        return df, "Stormglass.io Marine API (Live)"
        
    except Exception as e:
        return get_mock_data()

with st.spinner("Establishing secure uplink to Bay of Bengal buoys..."):
    df, source_label = fetch_real_tidal_data()

current_tide = df["Sea Level (m)"].iloc[-1]
trend = current_tide - df["Sea Level (m)"].iloc[-2]

col1, col2, col3 = st.columns(3)

with col1:
    st.metric("Current Sea Level Anomaly", f"{current_tide:.3f} m", f"{trend:.3f} m/hr")
with col2:
    status = "Safe" if current_tide < 0.5 else ("WARNING" if current_tide < 0.7 else "CRITICAL")
    st.metric("Backflow Risk Status", status)
with col3:
    st.metric("Outfall Sluice Gates", "OPEN" if current_tide < 0.5 else "CLOSED")

if "Live" in source_label:
    st.success(f"📡 Status: SECURE | Source: {source_label} | Last Sync: {datetime.now().strftime('%H:%M:%S')} IST")
else:
    st.warning(f"📡 Status: OFFLINE | Source: {source_label} (Check API Key or Network)")

st.line_chart(df["Sea Level (m)"], height=400, use_container_width=True)
