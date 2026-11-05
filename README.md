# Flood-Detection-System
NEERKAAVAL is an interactive flood-monitoring and decision-support dashboard designed to simulate and mitigate coastal urban inundation during extreme storm events. Focusing on the low-lying catchment basin of Velachery in South Chennai, the platform demonstrates how automated, motorized sluice gates can counteract tidal backflow from the Bay of Bengal and alleviate urban waterlogging.

Key Highlights
Deterministic Hydrodynamic Modeling: Implements EPA SWMM-based routing principles grounded in the 1D Saint-Venant equations to model backwater effects, pipe surcharge, and channel momentum—avoiding the black-box hallucinations of unconstrained ML models.

100-Year Synthetic Design Storm: Evaluates drainage network behavior against a synthetic rainfall hyetograph peaking at 120 mm/hr, synthesized using the Chicago Design Storm method and local historical Intensity-Duration-Frequency (IDF) parameters.

Interactive Spatiotemporal Mapping: Visualizes real-time node stage heights, reverse flow points, and mitigation impacts using Folium and OpenTopoMap elevation contours without external proprietary API dependencies.

Zero-Latency Alert Pipeline: Integrates decoupled notification pipelines using ntfy.sh push notifications, Telegram bot webhooks, and standard SMTP alerting to trigger automated warnings whenever threshold depths are breached.

Tech Stack
Frontend / Dashboard: Streamlit, Folium (streamlit-folium)

Hydraulic Principles: EPA SWMM, 1D Saint-Venant Equations (Dynamic Wave Routing)

Telemetry & Dispatch: requests (HTTP Webhooks / ntfy.sh), Python SMTP, Telegram Bot API

Data Processing: Python, NumPy, Pandas
Automated urban flood telemetry & decision-support dashboard for Velachery, Chennai. Uses EPA SWMM hydrodynamic routing to simulate 100-year storm surges and evaluate motorized sluice gate control, featuring live Folium mapping and zero-latency push alerts via ntfy.sh.
