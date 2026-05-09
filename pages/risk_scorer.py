# pages/risk_scorer.py
# ForensiQ — Session 9: Risk Scorer
# Aggregates all case evidence → AI risk assessment → Plotly gauge → DB save

import os
import json
import re
import sqlite3
import streamlit as st
import plotly.graph_objects as go
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

from theme import apply_theme
from database import (
    get_connection,
    get_all_cases,
    get_case_by_id,
    get_autopsy_by_case,
    get_witnesses_by_case,
    get_tod_by_case,
    get_cctv_by_case,
    get_suspects_by_case,
    insert_risk_score,
    get_risk_score_by_case,
    _normalize_case,
)

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="ForensiQ — Risk Scorer",
    page_icon="⚠️",
    layout="wide",
)
apply_theme()

# ── Featherless AI client ──────────────────────────────────────────────────────
client = OpenAI(
    api_key=os.getenv("FEATHERLESS_API_KEY"),
    base_url="https://api.featherless.ai/v1",
)
MODEL = "meta-llama/Llama-3.3-70B-Instruct"


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def row_to_dict(row):
    """Safely convert a sqlite3.Row or plain tuple to dict."""
    if row is None:
        return {}
    try:
        return dict(row)
    except Exception:
        return {}


def fetch_tod_dict(case_id: str) -> dict:
    """
    Fetch TOD via row_factory so columns are accessible by name.
    Mirrors the pattern in forensic_profiler.py.
    """
    try:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM tod_estimates WHERE case_id = ? ORDER BY created_at DESC LIMIT 1",
            (case_id,),
        )
        row = cur.fetchone()
        conn.close()
        if row:
            return dict(row)
        return {}
    except Exception:
        return {}


def clean_json_string(raw: str) -> str:
    """Strip markdown fences, extract outermost {}, remove trailing commas."""
    raw = re.sub(r"```(?:json)?", "", raw).strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1:
        raw = raw[start : end + 1]
    raw = re.sub(r",\s*([}\]])", r"\1", raw)
    raw = raw.replace("\n", " ").replace("\r", " ")
    return raw


def risk_color(category: str) -> str:
    mapping = {
        "low": "#28a745",
        "medium": "#ffc107",
        "high": "#fd7e14",
        "critical": "#dc3545",
    }
    return mapping.get(category.lower(), "#6c757d")


def speedometer_gauge(score: int, title: str = "Risk Score", size: int = 350) -> go.Figure:
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=score,
            title={"text": title, "font": {"size": 18}},
            number={"font": {"size": 48}},
            gauge={
                "axis": {"range": [0, 100], "tickwidth": 1},
                "bar": {"color": "#e63946"},
                "steps": [
                    {"range": [0, 25], "color": "#d4edda"},
                    {"range": [25, 50], "color": "#fff3cd"},
                    {"range": [50, 75], "color": "#ffe5b4"},
                    {"range": [75, 100], "color": "#f8d7da"},
                ],
                "threshold": {
                    "line": {"color": "#e63946", "width": 4},
                    "thickness": 0.75,
                    "value": score,
                },
            },
        )
    )
    fig.update_layout(
        height=size,
        margin=dict(t=40, b=10, l=20, r=20),
        paper_bgcolor="rgba(0,0,0,0)",
        font_color="#f0f0f0",
    )
    return fig


def mini_gauge(value: int, label: str) -> go.Figure:
    color = (
        "#28a745" if value >= 70
        else "#ffc107" if value >= 40
        else "#dc3545"
    )
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=value,
            title={"text": label, "font": {"size": 13}},
            number={"font": {"size": 28}, "suffix": "%"},
            gauge={
                "axis": {"range": [0, 100]},
                "bar": {"color": color},
                "bgcolor": "rgba(0,0,0,0)",
            },
        )
    )
    fig.update_layout(
        height=200,
        margin=dict(t=30, b=0, l=10, r=10),
        paper_bgcolor="rgba(0,0,0,0)",
        font_color="#f0f0f0",
    )
    return fig


