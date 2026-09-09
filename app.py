import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium

# Imports from your modules
from twin.runner_stub import run_simulation
from sensors.virtual import apply_sensor_noise
from alerts.telegram import send_flood_alert

st.set_page_config(page_title="NEERKAAVAL MVP", layout="wide")
st.title("🌊 NEERKAAVAL: Digital Twin")

# The core interactive element
control_on = st.toggle("Enable Smart Control (Tidal Gates & Detention)", value=False)
st.write(f"**System Status:** {'🟢 Active Control' if control_on else '🔴 No Control (Flooding Risk)'}")

# Generate data
raw_data = run_simulation(control_on=control_on)
sensor_data = [apply_sensor_noise(step) for step in raw_data]
df = pd.DataFrame(sensor_data)

# Calculate metric
peak_depth = df["Velachery_Main"].max() if not df.empty else 0

# Map
st.subheader("Live Network Map: Velachery & Pallikaranai")
node_color = "red" if peak_depth > 1.2 else "green"
m = folium.Map(location=[12.96, 80.22], zoom_start=13, tiles="CartoDB positron")

folium.CircleMarker(
    [12.98, 80.22], radius=10, color=node_color, fill=True, popup="Velachery Main"
).add_to(m)
folium.CircleMarker(
    [12.93, 80.21], radius=15, color="blue", fill=True, popup="Marsh Storage (Detention)"
).add_to(m)
folium.CircleMarker(
    [12.95, 80.25], radius=10, color="orange", fill=True, popup="Tidal Outfall Gate"
).add_to(m)

st_folium(m, use_container_width=True, height=550)

# Charts and Alerts
st.subheader("Water Depths at Key Nodes (Meters)")
st.line_chart(df)

col1, col2 = st.columns(2)
with col1:
    st.metric(
        label="Peak Network Depth", 
        value=f"{peak_depth:.2f} m", 
        delta="-0.60 m (Flooding Avoided)" if control_on else "Warning: Overflow", 
        delta_color="inverse"
    )

if peak_depth > 1.2:
    st.error(f"🚨 CRITICAL: Velachery_Main breached 1.2m! Peak: {peak_depth:.2f}m")
else:
    st.success(f"✅ Smart Control Active. Peak held at {peak_depth:.2f}m")

# Telegram integration
st.subheader("System Communications")

# NOTE: Paste your real Token and Chat ID here for the demo
BOT_TOKEN = "YOUR_BOTFATHER_TOKEN" 
CHAT_ID = "YOUR_CHAT_ID"

if peak_depth > 1.2:
    if st.button("📱 Push Emergency Alert to Engineers"):
        send_flood_alert(BOT_TOKEN, CHAT_ID, "Velachery_Main", peak_depth)
        st.success("Alert pushed to Telegram successfully.")