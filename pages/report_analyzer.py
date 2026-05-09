# pages/report_analyzer.py — ForensiQ Forensic Report Analyzer (Session 3)

import streamlit as st
import os
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ── Page config MUST be the very first Streamlit call ──────
st.set_page_config(
    page_title="ForensiQ — Report Analyzer",
    page_icon="🔬",
    layout="wide"
)

from theme import apply_theme
apply_theme(active_page="Report Analyzer")

from openai import OpenAI
from database import (
    get_all_cases,
    insert_autopsy_report,
    insert_witness_statement,
)

# PyMuPDF — imported as fitz
try:
    import fitz
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False


# ══════════════════════════════════════════════════════════════
# SESSION STATE INITIALISATION
# ══════════════════════════════════════════════════════════════

_defaults = {
    "ra_autopsy_result":    None,
    "ra_autopsy_raw_text":  None,
    "ra_autopsy_file_name": None,
    "ra_autopsy_saved":     False,
    "ra_witness_result":    None,
    "ra_witness_raw_text":  None,
    "ra_witness_saved":     False,
}
for k, v in _defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ══════════════════════════════════════════════════════════════
# CUSTOM CSS
# ══════════════════════════════════════════════════════════════

st.markdown("""
<style>
/* ── SOAP Cards ─────────────────────────────────────────── */
.soap-card {
    background: #0d1117;
    border-radius: 10px;
    padding: 20px 24px;
    margin: 10px 0 14px 0;
    border-left: 5px solid;
    font-family: 'Courier New', monospace;
}
.soap-s { border-color: #00d4ff; }
.soap-o { border-color: #00ff88; }
.soap-a { border-color: #ff8800; }
.soap-p { border-color: #ff4444; }

.soap-tag {
    font-size: 11px;
    font-weight: bold;
    letter-spacing: 3px;
    font-family: 'Courier New', monospace;
}
.soap-s .soap-tag { color: #00d4ff; }
.soap-o .soap-tag { color: #00ff88; }
.soap-a .soap-tag { color: #ff8800; }
.soap-p .soap-tag { color: #ff4444; }

.soap-subtitle {
    color: #555;
    font-size: 11px;
    font-family: 'Courier New', monospace;
    margin: 3px 0 10px 0;
}
.soap-body {
    color: #c9d1d9;
    font-size: 14px;
    line-height: 1.75;
    font-family: 'Courier New', monospace;
}

/* ── Forensic Term Cards ─────────────────────────────────── */
.fterm-card {
    background: #161b22;
    border: 1px solid #21262d;
    border-radius: 8px;
    padding: 14px 16px;
    margin: 6px 0;
    min-height: 70px;
}
.fterm-label {
    color: #00d4ff;
    font-size: 10px;
    font-weight: bold;
    letter-spacing: 2px;
    font-family: 'Courier New', monospace;
    margin-bottom: 6px;
}
.fterm-value {
    font-size: 13px;
    font-family: 'Courier New', monospace;
    line-height: 1.5;
}

/* ── Witness Analysis Items ──────────────────────────────── */
.timeline-item {
    background: #0d1117;
    border-left: 3px solid #00d4ff;
    padding: 9px 14px;
    margin: 5px 0;
    border-radius: 0 6px 6px 0;
    color: #c9d1d9;
    font-family: 'Courier New', monospace;
    font-size: 13px;
}
.people-item {
    background: #0d1117;
    border-left: 3px solid #00ff88;
    padding: 9px 14px;
    margin: 5px 0;
    border-radius: 0 6px 6px 0;
    color: #c9d1d9;
    font-family: 'Courier New', monospace;
    font-size: 13px;
}
.location-item {
    background: #0d1117;
    border-left: 3px solid #ff8800;
    padding: 9px 14px;
    margin: 5px 0;
    border-radius: 0 6px 6px 0;
    color: #c9d1d9;
    font-family: 'Courier New', monospace;
    font-size: 13px;
}
.object-item {
    background: #161b22;
    border: 1px solid #21262d;
    border-radius: 8px;
    padding: 10px 14px;
    margin: 5px 0;
    color: #c9d1d9;
    font-family: 'Courier New', monospace;
    font-size: 13px;
}
.contradiction-item {
    background: #200a0a;
    border: 1px solid #ff4444;
    border-radius: 8px;
    padding: 11px 16px;
    margin: 6px 0;
    color: #ff8888;
    font-family: 'Courier New', monospace;
    font-size: 13px;
    line-height: 1.6;
}
.crossref-item {
    background: #0d1117;
    border-left: 3px solid #a371f7;
    padding: 9px 14px;
    margin: 5px 0;
    border-radius: 0 6px 6px 0;
    color: #c9d1d9;
    font-family: 'Courier New', monospace;
    font-size: 13px;
}
.reliability-card {
    background: #0d1117;
    border: 1px solid #30363d;
    border-radius: 10px;
    padding: 16px 20px;
    color: #e6edf3;
    font-family: 'Courier New', monospace;
    font-size: 13px;
    line-height: 1.75;
}

/* ── Section Header ──────────────────────────────────────── */
.ra-section-hdr {
    color: #00d4ff;
    font-family: 'Courier New', monospace;
    font-size: 12px;
    font-weight: bold;
    letter-spacing: 3px;
    border-bottom: 1px solid #21262d;
    padding-bottom: 8px;
    margin: 24px 0 12px 0;
}

/* ── Disclaimer Banner ───────────────────────────────────── */
.disclaimer {
    background: #1a1200;
    border: 1px solid #ff8800;
    border-radius: 8px;
    padding: 13px 18px;
    color: #ffa040;
    font-family: 'Courier New', monospace;
    font-size: 12px;
    text-align: center;
    margin: 22px 0;
    line-height: 1.6;
}

/* ── No-Result Placeholder ───────────────────────────────── */
.no-result {
    color: #555;
    font-family: 'Courier New', monospace;
    font-size: 13px;
    padding: 8px 0;
}
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════
# HELPER: AI CLIENT
# ══════════════════════════════════════════════════════════════

def get_client():
    api_key = os.getenv("FEATHERLESS_API_KEY")
    if not api_key:
        st.error("❌ FEATHERLESS_API_KEY not found in your .env file.")
        return None
    return OpenAI(
        api_key=api_key,
        base_url="https://api.featherless.ai/v1"
    )


# ══════════════════════════════════════════════════════════════
# HELPER: EXTRACT TEXT FROM UPLOADED FILE
# ══════════════════════════════════════════════════════════════

def extract_text(uploaded_file) -> str:
    name = uploaded_file.name.lower()
    if name.endswith(".pdf"):
        if not PYMUPDF_AVAILABLE:
            st.error("❌ PyMuPDF is not installed. Run: pip install PyMuPDF")
            return ""
        pdf_bytes = uploaded_file.read()
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
        return text
    else:
        return uploaded_file.read().decode("utf-8", errors="replace")


# ══════════════════════════════════════════════════════════════
# HELPER: SAFELY PARSE JSON FROM AI RESPONSE
# ══════════════════════════════════════════════════════════════

def safe_parse_json(raw: str) -> dict:
    """
    Strips markdown fences and extracts the first JSON object found.
    Returns a dict or raises json.JSONDecodeError.
    """
    text = raw.strip()

    # Remove ```json ... ``` or ``` ... ``` fences
    if "```" in text:
        lines = text.split("\n")
        cleaned = []
        skip = False
        for line in lines:
            if line.strip().startswith("```"):
                skip = not skip
                continue
            if not skip:
                cleaned.append(line)
        text = "\n".join(cleaned).strip()

    # Find the outermost { ... }
    start = text.find("{")
    end = text.rfind("}") + 1
    if start != -1 and end > start:
        text = text[start:end]

    return json.loads(text)


# ══════════════════════════════════════════════════════════════
# AI CALL: AUTOPSY ANALYSIS
# ══════════════════════════════════════════════════════════════

def analyze_autopsy_report(report_text: str):
    client = get_client()
    if not client:
        return None

    system_prompt = (
        "You are Dr. FORENSIQ, a board-certified forensic pathologist AI. "
        "You analyze autopsy reports and extract structured findings for law enforcement. "
        "ABSOLUTE RULE: Your ENTIRE response must be ONE valid JSON object only. "
        "Do NOT include any text before or after the JSON. "
        "Do NOT use markdown fences. Do NOT explain anything. Pure JSON only."
    )

    user_prompt = f"""Analyze the autopsy report below and return ONLY this exact JSON structure.
Fill every field with real content extracted from the report. Do not leave placeholders.

{{
  "soap": {{
    "subjective": "2–4 sentences: circumstances of discovery, who found the body, where and when, reported history, background given to the medical examiner.",
    "objective": "3–6 sentences: ALL physical findings with exact measurements — body weight, height, temperature at discovery, lividity pattern and fixation status, rigor mortis state, every injury with location and description, all toxicology values and lab results.",
    "assessment": "2–4 sentences: official cause of death, manner of death classification (Homicide / Suicide / Accidental / Natural / Undetermined), key forensic conclusions, medical examiner interpretation.",
    "plan": "2–4 sentences: specific follow-up actions recommended for investigators, anomalies requiring verification, additional tests needed, areas investigators must examine."
  }},
  "forensic_terms": {{
    "injury_type": "All injury types found, comma-separated (e.g. blunt force trauma, ligature strangulation, incised wounds)",
    "body_location": "All body regions with significant findings",
    "weapon_type": "Most probable weapon or mechanism, or Undetermined",
    "defensive_wounds": "Yes / No / Inconclusive",
    "signs_of_struggle": "Yes / No / Inconclusive",
    "toxicology": "All substances detected with values, or: None detected",
    "time_indicators": "Body temperature reading, lividity fixation status, rigor state, stomach content digestion, estimated post-mortem interval",
    "anomalies": "Unusual, unexpected, or notable findings that investigators must examine further"
  }}
}}

AUTOPSY REPORT TEXT:
{report_text[:8000]}
"""

    try:
        resp = client.chat.completions.create(
            model="meta-llama/Llama-3.3-70B-Instruct",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            max_tokens=2000,
            temperature=0.1,
        )
        raw = resp.choices[0].message.content
        return safe_parse_json(raw)

    except json.JSONDecodeError as e:
        st.error(f"❌ The AI returned badly formatted data. Please click Analyze again. (Error: {e})")
        with st.expander("🐛 Raw AI Response — for debugging"):
            st.code(raw, language="text")
        return None
    except Exception as e:
        st.error(f"❌ AI call failed: {e}")
        return None


# ══════════════════════════════════════════════════════════════
# AI CALL: WITNESS STATEMENT ANALYSIS
# ══════════════════════════════════════════════════════════════

def analyze_witness_statement(statement_text: str):
    client = get_client()
    if not client:
        return None

    system_prompt = (
        "You are FORENSIQ Intelligence, a specialist forensic statement analyst. "
        "You extract structured information and flag inconsistencies in witness statements. "
        "ABSOLUTE RULE: Your ENTIRE response must be ONE valid JSON object only. "
        "Do NOT use markdown. Do NOT add any text outside the JSON. Pure JSON only."
    )

    user_prompt = f"""Analyze the witness statement below. Return ONLY this JSON.
Every array must contain real items from the statement. Use [] only if truly nothing found.

{{
  "timeline": [
    "Each event the witness describes, in chronological order. Format: 'TIME — Description'. Use 'Approx. TIME' if no exact time given."
  ],
  "key_people": [
    "Every person mentioned. Format: 'Name or description — role or relationship to witness'"
  ],
  "key_locations": [
    "Every specific location or address mentioned"
  ],
  "key_objects": [
    "Every significant object, vehicle, weapon, or item mentioned"
  ],
  "contradictions": [
    "Every internal contradiction, inconsistency, implausibility, suspicious vagueness, or changed story. Be specific — quote the conflicting details directly."
  ],
  "emotional_reliability": "Describe witness emotional state and delivery style. Assign a rating — High / Medium / Low / Unreliable — with a one-sentence explanation of why.",
  "cross_references": [
    "Possible connections to physical evidence or forensic findings. Format: 'Witness claims X — this could confirm or conflict with Y'"
  ]
}}

WITNESS STATEMENT:
{statement_text[:6000]}
"""

    try:
        resp = client.chat.completions.create(
            model="meta-llama/Llama-3.3-70B-Instruct",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            max_tokens=1500,
            temperature=0.1,
        )
        raw = resp.choices[0].message.content
        return safe_parse_json(raw)

    except json.JSONDecodeError as e:
        st.error(f"❌ The AI returned badly formatted data. Click Analyze again. (Error: {e})")
        with st.expander("🐛 Raw AI Response — for debugging"):
            st.code(raw, language="text")
        return None
    except Exception as e:
        st.error(f"❌ AI call failed: {e}")
        return None


# ══════════════════════════════════════════════════════════════
# DISPLAY HELPERS
# ══════════════════════════════════════════════════════════════

def show_section(label: str):
    st.markdown(f'<div class="ra-section-hdr">{label}</div>', unsafe_allow_html=True)


def show_soap(soap: dict):
    entries = [
        ("S — SUBJECTIVE",    "soap-s", "Circumstances of Discovery & Reported Background"),
        ("O — OBJECTIVE",     "soap-o", "Physical Findings, Measurements & Lab Results"),
        ("A — ASSESSMENT",    "soap-a", "Cause of Death & Forensic Conclusions"),
        ("P — PLAN / FLAGS",  "soap-p", "Recommended Investigations & Follow-Up Actions"),
    ]
    keys = ["subjective", "objective", "assessment", "plan"]

    for (title, cls, subtitle), key in zip(entries, keys):
        text = soap.get(key, "Not extracted.")
        st.markdown(f"""
        <div class="soap-card {cls}">
            <div class="soap-tag">{title}</div>
            <div class="soap-subtitle">{subtitle}</div>
            <div class="soap-body">{text}</div>
        </div>
        """, unsafe_allow_html=True)


def show_forensic_terms(ft: dict):
    fields = [
        ("injury_type",       "🩸 INJURY TYPE"),
        ("body_location",     "📍 BODY LOCATION"),
        ("weapon_type",       "🔪 PROBABLE WEAPON"),
        ("defensive_wounds",  "🛡️ DEFENSIVE WOUNDS"),
        ("signs_of_struggle", "⚡ SIGNS OF STRUGGLE"),
        ("toxicology",        "🧪 TOXICOLOGY"),
        ("time_indicators",   "⏱️ TIME INDICATORS"),
        ("anomalies",         "⚠️ ANOMALIES"),
    ]

    col_a, col_b = st.columns(2)
    columns = [col_a, col_b]

    for i, (key, label) in enumerate(fields):
        value = ft.get(key, "Not extracted.")

        # Colour-code Yes/No/Inconclusive values
        if value.strip().lower() == "yes":
            colour = "#ff4444"
        elif value.strip().lower() == "no":
            colour = "#00ff88"
        elif "inconclusive" in value.strip().lower():
            colour = "#ff8800"
        else:
            colour = "#e6edf3"

        with columns[i % 2]:
            st.markdown(f"""
            <div class="fterm-card">
                <div class="fterm-label">{label}</div>
                <div class="fterm-value" style="color:{colour};">{value}</div>
            </div>
            """, unsafe_allow_html=True)


def show_list(items: list, css_class: str, prefix: str = "", empty: str = "None identified."):
    if not items:
        st.markdown(f'<div class="no-result">{empty}</div>', unsafe_allow_html=True)
        return
    for item in items:
        st.markdown(
            f'<div class="{css_class}">{prefix}{item}</div>',
            unsafe_allow_html=True
        )


def show_contradictions(items: list):
    if not items:
        st.markdown("""
        <div class="fterm-card">
            <div class="fterm-value" style="color:#00ff88;">
                ✅ No contradictions identified in this statement.
            </div>
        </div>
        """, unsafe_allow_html=True)
        return
    for item in items:
        st.markdown(
            f'<div class="contradiction-item">⚠️ {item}</div>',
            unsafe_allow_html=True
        )


def show_disclaimer():
    st.markdown("""
    <div class="disclaimer">
        ⚠️&nbsp; AI-ASSISTED ANALYSIS — All findings must be verified by a certified forensic pathologist or
        qualified investigator.<br>
        This analysis is not admissible as standalone legal evidence and must not replace official examination.
    </div>
    """, unsafe_allow_html=True)


def case_selector(key_suffix: str):
    """Returns (case_options dict, selected_case_id str) or (None, None) if no cases."""
    all_cases = get_all_cases()
    if not all_cases:
        st.warning(
            "⚠️ No cases exist yet. Go to **Case Manager** to create a case first, "
            "then come back here to save."
        )
        return None, None

    options = {
        f"{c['case_id']}  —  {c.get('victim_name', 'Unknown Victim')}": c["case_id"]
        for c in all_cases
    }
    label = st.selectbox(
        "Link this analysis to a case:",
        list(options.keys()),
        key=f"case_select_{key_suffix}"
    )
    return options, options[label]


# ══════════════════════════════════════════════════════════════
# PAGE HEADER
# ══════════════════════════════════════════════════════════════

st.markdown("""
<h1 style="
    color: #00d4ff;
    font-family: 'Courier New', monospace;
    letter-spacing: 2px;
    margin-bottom: 2px;
">🔬 FORENSIC REPORT ANALYZER</h1>
<p style="
    color: #8b949e;
    font-family: 'Courier New', monospace;
    font-size: 13px;
    margin-top: 0;
">AI-powered structured extraction from autopsy reports and witness statements  ·  Powered by Featherless AI</p>
""", unsafe_allow_html=True)

st.divider()


# ══════════════════════════════════════════════════════════════
# TABS
# ══════════════════════════════════════════════════════════════

tab1, tab2 = st.tabs(["  📋  Autopsy Report Analyzer  ", "  👁️  Witness Statement Analyzer  "])


# ──────────────────────────────────────────────────────────────
# TAB 1 — AUTOPSY REPORT ANALYZER
# ──────────────────────────────────────────────────────────────

with tab1:

    show_section("📂 UPLOAD AUTOPSY REPORT")
    st.caption("Accepted formats: PDF (text-based, not scanned) or TXT")

    uploaded = st.file_uploader(
        "Drop the report here or click Browse",
        type=["pdf", "txt"],
        key="ra_autopsy_uploader",
        label_visibility="collapsed",
    )

    if uploaded:
        st.success(f"✅  File loaded: **{uploaded.name}**  ({round(uploaded.size / 1024, 1)} KB)")

        col_analyze, col_clear, _ = st.columns([1.2, 0.8, 5])

        with col_analyze:
            do_analyze = st.button(
                "🔬  ANALYZE REPORT",
                type="primary",
                key="ra_btn_analyze_autopsy",
                use_container_width=True,
            )
        with col_clear:
            if st.button("🗑️  Clear", key="ra_btn_clear_autopsy", use_container_width=True):
                st.session_state.ra_autopsy_result    = None
                st.session_state.ra_autopsy_raw_text  = None
                st.session_state.ra_autopsy_file_name = None
                st.session_state.ra_autopsy_saved     = False
                st.rerun()

        if do_analyze:
            with st.spinner("🔬  FORENSIQ AI is reading the report — please wait..."):
                raw_text = extract_text(uploaded)

            if len(raw_text.strip()) < 80:
                st.error(
                    "❌ Could not extract readable text from this file. "
                    "If it is a scanned image PDF, please re-save it as a TXT file and upload that instead."
                )
            else:
                with st.spinner("🧠  AI is extracting forensic findings..."):
                    result = analyze_autopsy_report(raw_text)
                if result:
                    st.session_state.ra_autopsy_result    = result
                    st.session_state.ra_autopsy_raw_text  = raw_text
                    st.session_state.ra_autopsy_file_name = uploaded.name
                    st.session_state.ra_autopsy_saved     = False

    # ── Results display ────────────────────────────────────────
    if st.session_state.ra_autopsy_result:
        result = st.session_state.ra_autopsy_result
        soap   = result.get("soap", {})
        ft     = result.get("forensic_terms", {})

        # ── SOAP ───────────────────────────────────────────────
        show_section("📊 SOAP ANALYSIS")
        show_soap(soap)

        # ── Forensic Terms ─────────────────────────────────────
        show_section("🔑 KEY FORENSIC TERMS")
        show_forensic_terms(ft)

        # ── Disclaimer ─────────────────────────────────────────
        show_disclaimer()

        # ── Raw text (collapsible) ─────────────────────────────
        with st.expander("📄 View Extracted Raw Text"):
            st.text_area(
                "",
                value=st.session_state.ra_autopsy_raw_text or "",
                height=220,
                disabled=True,
                key="ra_raw_text_autopsy"
            )

        # ── Save to Case ────────────────────────────────────────
        show_section("💾 SAVE TO CASE")

        options, selected_id = case_selector("autopsy")

        if options and selected_id:
            if st.session_state.ra_autopsy_saved:
                st.success("✅  This autopsy analysis has already been saved.")
            else:
                if st.button("💾  Save Autopsy Analysis", type="primary", key="ra_save_autopsy"):
                    insert_autopsy_report({
                        "case_id":           selected_id,
                        "file_name":         st.session_state.ra_autopsy_file_name or "unknown",
                        "raw_text":          st.session_state.ra_autopsy_raw_text  or "",
                        "soap_subjective":   soap.get("subjective",   ""),
                        "soap_objective":    soap.get("objective",    ""),
                        "soap_assessment":   soap.get("assessment",   ""),
                        "soap_plan":         soap.get("plan",         ""),
                        "injury_type":       ft.get("injury_type",       ""),
                        "body_location":     ft.get("body_location",     ""),
                        "weapon_type":       ft.get("weapon_type",       ""),
                        "defensive_wounds":  ft.get("defensive_wounds",  ""),
                        "signs_of_struggle": ft.get("signs_of_struggle", ""),
                        "toxicology":        ft.get("toxicology",        ""),
                        "time_indicators":   ft.get("time_indicators",   ""),
                        "anomalies":         ft.get("anomalies",         ""),
                    })
                    st.session_state.ra_autopsy_saved = True
                    st.success(f"✅  Autopsy analysis saved to case **{selected_id}**!")
                    st.balloons()


# ──────────────────────────────────────────────────────────────
# TAB 2 — WITNESS STATEMENT ANALYZER
# ──────────────────────────────────────────────────────────────

with tab2:

    show_section("👤 WITNESS DETAILS")

    witness_name = st.text_input(
        "Witness Name  (optional — used for record-keeping only)",
        placeholder="e.g.  Marcus Webb",
        key="ra_witness_name",
    )

    show_section("📝 STATEMENT INPUT")

    input_method = st.radio(
        "Choose input method:",
        ["📝  Paste text directly", "📁  Upload a TXT file"],
        horizontal=True,
        key="ra_witness_method",
    )

    witness_text = ""

    if input_method == "📝  Paste text directly":
        witness_text = st.text_area(
            "Paste the full witness statement here:",
            height=260,
            placeholder="Paste the complete statement text...",
            key="ra_witness_paste",
        )

    else:
        w_file = st.file_uploader(
            "Upload statement TXT file:",
            type=["txt"],
            key="ra_witness_uploader",
        )
        if w_file:
            witness_text = w_file.read().decode("utf-8", errors="replace")
            st.success(f"✅  File loaded: **{w_file.name}**")
            with st.expander("🔍 Preview Statement (first 800 characters)"):
                st.text(witness_text[:800] + ("…" if len(witness_text) > 800 else ""))

    col_w1, col_w2, _ = st.columns([1.5, 0.8, 5])

    with col_w1:
        do_witness = st.button(
            "👁️  ANALYZE STATEMENT",
            type="primary",
            key="ra_btn_analyze_witness",
            use_container_width=True,
        )
    with col_w2:
        if st.button("🗑️  Clear", key="ra_btn_clear_witness", use_container_width=True):
            st.session_state.ra_witness_result    = None
            st.session_state.ra_witness_raw_text  = None
            st.session_state.ra_witness_saved     = False
            st.rerun()

    if do_witness:
        if not witness_text.strip():
            st.error("❌ Please paste a statement or upload a TXT file before clicking Analyze.")
        elif len(witness_text.strip()) < 40:
            st.error("❌ Statement is too short. Please provide the complete witness statement.")
        else:
            with st.spinner("👁️  FORENSIQ AI is analyzing the statement..."):
                result = analyze_witness_statement(witness_text)
            if result:
                st.session_state.ra_witness_result   = result
                st.session_state.ra_witness_raw_text = witness_text
                st.session_state.ra_witness_saved    = False

    # ── Witness Results ─────────────────────────────────────────
    if st.session_state.ra_witness_result:
        wr = st.session_state.ra_witness_result

        # Timeline
        show_section("📅 CHRONOLOGICAL TIMELINE")
        show_list(wr.get("timeline", []), "timeline-item", empty="No timeline events extracted.")

        # People & Locations side by side
        col_people, col_locs = st.columns(2)

        with col_people:
            show_section("👥 KEY PEOPLE MENTIONED")
            show_list(wr.get("key_people", []), "people-item", empty="No key people identified.")

        with col_locs:
            show_section("📍 KEY LOCATIONS MENTIONED")
            show_list(wr.get("key_locations", []), "location-item", empty="No locations identified.")

        # Objects
        show_section("📦 KEY OBJECTS & VEHICLES")
        objects = wr.get("key_objects", [])
        if objects:
            obj_cols = st.columns(min(len(objects), 3))
            for i, obj in enumerate(objects):
                with obj_cols[i % 3]:
                    st.markdown(
                        f'<div class="object-item">🔹 {obj}</div>',
                        unsafe_allow_html=True
                    )
        else:
            st.markdown('<div class="no-result">No significant objects mentioned.</div>', unsafe_allow_html=True)

        # Contradictions — always shown prominently
        show_section("⚠️ CONTRADICTIONS & INCONSISTENCIES")
        show_contradictions(wr.get("contradictions", []))

        # Reliability
        show_section("🧠 EMOTIONAL RELIABILITY ASSESSMENT")
        reliability = wr.get("emotional_reliability", "Not assessed.")
        st.markdown(
            f'<div class="reliability-card">🧠 {reliability}</div>',
            unsafe_allow_html=True
        )

        # Cross-references
        cross = wr.get("cross_references", [])
        if cross:
            show_section("🔗 CROSS-REFERENCE POINTS")
            show_list(cross, "crossref-item", prefix="🔗 ", empty="No cross-reference points identified.")

        # Disclaimer
        show_disclaimer()

        # Save to Case
        show_section("💾 SAVE TO CASE")
        options_w, selected_id_w = case_selector("witness")

        if options_w and selected_id_w:
            if st.session_state.ra_witness_saved:
                st.success("✅  This statement analysis has already been saved.")
            else:
                if st.button("💾  Save Statement Analysis", type="primary", key="ra_save_witness"):
                    insert_witness_statement({
                        "case_id":               selected_id_w,
                        "witness_name":          witness_name or "Unknown",
                        "raw_statement":         st.session_state.ra_witness_raw_text or "",
                        "timeline":              json.dumps(wr.get("timeline",      [])),
                        "key_people":            json.dumps(wr.get("key_people",    [])),
                        "key_locations":         json.dumps(wr.get("key_locations", [])),
                        "key_objects":           json.dumps(wr.get("key_objects",   [])),
                        "contradictions":        json.dumps(wr.get("contradictions",[])),
                        "emotional_reliability": wr.get("emotional_reliability", ""),
                        "cross_references":      json.dumps(wr.get("cross_references", [])),
                    })
                    st.session_state.ra_witness_saved = True
                    st.success(f"✅  Statement saved to case **{selected_id_w}**!")
                    st.balloons()