# ══════════════════════════════════════════════════════════════════════════════
# EVIDENCE COLLECTION
# ══════════════════════════════════════════════════════════════════════════════

def collect_all_evidence(case_id: str) -> dict:
    """Pull every evidence type for a case and return a single dict."""
    evidence = {}

    # Autopsy
    try:
        autopsy_row = get_autopsy_by_case(case_id)
        evidence["autopsy"] = row_to_dict(autopsy_row) if autopsy_row else {}
    except Exception:
        evidence["autopsy"] = {}

    # Witnesses
    try:
        witness_rows = get_witnesses_by_case(case_id)
        evidence["witnesses"] = [row_to_dict(w) for w in witness_rows] if witness_rows else []
    except Exception:
        evidence["witnesses"] = []

    # TOD
    evidence["tod"] = fetch_tod_dict(case_id)

    # CCTV sightings
    try:
        cctv_rows = get_cctv_by_case(case_id)
        evidence["cctv"] = [row_to_dict(c) for c in cctv_rows] if cctv_rows else []
    except Exception:
        evidence["cctv"] = []

    # Suspects
    try:
        suspect_rows = get_suspects_by_case(case_id)
        evidence["suspects"] = [row_to_dict(s) for s in suspect_rows] if suspect_rows else []
    except Exception:
        evidence["suspects"] = []

    return evidence


def summarise_evidence(ev: dict) -> str:
    """Convert evidence dict into a readable text block for the AI prompt."""
    lines = []

    # Autopsy
    a = ev.get("autopsy", {})
    if a:
        lines.append("=== AUTOPSY / FORENSIC REPORT ===")
        for key in ["cause_of_death", "manner_of_death", "injuries", "toxicology",
                    "soap_subjective", "soap_objective", "soap_assessment", "soap_plan",
                    "key_terms", "findings"]:
            val = a.get(key, "")
            if val:
                lines.append(f"  {key.replace('_',' ').title()}: {val}")
    else:
        lines.append("=== AUTOPSY: Not available ===")

    # Witnesses
    lines.append("\n=== WITNESS STATEMENTS ===")
    witnesses = ev.get("witnesses", [])
    if witnesses:
        for i, w in enumerate(witnesses, 1):
            name = w.get("witness_name") or w.get("name", f"Witness {i}")
            stmt = w.get("statement", "")
            reliability = w.get("reliability_score", w.get("reliability", "N/A"))
            contradictions = w.get("contradictions", "")
            lines.append(f"  Witness {i} — {name}")
            lines.append(f"    Statement: {stmt[:300]}")
            lines.append(f"    Reliability: {reliability}")
            if contradictions:
                lines.append(f"    Contradictions: {contradictions}")
    else:
        lines.append("  No witness statements recorded.")

    # TOD
    lines.append("\n=== TIME OF DEATH ESTIMATE ===")
    tod = ev.get("tod", {})
    if tod:
        for key in ["estimated_tod", "time_window_start", "time_window_end",
                    "confidence_score", "method_used", "notes"]:
            val = tod.get(key, "")
            if val:
                lines.append(f"  {key.replace('_',' ').title()}: {val}")
    else:
        lines.append("  No TOD estimate recorded.")

    # CCTV
    lines.append("\n=== CCTV SIGHTINGS ===")
    cctv = ev.get("cctv", [])
    if cctv:
        for i, s in enumerate(cctv, 1):
            lines.append(
                f"  Sighting {i} — {s.get('timestamp','')} at {s.get('location','')} "
                f"| Confidence: {s.get('confidence','')} "
                f"| {s.get('description','')}"
            )
            notes = s.get("notes", "")
            if notes:
                lines.append(f"    Flags/Notes: {notes}")
    else:
        lines.append("  No CCTV sightings recorded.")

    # Suspects
    lines.append("\n=== SUSPECTS ===")
    suspects = ev.get("suspects", [])
    if suspects:
        for i, s in enumerate(suspects, 1):
            name = s.get("suspect_name") or s.get("name", f"Suspect {i}")
            priority = s.get("priority_rank", s.get("priority", ""))
            motive = s.get("motive", "")
            alibi = s.get("alibi", "")
            lines.append(f"  Suspect {i} — {name} | Priority: {priority}")
            if motive:
                lines.append(f"    Motive: {motive}")
            if alibi:
                lines.append(f"    Alibi: {alibi}")
    else:
        lines.append("  No suspects recorded.")

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# AI RISK ASSESSMENT
# ══════════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """You are ForensiQ Risk Engine, a forensic intelligence AI embedded in a
homicide investigation platform. You receive a structured evidence bundle for a case and
perform a rigorous risk assessment.

