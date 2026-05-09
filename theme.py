# theme.py
# ForensiQ — Shared theme, CSS, and sidebar navigation
# Every page imports this and calls apply_theme() at the top.
# To change the look of the whole app, only edit this one file.

import streamlit as st


def apply_theme(active_page="Home"):
    """
    Call this at the top of every page file, after set_page_config().
    It injects the dark CSS and draws the sidebar navigation.

    Usage in any page file:
        from theme import apply_theme
        apply_theme(active_page="Case Manager")
    """

    # ------------------------------------------------------------------ #
    # CUSTOM CSS — Dark forensic theme (same as app.py)
    # ------------------------------------------------------------------ #
    st.markdown("""
    <style>
        /* ---- Hide Streamlit's auto-generated page nav ---- */
        [data-testid="stSidebarNav"] {
            display: none !important;
        }

        /* ---- Main background ---- */
        .stApp {
            background-color: #0d1117;
            color: #c9d1d9;
        }

        /* ---- Sidebar ---- */
        section[data-testid="stSidebar"] {
            background-color: #161b22;
            border-right: 1px solid #30363d;
        }

        /* ---- Sidebar text ---- */
        section[data-testid="stSidebar"] * {
            color: #c9d1d9 !important;
        }

        /* ---- Buttons ---- */
        .stButton > button {
            background-color: #238636;
            color: white;
            border: none;
            border-radius: 6px;
            padding: 0.5rem 1.2rem;
            font-weight: 600;
            transition: background-color 0.2s;
        }
        .stButton > button:hover {
            background-color: #2ea043;
        }

        /* ---- Cards / Info boxes ---- */
        .forensiq-card {
            background-color: #161b22;
            border: 1px solid #30363d;
            border-radius: 10px;
            padding: 1.2rem 1.5rem;
            margin-bottom: 1rem;
        }

        /* ---- Big header title ---- */
        .forensiq-title {
            font-size: 3rem;
            font-weight: 800;
            color: #58a6ff;
            letter-spacing: -1px;
            line-height: 1.1;
        }

        /* ---- Subtitle ---- */
        .forensiq-subtitle {
            font-size: 1.1rem;
            color: #8b949e;
            margin-top: 0.3rem;
            margin-bottom: 1.5rem;
        }

        /* ---- Module cards on home page ---- */
        .module-card {
            background-color: #161b22;
            border: 1px solid #30363d;
            border-radius: 10px;
            padding: 1rem 1.2rem;
            margin-bottom: 0.8rem;
            transition: border-color 0.2s;
        }
        .module-card:hover {
            border-color: #58a6ff;
        }

        /* ---- Status badges ---- */
        .badge-green {
            background-color: #238636;
            color: white;
            border-radius: 20px;
            padding: 2px 10px;
            font-size: 0.78rem;
            font-weight: 600;
        }
        .badge-yellow {
            background-color: #d29922;
            color: white;
            border-radius: 20px;
            padding: 2px 10px;
            font-size: 0.78rem;
            font-weight: 600;
        }
        .badge-red {
            background-color: #da3633;
            color: white;
            border-radius: 20px;
            padding: 2px 10px;
            font-size: 0.78rem;
            font-weight: 600;
        }

        /* ---- Divider ---- */
        hr {
            border-color: #30363d;
        }

        /* ---- Metrics ---- */
        [data-testid="metric-container"] {
            background-color: #161b22;
            border: 1px solid #30363d;
            border-radius: 8px;
            padding: 0.8rem;
        }

        /* ---- Text inputs / select boxes ---- */
        .stTextInput > div > div > input,
        .stSelectbox > div > div,
        .stTextArea > div > div > textarea {
            background-color: #0d1117;
            color: #c9d1d9;
            border: 1px solid #30363d;
            border-radius: 6px;
        }
    </style>
    """, unsafe_allow_html=True)

    # ------------------------------------------------------------------ #
    # SIDEBAR — Navigation (same on every page)
    # ------------------------------------------------------------------ #
    with st.sidebar:
        st.markdown("## 🔬 ForensiQ")
        st.markdown("**Forensic Intelligence System**")
        st.markdown("---")
        st.markdown("### 📂 Navigation")

        st.page_link("app.py",                      label="🏠 Home Dashboard")
        st.page_link("pages/case_manager.py",        label="📋 Case Manager")
        st.page_link("pages/report_analyzer.py",     label="📄 Report Analyzer")
        st.page_link("pages/tod_estimator.py",       label="⏱️ TOD Estimator")
        st.page_link("pages/cctv_tracker.py",        label="📷 CCTV Tracker")
        st.page_link("pages/pattern_engine.py",      label="🔗 Pattern Engine")
        st.page_link("pages/forensic_profiler.py",   label="🧬 Forensic Profiler")
        st.page_link("pages/risk_scorer.py",         label="⚠️ Risk Scorer")
        st.page_link("pages/dashboard.py",           label="📊 Analytics Dashboard")

        st.markdown("---")
        st.markdown(
            "<small style='color:#8b949e'>Powered by Featherless AI<br>"
            "Model: Llama-3.3-70B-Instruct</small>",
            unsafe_allow_html=True
        )