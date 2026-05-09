# app.py
# ForensiQ — Main Application Entry Point

import streamlit as st
from database import init_db as initialize_database
from theme import apply_theme

# Must be the very first Streamlit command
st.set_page_config(
    page_title="ForensiQ — Forensic Intelligence System",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize database (creates all tables if not already there)
initialize_database()

# Apply dark theme + sidebar navigation
apply_theme(active_page="Home")

# ------------------------------------------------------------------ #
# HOME PAGE CONTENT
# ------------------------------------------------------------------ #

st.markdown("""
<div class='forensiq-title'>🔬 ForensiQ</div>
<div class='forensiq-subtitle'>
    AI-Powered Forensic Triage & Intelligence System — Built for Investigators
</div>
""", unsafe_allow_html=True)

st.markdown("---")

# Stats Row
from database import get_all_cases
all_cases    = get_all_cases()
open_cases   = [c for c in all_cases if c["status"] == "Open"]
closed_cases = [c for c in all_cases if c["status"] == "Closed"]
urgent_cases = [c for c in all_cases if c["priority"] in ("High", "Critical")]

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("📋 Total Cases",  len(all_cases))
with col2:
    st.metric("🟢 Open Cases",   len(open_cases))
with col3:
    st.metric("✅ Closed Cases", len(closed_cases))
with col4:
    st.metric("🔴 Urgent Cases", len(urgent_cases))

st.markdown("---")

# Module Cards
st.markdown("### 🛠️ Modules")
st.markdown("Click any module in the sidebar to open it.")

modules = [
    ("📋", "Case Manager",
     "Create, search, and manage all investigation cases. Assign priorities, track statuses, and link evidence."),
    ("📄", "Report Analyzer",
     "Upload autopsy and witness statement PDFs. AI extracts key findings and saves them to the database."),
    ("⏱️", "TOD Estimator",
     "Enter body temperature, rigor mortis stage, and ambient conditions. AI calculates time of death range."),
    ("📷", "CCTV Tracker",
     "Log CCTV sightings. Plot suspect movement on an interactive map. AI flags suspicious patterns."),
    ("🔗", "Pattern Engine",
     "AI scans across all cases to detect common MOs, repeat offenders, and linked crime events."),
    ("🧬", "Forensic Profiler",
     "Build AI-assisted suspect profiles from behavioral clues, physical descriptions, and case data."),
    ("⚠️", "Risk Scorer",
     "AI generates violence, flight-risk, and recidivism scores for each suspect with full justification."),
    ("📊", "Analytics Dashboard",
     "Charts and visualizations: case trends, priority heatmaps, TOD distributions, and risk score breakdowns."),
]

col_a, col_b = st.columns(2)
for i, (icon, name, desc) in enumerate(modules):
    target_col = col_a if i % 2 == 0 else col_b
    with target_col:
        st.markdown(f"""
        <div class='module-card'>
            <strong>{icon} {name}</strong><br>
            <small style='color:#8b949e'>{desc}</small>
        </div>
        """, unsafe_allow_html=True)

st.markdown("---")

st.markdown("### ℹ️ About ForensiQ")
st.markdown("""
<div class='forensiq-card'>
    <b>ForensiQ</b> is an AI-powered forensic intelligence platform designed to assist investigators
    in triaging evidence, estimating time of death, tracking suspect movement via CCTV,
    detecting crime patterns across cases, profiling suspects, and generating risk scores —
    all in one unified system.<br><br>
    <b>AI Engine:</b> Featherless AI — <code>meta-llama/Llama-3.3-70B-Instruct</code><br>
    <b>Database:</b> SQLite (local, offline, zero cost)<br>
    <b>Built for:</b> Hackathon — AI Forensics Track
</div>
""", unsafe_allow_html=True)