Return ONLY a valid JSON object — no markdown, no commentary, no trailing commas.

JSON schema:
{
  "risk_score": <integer 0-100>,
  "risk_category": "<Low|Medium|High|Critical>",
  "confidence_in_score": <integer 0-100>,
  "top_red_flags": [
    {"flag": "<specific anomaly>", "implication": "<what it means for the investigation>"},
    ... (exactly 5 items)
  ],
  "evidence_gaps": [
    "<specific missing evidence or test>",
    ... (3-6 items)
  ],
  "recommended_actions": [
    "<numbered actionable step for investigators>",
    ... (4-7 items)
  ],
  "scoring_rationale": "<2-3 sentence explanation of the score>",
  "evidence_quality": {
    "physical": <integer 0-100>,
    "witness": <integer 0-100>,
    "digital": <integer 0-100>
  }
}

Scoring guidance:
  0–24   Low      — minimal indicators, weak evidence, no imminent threat
  25–49  Medium   — moderate evidence, some red flags, investigation ongoing
  50–74  High     — strong indicators, significant red flags, active threat likely
  75–100 Critical — overwhelming evidence, imminent danger, urgent action required

Base the score on: evidence strength, number of red flags, witness reliability,
TOD confidence, CCTV coverage, suspect prioritisation, and evidence gaps."""


def call_ai_risk(case_title: str, evidence_summary: str, max_retries: int = 3) -> dict:
    user_msg = f"""CASE: {case_title}

{evidence_summary}

Perform a full risk assessment and return the JSON object exactly as specified."""

    for attempt in range(1, max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                temperature=0.2,
                max_tokens=1800,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
            )
            raw = response.choices[0].message.content
            cleaned = clean_json_string(raw)
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            if attempt == max_retries:
                st.error(f"AI returned invalid JSON after {max_retries} attempts: {e}")
                return {}
        except Exception as e:
            if attempt == max_retries:
                st.error(f"AI call failed: {e}")
                return {}
    return {}


# ══════════════════════════════════════════════════════════════════════════════
# UI
# ══════════════════════════════════════════════════════════════════════════════

st.title("⚠️ Forensic Risk Scorer")
st.caption("Aggregates all case evidence → AI risk assessment → actionable intelligence")

st.divider()

# ── Case selector ──────────────────────────────────────────────────────────────
all_cases = get_all_cases()
if not all_cases:
    st.warning("No cases found in the database. Please create a case first.")
    st.stop()

case_options = {}
for c in all_cases:
    nc = _normalize_case(c)
    label = f"{nc.get('case_number','?')} — {nc.get('title', nc.get('name','Untitled'))}"
    case_options[label] = nc

selected_label = st.selectbox("Select a Case", list(case_options.keys()))
selected_case = case_options[selected_label]
case_id = selected_case.get("case_id") or selected_case.get("id") or selected_case.get("case_number")
case_title = selected_case.get("title") or selected_case.get("name", "Unknown")

st.markdown(f"**Case:** `{selected_label}`")

# ── Auto-collect evidence ──────────────────────────────────────────────────────
with st.spinner("Pulling all evidence from database…"):
    evidence = collect_all_evidence(case_id)

# Evidence availability summary
col_a, col_b, col_c, col_d, col_e = st.columns(5)
col_a.metric("Autopsy", "✅" if evidence["autopsy"] else "❌")
col_b.metric("Witnesses", len(evidence["witnesses"]))
col_c.metric("TOD", "✅" if evidence["tod"] else "❌")
col_d.metric("CCTV Sightings", len(evidence["cctv"]))
col_e.metric("Suspects", len(evidence["suspects"]))

# ── Existing score banner ──────────────────────────────────────────────────────
existing = None
try:
    existing_row = get_risk_score_by_case(case_id)
    if existing_row:
        existing = row_to_dict(existing_row)
except Exception:
    pass

if existing:
    prev_score = existing.get("risk_score", existing.get("score", "N/A"))
    prev_cat = existing.get("risk_category", existing.get("category", "N/A"))
    st.info(
        f"📋 A risk score already exists for this case — "
        f"**Score: {prev_score} / 100** | **Category: {prev_cat}**  "
        f"Running a new assessment will overwrite it."
    )

st.divider()

# ── Run assessment ─────────────────────────────────────────────────────────────
run_col, _ = st.columns([2, 5])
run_btn = run_col.button("🚀 Run Risk Assessment", type="primary", use_container_width=True)

if run_btn:
    with st.spinner("Bundling evidence and consulting Featherless AI…"):
        evidence_summary = summarise_evidence(evidence)
        result = call_ai_risk(case_title, evidence_summary)

    if not result:
        st.error("Risk assessment failed. Check your API key and try again.")
        st.stop()

    # Cache in session state
    st.session_state["risk_result"] = result
    st.session_state["risk_case_id"] = case_id
    st.session_state["risk_case_title"] = case_title

# ── Display results ────────────────────────────────────────────────────────────
if "risk_result" in st.session_state and st.session_state.get("risk_case_id") == case_id:
    result = st.session_state["risk_result"]

    risk_score = int(result.get("risk_score", 0))
    risk_category = result.get("risk_category", "Unknown")
    confidence = int(result.get("confidence_in_score", 0))
    rationale = result.get("scoring_rationale", "")
    red_flags = result.get("top_red_flags", [])
    evidence_gaps = result.get("evidence_gaps", [])
    actions = result.get("recommended_actions", [])
    eq = result.get("evidence_quality", {})

    st.subheader("📊 Risk Assessment Results")

    # ── Main gauge + category badge ───────────────────────────────────────────
    gauge_col, badge_col = st.columns([3, 2])

    with gauge_col:
        st.plotly_chart(
            speedometer_gauge(risk_score, "Overall Risk Score"),
            use_container_width=True,
        )

    with badge_col:
        cat_color = risk_color(risk_category)
        st.markdown(
            f"""
            <div style="
                background:{cat_color};
                border-radius:12px;
                padding:24px 16px;
                text-align:center;
                margin-top:40px;
            ">
                <div style="font-size:14px;color:#fff;letter-spacing:2px;text-transform:uppercase;">
                    Risk Category
                </div>
                <div style="font-size:42px;font-weight:900;color:#fff;margin:8px 0;">
                    {risk_category.upper()}
                </div>
                <div style="font-size:13px;color:#fff;opacity:0.85;">
                    Confidence in Score: {confidence}%
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if rationale:
            st.markdown(f"**Scoring Rationale**")
            st.info(rationale)

    st.divider()

    # ── Evidence quality mini-gauges ──────────────────────────────────────────
    if eq:
        st.subheader("🔬 Evidence Quality Breakdown")
        qc1, qc2, qc3 = st.columns(3)
        with qc1:
            st.plotly_chart(
                mini_gauge(int(eq.get("physical", 0)), "Physical Evidence"),
                use_container_width=True,
            )
        with qc2:
            st.plotly_chart(
                mini_gauge(int(eq.get("witness", 0)), "Witness Evidence"),
                use_container_width=True,
            )
        with qc3:
            st.plotly_chart(
                mini_gauge(int(eq.get("digital", 0)), "Digital Evidence"),
                use_container_width=True,
            )

    st.divider()

    # ── Top 5 red flags ───────────────────────────────────────────────────────
    st.subheader("🚩 Top 5 Red Flags")
    if red_flags:
        for i, flag in enumerate(red_flags[:5], 1):
            with st.expander(f"🔴 Red Flag {i}: {flag.get('flag', 'N/A')}"):
                st.markdown(f"**Implication:** {flag.get('implication', 'N/A')}")
    else:
        st.info("No red flags identified.")

    # ── Evidence gaps ─────────────────────────────────────────────────────────
    st.subheader("🕳️ Evidence Gaps")
    if evidence_gaps:
        for gap in evidence_gaps:
            st.markdown(f"- {gap}")
    else:
        st.info("No significant gaps identified.")

    # ── Recommended actions ───────────────────────────────────────────────────
    st.subheader("✅ Recommended Immediate Actions")
    if actions:
        for i, action in enumerate(actions, 1):
            st.markdown(f"**{i}.** {action}")
    else:
        st.info("No actions generated.")

    st.divider()

    # ── Save to database ──────────────────────────────────────────────────────
    save_col, _ = st.columns([2, 5])
    if save_col.button("💾 Save Risk Score to Case", type="secondary", use_container_width=True):
        try:
            insert_risk_score(
                case_id=case_id,
                risk_score=risk_score,
                risk_category=risk_category,
                notes=json.dumps({
                    "confidence": confidence,
                    "rationale": rationale,
                    "red_flags": red_flags,
                    "evidence_gaps": evidence_gaps,
                    "recommended_actions": actions,
                    "evidence_quality": eq,
                }),
            )
            st.success(f"✅ Risk score saved — Case: {case_title} | Score: {risk_score} | Category: {risk_category}")
        except Exception as e:
            st.error(f"Save failed: {e}")

    # ── Plain-text report download ─────────────────────────────────────────────
    report_lines = [
        f"FORENSIQ — RISK ASSESSMENT REPORT",
        f"Case: {case_title}",
        f"Risk Score: {risk_score}/100",
        f"Risk Category: {risk_category}",
        f"Confidence: {confidence}%",
        f"\nSCORING RATIONALE\n{rationale}",
        f"\nEVIDENCE QUALITY",
        f"  Physical: {eq.get('physical',0)}%",
        f"  Witness:  {eq.get('witness',0)}%",
        f"  Digital:  {eq.get('digital',0)}%",
        f"\nTOP 5 RED FLAGS",
    ]
    for i, rf in enumerate(red_flags[:5], 1):
        report_lines.append(f"  {i}. {rf.get('flag','')} — {rf.get('implication','')}")
    report_lines.append("\nEVIDENCE GAPS")
    for gap in evidence_gaps:
        report_lines.append(f"  - {gap}")
    report_lines.append("\nRECOMMENDED IMMEDIATE ACTIONS")
    for i, act in enumerate(actions, 1):
        report_lines.append(f"  {i}. {act}")
    report_lines.append("\n--- Generated by ForensiQ Risk Engine ---")

    report_text = "\n".join(report_lines)

    st.download_button(
        label="📥 Download Risk Report (.txt)",
        data=report_text,
        file_name=f"risk_report_{case_id}.txt",
        mime="text/plain",
    )

# ── Disclaimer ─────────────────────────────────────────────────────────────────
st.divider()
st.warning(
    "⚠️ **Disclaimer:** ForensiQ Risk Scorer is an AI-assisted investigative tool intended "
    "to support — not replace — qualified forensic professionals. Risk scores are probabilistic "
    "estimates based on available data and must not be used as the sole basis for legal or "
    "operational decisions. Always verify findings through established forensic and legal procedures."
)