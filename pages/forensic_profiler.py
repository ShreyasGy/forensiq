# pages/forensic_profiler.py
# Session 8 — Forensic Evidence Profiler & Suspect Shortlister
# DO NOT MODIFY after session is complete

import streamlit as st
import os
import json
import plotly.graph_objects as go
from openai import OpenAI
from dotenv import load_dotenv

from database import (
    get_all_cases,
    get_case_by_id,
    get_autopsy_by_case,
    get_witnesses_by_case,
    get_tod_by_case,
    get_cctv_by_case,
    get_suspects_by_case,
    _normalize_case,
)
from theme import apply_theme

# ── Bootstrap ──────────────────────────────────────────────────────────────────
load_dotenv()

st.set_page_config(
    page_title="Forensic Profiler | ForensiQ",
    page_icon="🧠",
    layout="wide",
)
apply_theme()

# ── Featherless AI client ───────────────────────────────────────────────────────
client = OpenAI(
    api_key=os.getenv("FEATHERLESS_API_KEY"),
    base_url="https://api.featherless.ai/v1",
)
MODEL = "meta-llama/Llama-3.3-70B-Instruct"


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def safe(value, fallback="Not recorded"):
    """Return a clean string or a fallback label."""
    if value is None:
        return fallback
    s = str(value).strip()
    return s if s else fallback


import sqlite3 as _sqlite3

def row_to_dict(row):
    if row is None:
        return {}
    if isinstance(row, dict):
        return row
    try:
        return {k: row[k] for k in row.keys()}
    except AttributeError:
        pass
    try:
        return row._asdict()
    except AttributeError:
        pass
    return {}


def fetch_tod_dict(case_id: str) -> dict:
    """Fetch TOD directly with row_factory guaranteed, bypassing the plain-tuple issue."""
    from database import get_connection
    conn = get_connection()
    conn.row_factory = _sqlite3.Row
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT * FROM tod_estimates WHERE case_id = ? ORDER BY id DESC LIMIT 1",
            (case_id,)
        )
        row = cur.fetchone()
        if row:
            return {k: row[k] for k in row.keys()}
    except Exception:
        pass
    finally:
        conn.close()
    return {}


def badge(label: str, color: str) -> str:
    return (
        f'<span style="background:{color};color:#fff;padding:4px 14px;'
        f'border-radius:12px;font-weight:700;font-size:0.85rem;">{label}</span>'
    )


def threat_color(level: str) -> str:
    mapping = {
        "critical": "#e74c3c",
        "high": "#e67e22",
        "medium": "#f1c40f",
        "low": "#2ecc71",
    }
    return mapping.get(str(level).lower(), "#95a5a6")


def rank_badge(rank: int) -> str:
    colors = {1: "#e74c3c", 2: "#e67e22", 3: "#f1c40f"}
    color = colors.get(rank, "#95a5a6")
    return (
        f'<span style="background:{color};color:#fff;padding:3px 10px;'
        f'border-radius:8px;font-weight:700;">#{rank}</span>'
    )


# ══════════════════════════════════════════════════════════════════════════════
#  DATA COLLECTION
# ══════════════════════════════════════════════════════════════════════════════

def collect_case_evidence(case_id: str) -> dict:
    """Pull every evidence type for a case and return a structured dict."""
    evidence = {
        "case": {},
        "autopsy": {},
        "witnesses": [],
        "tod": {},
        "cctv": [],
        "suspects": [],
    }

    raw_case = get_case_by_id(case_id)
    if raw_case:
        c = _normalize_case(row_to_dict(raw_case))
        evidence["case"] = {
            "case_number": safe(c.get("case_number")),
            "title": safe(c.get("title")),
            "victim_name": safe(c.get("victim_name")),
            "case_type": safe(c.get("case_type")),
            "assigned_investigator": safe(c.get("assigned_investigator")),
            "description": safe(c.get("description")),
            "status": safe(c.get("status")),
        }

    raw_autopsy = get_autopsy_by_case(case_id)
    if raw_autopsy:
        a = row_to_dict(raw_autopsy)
        evidence["autopsy"] = {
            "soap_assessment": safe(a.get("soap_assessment")),
            "injury_type": safe(a.get("injury_type")),
            "body_location": safe(a.get("body_location")),
            "weapon_type": safe(a.get("weapon_type")),
            "defensive_wounds": safe(a.get("defensive_wounds")),
            "signs_of_struggle": safe(a.get("signs_of_struggle")),
            "toxicology": safe(a.get("toxicology")),
            "time_indicators": safe(a.get("time_indicators")),
            "anomalies": safe(a.get("anomalies")),
        }

    raw_witnesses = get_witnesses_by_case(case_id)
    if raw_witnesses:
        for row in raw_witnesses:
            w = row_to_dict(row)
            evidence["witnesses"].append({
                "timeline": safe(w.get("timeline")),
                "key_people": safe(w.get("key_people")),
                "key_locations": safe(w.get("key_locations")),
                "key_objects": safe(w.get("key_objects")),
                "contradictions": safe(w.get("contradictions")),
                "reliability_rating": safe(w.get("reliability_rating")),
            })

        # ── TOD ──
        t = fetch_tod_dict(case_id)
        if t:
            evidence["tod"] = {
                "estimated_tod_range": safe(t.get("estimated_tod_range")),
                "confidence_score": safe(t.get("confidence_score")),
                "special_notes": safe(t.get("special_notes")),
            }

    raw_cctv = get_cctv_by_case(case_id)
    if raw_cctv:
        for row in raw_cctv:
            v = row_to_dict(row)
            evidence["cctv"].append({
                "timestamp": safe(v.get("timestamp")),
                "location": safe(v.get("location")),
                "description": safe(v.get("description")),
                "confidence": safe(v.get("confidence")),
                "notes": safe(v.get("notes")),
            })

    raw_suspects = get_suspects_by_case(case_id)
    if raw_suspects:
        for row in raw_suspects:
            s = row_to_dict(row)
            evidence["suspects"].append({
                "name": safe(s.get("name")),
                "motive": safe(s.get("motive")),
                "threat_level": safe(s.get("threat_level")),
                "alibi": safe(s.get("alibi")),
                "notes": safe(s.get("notes")),
            })

    return evidence
# ══════════════════════════════════════════════════════════════════════════════
#  EVIDENCE SUMMARY PANEL
# ══════════════════════════════════════════════════════════════════════════════

def show_evidence_summary(ev: dict):
    """Display collected evidence in expandable sections."""
    c = ev["case"]
    st.markdown("### 📁 Case Overview")
    col1, col2, col3 = st.columns(3)
    col1.metric("Case Number", c.get("case_number", "—"))
    col2.metric("Victim", c.get("victim_name", "—"))
    col3.metric("Type", c.get("case_type", "—"))

    col4, col5 = st.columns(2)
    col4.metric("Investigator", c.get("assigned_investigator", "—"))
    col5.metric("Status", c.get("status", "—"))

    st.markdown("---")

    # Evidence counts
    e_col1, e_col2, e_col3, e_col4, e_col5 = st.columns(5)
    e_col1.metric("🔬 Autopsy", "✅" if ev["autopsy"] else "❌")
    e_col2.metric("👁 Witnesses", len(ev["witnesses"]))
    e_col3.metric("⏱ TOD", "✅" if ev["tod"] else "❌")
    e_col4.metric("📹 CCTV Sightings", len(ev["cctv"]))
    e_col5.metric("🕵️ Suspects", len(ev["suspects"]))

    # Expandable detail sections
    if ev["autopsy"]:
        with st.expander("🔬 Autopsy Details", expanded=False):
            a = ev["autopsy"]
            st.write(f"**SOAP Assessment:** {a['soap_assessment']}")
            st.write(f"**Injury Type:** {a['injury_type']}  |  **Body Location:** {a['body_location']}")
            st.write(f"**Weapon Type:** {a['weapon_type']}")
            st.write(f"**Defensive Wounds:** {a['defensive_wounds']}  |  **Signs of Struggle:** {a['signs_of_struggle']}")
            st.write(f"**Toxicology:** {a['toxicology']}")
            st.write(f"**Anomalies:** {a['anomalies']}")

    if ev["witnesses"]:
        with st.expander(f"👁 Witness Statements ({len(ev['witnesses'])})", expanded=False):
            for i, w in enumerate(ev["witnesses"], 1):
                st.markdown(f"**Witness {i}** — Reliability: `{w['reliability_rating']}`")
                st.write(f"Timeline: {w['timeline']}")
                st.write(f"Contradictions: {w['contradictions']}")
                st.markdown("---")

    if ev["tod"]:
        with st.expander("⏱ Time of Death Estimate", expanded=False):
            t = ev["tod"]
            st.write(f"**Estimated TOD Range:** {t['estimated_tod_range']}")
            st.write(f"**Confidence Score:** {t['confidence_score']}")
            st.write(f"**Notes:** {t['special_notes']}")

    if ev["cctv"]:
        with st.expander(f"📹 CCTV Sightings ({len(ev['cctv'])})", expanded=False):
            for i, v in enumerate(ev["cctv"], 1):
                st.markdown(f"**Sighting {i}** — {v['timestamp']} @ {v['location']}")
                st.write(f"Description: {v['description']}  |  Confidence: {v['confidence']}")

    if ev["suspects"]:
        with st.expander(f"🕵️ Known Suspects ({len(ev['suspects'])})", expanded=False):
            for s in ev["suspects"]:
                st.markdown(
                    f"**{s['name']}** — Threat: "
                    + badge(s["threat_level"], threat_color(s["threat_level"])),
                    unsafe_allow_html=True,
                )
                st.write(f"Motive: {s['motive']}  |  Alibi: {s['alibi']}")
                st.markdown("---")


# ══════════════════════════════════════════════════════════════════════════════
#  AI PROMPT BUILDER
# ══════════════════════════════════════════════════════════════════════════════

def build_profiler_prompt(ev: dict) -> str:
    c = ev["case"]
    a = ev["autopsy"]
    tod = ev["tod"]

    witness_text = ""
    for i, w in enumerate(ev["witnesses"], 1):
        witness_text += f"""
  Witness {i} (Reliability: {w['reliability_rating']}):
    Timeline: {w['timeline']}
    Key People: {w['key_people']}
    Key Locations: {w['key_locations']}
    Key Objects: {w['key_objects']}
    Contradictions: {w['contradictions']}"""

    cctv_text = ""
    for i, v in enumerate(ev["cctv"], 1):
        cctv_text += f"\n  Sighting {i}: {v['timestamp']} at {v['location']} — {v['description']} (Confidence: {v['confidence']})"

    suspect_text = ""
    for s in ev["suspects"]:
        suspect_text += f"\n  - {s['name']}: Motive={s['motive']}, Threat={s['threat_level']}, Alibi={s['alibi']}"

    autopsy_block = f"""
  SOAP Assessment: {a.get('soap_assessment', 'Not available')}
  Injury Type: {a.get('injury_type', 'Not available')}
  Body Location: {a.get('body_location', 'Not available')}
  Weapon Type: {a.get('weapon_type', 'Not available')}
  Defensive Wounds: {a.get('defensive_wounds', 'Not available')}
  Signs of Struggle: {a.get('signs_of_struggle', 'Not available')}
  Toxicology: {a.get('toxicology', 'Not available')}
  Anomalies: {a.get('anomalies', 'Not available')}""" if a else "\n  No autopsy data available."

    tod_block = f"""
  Estimated TOD Range: {tod.get('estimated_tod_range', 'Not available')}
  Confidence: {tod.get('confidence_score', 'Not available')}
  Notes: {tod.get('special_notes', 'Not available')}""" if tod else "\n  No TOD data available."

    prompt = f"""You are a forensic behavioral analyst and criminal investigator with 30 years of experience.
Analyse all evidence below for Case {c['case_number']} — {c['title']} and produce a structured forensic profile.

═══════════════════════════════════════════════════════════
CASE DETAILS
═══════════════════════════════════════════════════════════
Case Number       : {c['case_number']}
Title             : {c['title']}
Victim Name       : {c['victim_name']}
Case Type         : {c['case_type']}
Investigator      : {c['assigned_investigator']}
Description       : {c['description']}
Status            : {c['status']}

═══════════════════════════════════════════════════════════
AUTOPSY FINDINGS
═══════════════════════════════════════════════════════════{autopsy_block}

═══════════════════════════════════════════════════════════
WITNESS STATEMENTS ({len(ev['witnesses'])} total)
═══════════════════════════════════════════════════════════{witness_text if witness_text else chr(10) + '  No witness statements recorded.'}

═══════════════════════════════════════════════════════════
TIME OF DEATH ESTIMATE
═══════════════════════════════════════════════════════════{tod_block}

═══════════════════════════════════════════════════════════
CCTV INTELLIGENCE ({len(ev['cctv'])} sightings)
═══════════════════════════════════════════════════════════{cctv_text if cctv_text else chr(10) + '  No CCTV sightings recorded.'}

═══════════════════════════════════════════════════════════
KNOWN SUSPECTS ({len(ev['suspects'])} total)
═══════════════════════════════════════════════════════════{suspect_text if suspect_text else chr(10) + '  No suspects currently on record.'}

═══════════════════════════════════════════════════════════
YOUR TASK
═══════════════════════════════════════════════════════════
Return your analysis as a JSON object with EXACTLY these keys (no extra keys, no markdown):

{{
  "offender_profile": {{
    "age_range": "estimated age range (e.g. 25-40)",
    "gender_inference": "inference based on evidence",
    "physical_build": "inference from evidence",
    "psychological_type": "organised / disorganised / mixed — explain",
    "likely_relationship_to_victim": "stranger / acquaintance / intimate / unknown",
    "skill_level": "professional / experienced / opportunistic / novice",
    "behavioural_indicators": ["indicator 1", "indicator 2", "indicator 3"],
    "likely_motive": "detailed motive analysis"
  }},
  "suspect_shortlist": [
    {{
      "rank": 1,
      "name": "Suspect name or UNKNOWN",
      "alignment_score": 85,
      "key_evidence_links": ["link 1", "link 2"],
      "alibi_assessment": "assessment of their alibi",
      "priority_action": "most important next investigative step"
    }}
  ],
  "evidence_strength": {{
    "physical_evidence_score": 70,
    "witness_reliability_score": 55,
    "digital_evidence_score": 40,
    "overall_evidence_strength": "Moderate",
    "strongest_evidence_piece": "description",
    "weakest_link": "description"
  }},
  "critical_red_flags": [
    {{"flag": "red flag 1", "implication": "what this means"}},
    {{"flag": "red flag 2", "implication": "what this means"}},
    {{"flag": "red flag 3", "implication": "what this means"}}
  ],
  "evidence_gaps": [
    "gap 1 — what is missing and why it matters",
    "gap 2",
    "gap 3"
  ],
  "recommended_actions": [
    "1. Immediate action with reasoning",
    "2. Second action",
    "3. Third action",
    "4. Fourth action",
    "5. Fifth action"
  ],
  "profile_confidence": {{
    "score": 72,
    "label": "Moderate",
    "reasoning": "brief explanation of confidence level"
  }},
  "analyst_summary": "A 4-6 sentence narrative summary integrating all findings into a coherent investigative picture."
}}

IMPORTANT: Return ONLY the JSON object. No preamble, no markdown, no explanation outside the JSON.
"""
    return prompt


# ══════════════════════════════════════════════════════════════════════════════
#  AI CALL
# ══════════════════════════════════════════════════════════════════════════════

def clean_json_string(raw: str) -> str:
    """Aggressively clean AI output to extract valid JSON."""
    # Strip markdown fences
    if "```" in raw:
        parts = raw.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:]
            part = part.strip()
            if part.startswith("{"):
                raw = part
                break

    # Find the outermost { ... }
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        raw = raw[start:end + 1]

    # Fix common model mistakes
    raw = raw.replace("\n", " ")
    raw = raw.replace("\r", " ")
    raw = raw.replace("\t", " ")

    # Remove trailing commas before } or ]
    import re
    raw = re.sub(r",\s*}", "}", raw)
    raw = re.sub(r",\s*]", "]", raw)

    return raw.strip()


def run_profiler_ai(prompt: str) -> dict | None:
    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a senior forensic behavioural analyst. "
                            "You MUST respond with a single valid JSON object only. "
                            "No markdown. No code fences. No text before or after the JSON. "
                            "Every string value must be properly quoted and escaped. "
                            "Do not use newlines inside string values."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=3000,
            )
            raw = response.choices[0].message.content.strip()
            cleaned = clean_json_string(raw)

            try:
                return json.loads(cleaned)
            except json.JSONDecodeError as e:
                if attempt < 2:
                    st.warning(f"⏳ Attempt {attempt + 1} returned malformed JSON, retrying...")
                    continue
                # Last attempt — show the specific error and the raw snippet around it
                err_pos = e.pos if hasattr(e, 'pos') else 0
                snippet = cleaned[max(0, err_pos - 80): err_pos + 80]
                st.error(
                    f"⚠️ AI returned invalid JSON after 3 attempts.\n\n"
                    f"**Error:** {e}\n\n"
                    f"**Near:** `...{snippet}...`"
                )
                return None

        except Exception as e:
            st.error(f"⚠️ AI call failed: {e}")
            return None

    return None
# ══════════════════════════════════════════════════════════════════════════════
#  DISPLAY RESULTS
# ══════════════════════════════════════════════════════════════════════════════

def show_offender_profile(profile: dict):
    st.markdown("## 🧠 Offender Profile")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**Age Range:** {profile.get('age_range', '—')}")
        st.markdown(f"**Gender Inference:** {profile.get('gender_inference', '—')}")
        st.markdown(f"**Physical Build:** {profile.get('physical_build', '—')}")
        st.markdown(f"**Psychological Type:** {profile.get('psychological_type', '—')}")
    with col2:
        st.markdown(f"**Relationship to Victim:** {profile.get('likely_relationship_to_victim', '—')}")
        st.markdown(f"**Skill Level:** {profile.get('skill_level', '—')}")
        st.markdown(f"**Likely Motive:** {profile.get('likely_motive', '—')}")

    st.markdown("**Behavioural Indicators:**")
    for ind in profile.get("behavioural_indicators", []):
        st.markdown(f"- {ind}")


def show_suspect_shortlist(shortlist: list):
    st.markdown("## 🕵️ Suspect Shortlist")

    if not shortlist:
        st.info("No suspects could be ranked from available evidence.")
        return

    for s in shortlist:
        rank = s.get("rank", 0)
        score = s.get("alignment_score", 0)

        # Color band
        if score >= 80:
            bar_color = "#e74c3c"
        elif score >= 60:
            bar_color = "#e67e22"
        elif score >= 40:
            bar_color = "#f1c40f"
        else:
            bar_color = "#2ecc71"

        with st.container():
            st.markdown(
                f"{rank_badge(rank)} &nbsp; **{s.get('name', 'UNKNOWN')}** &nbsp; "
                f"— Alignment Score: "
                f'<span style="color:{bar_color};font-weight:700;">{score}/100</span>',
                unsafe_allow_html=True,
            )

            # Alignment bar
            fig = go.Figure(
                go.Bar(
                    x=[score],
                    y=[""],
                    orientation="h",
                    marker_color=bar_color,
                    width=0.4,
                )
            )
            fig.update_layout(
                height=60,
                margin=dict(l=0, r=0, t=0, b=0),
                xaxis=dict(range=[0, 100], showticklabels=False),
                yaxis=dict(showticklabels=False),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig, use_container_width=True, key=f"bar_{rank}")

            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Key Evidence Links:**")
                for link in s.get("key_evidence_links", []):
                    st.markdown(f"  - {link}")
            with col2:
                st.markdown(f"**Alibi Assessment:** {s.get('alibi_assessment', '—')}")
                st.markdown(f"**Priority Action:** {s.get('priority_action', '—')}")
            st.markdown("---")


def show_evidence_strength(strength: dict):
    st.markdown("## 📊 Evidence Strength Analysis")

    col1, col2, col3 = st.columns(3)

    def mini_gauge(value, title, key):
        fig = go.Figure(
            go.Indicator(
                mode="gauge+number",
                value=value,
                title={"text": title, "font": {"size": 13}},
                gauge={
                    "axis": {"range": [0, 100]},
                    "bar": {"color": "#3498db"},
                    "steps": [
                        {"range": [0, 40], "color": "#e74c3c"},
                        {"range": [40, 70], "color": "#f1c40f"},
                        {"range": [70, 100], "color": "#2ecc71"},
                    ],
                },
                number={"suffix": "%"},
            )
        )
        fig.update_layout(height=200, margin=dict(l=20, r=20, t=30, b=10))
        st.plotly_chart(fig, use_container_width=True, key=key)

    with col1:
        mini_gauge(strength.get("physical_evidence_score", 0), "Physical Evidence", "gauge_phys")
    with col2:
        mini_gauge(strength.get("witness_reliability_score", 0), "Witness Reliability", "gauge_wit")
    with col3:
        mini_gauge(strength.get("digital_evidence_score", 0), "Digital Evidence", "gauge_dig")

    col4, col5 = st.columns(2)
    col4.info(f"**Strongest Evidence:** {strength.get('strongest_evidence_piece', '—')}")
    col5.warning(f"**Weakest Link:** {strength.get('weakest_link', '—')}")

    overall = strength.get("overall_evidence_strength", "Unknown")
    color_map = {"Strong": "#2ecc71", "Moderate": "#f1c40f", "Weak": "#e67e22", "Insufficient": "#e74c3c"}
    color = color_map.get(overall, "#95a5a6")
    st.markdown(
        f"**Overall Evidence Strength:** " + badge(overall, color),
        unsafe_allow_html=True,
    )


def show_red_flags(flags: list):
    st.markdown("## 🚩 Critical Red Flags")
    if not flags:
        st.info("No critical red flags identified.")
        return
    for i, f in enumerate(flags, 1):
        st.error(f"**Flag {i}: {f.get('flag', '—')}**\n\n_{f.get('implication', '—')}_")


def show_confidence_gauge(conf: dict):
    score = conf.get("score", 0)
    label = conf.get("label", "Unknown")
    reasoning = conf.get("reasoning", "")

    if score >= 75:
        color = "#2ecc71"
    elif score >= 50:
        color = "#f1c40f"
    elif score >= 30:
        color = "#e67e22"
    else:
        color = "#e74c3c"

    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=score,
            title={"text": "Profile Confidence", "font": {"size": 18}},
            gauge={
                "axis": {"range": [0, 100], "tickwidth": 1},
                "bar": {"color": color},
                "steps": [
                    {"range": [0, 30], "color": "#2c3e50"},
                    {"range": [30, 60], "color": "#34495e"},
                    {"range": [60, 100], "color": "#3d566e"},
                ],
                "threshold": {
                    "line": {"color": "white", "width": 3},
                    "thickness": 0.75,
                    "value": score,
                },
            },
            number={"suffix": "%", "font": {"size": 36}},
        )
    )
    fig.update_layout(height=280, margin=dict(l=40, r=40, t=60, b=20))

    col1, col2 = st.columns([1, 1])
    with col1:
        st.plotly_chart(fig, use_container_width=True, key="conf_gauge")
    with col2:
        st.markdown(f"### {badge(label, color)}", unsafe_allow_html=True)
        st.markdown(f"_{reasoning}_")


def build_text_report(case_info: dict, result: dict) -> str:
    lines = [
        "=" * 65,
        "  FORENSIQ — FORENSIC EVIDENCE PROFILE & SUSPECT SHORTLIST",
        "=" * 65,
        f"Case Number : {case_info.get('case_number', '—')}",
        f"Title       : {case_info.get('title', '—')}",
        f"Victim      : {case_info.get('victim_name', '—')}",
        f"Investigator: {case_info.get('assigned_investigator', '—')}",
        "",
        "─" * 65,
        "ANALYST SUMMARY",
        "─" * 65,
        result.get("analyst_summary", "—"),
        "",
        "─" * 65,
        "OFFENDER PROFILE",
        "─" * 65,
    ]
    op = result.get("offender_profile", {})
    for k, v in op.items():
        if isinstance(v, list):
            lines.append(f"{k.replace('_', ' ').title()}:")
            for item in v:
                lines.append(f"  - {item}")
        else:
            lines.append(f"{k.replace('_', ' ').title()}: {v}")

    lines += ["", "─" * 65, "SUSPECT SHORTLIST", "─" * 65]
    for s in result.get("suspect_shortlist", []):
        lines.append(f"Rank #{s.get('rank')} — {s.get('name')} (Alignment: {s.get('alignment_score')}%)")
        lines.append(f"  Alibi: {s.get('alibi_assessment')}")
        lines.append(f"  Priority Action: {s.get('priority_action')}")
        for link in s.get("key_evidence_links", []):
            lines.append(f"  Evidence: {link}")
        lines.append("")

    lines += ["─" * 65, "CRITICAL RED FLAGS", "─" * 65]
    for f in result.get("critical_red_flags", []):
        lines.append(f"[FLAG] {f.get('flag')}")
        lines.append(f"       → {f.get('implication')}")

    lines += ["", "─" * 65, "EVIDENCE GAPS", "─" * 65]
    for g in result.get("evidence_gaps", []):
        lines.append(f"• {g}")

    lines += ["", "─" * 65, "RECOMMENDED ACTIONS", "─" * 65]
    for a in result.get("recommended_actions", []):
        lines.append(a)

    conf = result.get("profile_confidence", {})
    lines += [
        "",
        "─" * 65,
        "PROFILE CONFIDENCE",
        "─" * 65,
        f"Score : {conf.get('score')}% — {conf.get('label')}",
        f"Reason: {conf.get('reasoning')}",
        "",
        "=" * 65,
        "⚠  FOR OFFICIAL INVESTIGATIVE USE ONLY — ForensiQ v1.0",
        "=" * 65,
    ]
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN PAGE
# ══════════════════════════════════════════════════════════════════════════════

def main():
    st.title("🧠 Forensic Evidence Profiler")
    st.caption("AI-powered offender profiling and suspect prioritisation from all case evidence")

    # ── Disclaimer ────────────────────────────────────────────────────────────
    st.warning(
        "⚠️ **Disclaimer:** This profiler is an AI-assisted investigative support tool only. "
        "All profiles, rankings, and recommendations must be reviewed by a qualified forensic "
        "professional. This output does not constitute legal evidence and must not be used as "
        "the sole basis for any investigative or legal decision."
    )

    # ── Case Selector ──────────────────────────────────────────────────────────
    st.markdown("### 📂 Select a Case")
    all_cases = get_all_cases()

    if not all_cases:
        st.info("No cases found in the database. Please create a case first in Case Manager.")
        return

    case_options = {
        f"{_normalize_case(dict(c)).get('case_number', '?')} — {_normalize_case(dict(c)).get('title', 'Untitled')}": c
        for c in all_cases
    }

    selected_label = st.selectbox(
        "Choose a case to profile:",
        options=list(case_options.keys()),
        index=0,
        placeholder="Select a case...",
    )

    selected_raw = case_options[selected_label]
    selected_case = _normalize_case(dict(selected_raw))
    case_id = selected_case.get("case_id") or selected_case.get("case_number")

    if not case_id:
        st.error("Could not resolve case ID. Please check the database.")
        return

    # ── Collect Evidence ───────────────────────────────────────────────────────
    st.markdown("---")
    evidence = collect_case_evidence(case_id)
    show_evidence_summary(evidence)

    # ── Evidence availability check ────────────────────────────────────────────
    has_data = any([
        evidence["autopsy"],
        evidence["witnesses"],
        evidence["tod"],
        evidence["cctv"],
        evidence["suspects"],
    ])

    if not has_data:
        st.warning(
            "⚠️ This case has no evidence recorded yet. "
            "Please add autopsy reports, witness statements, TOD estimates, "
            "CCTV sightings, or suspects before running the profiler."
        )
        return

    # ── Run Profiler ───────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 🤖 AI Profiler")

    if st.button("🧠 Generate Forensic Profile", type="primary", use_container_width=True):
        with st.spinner("Analysing all evidence and building offender profile... (30–60 seconds)"):
            prompt = build_profiler_prompt(evidence)
            result = run_profiler_ai(prompt)

        if result:
            st.success("✅ Forensic profile generated successfully.")
            st.session_state["profiler_result"] = result
            st.session_state["profiler_case"] = evidence["case"]
        else:
            st.error("Profile generation failed. Please check your API key and try again.")

    # ── Display Results ────────────────────────────────────────────────────────
    if "profiler_result" in st.session_state and st.session_state.get("profiler_case", {}).get("case_number") == evidence["case"].get("case_number"):

        result = st.session_state["profiler_result"]
        case_info = st.session_state["profiler_case"]

        st.markdown("---")

        # Analyst Summary
        st.markdown("## 📋 Analyst Summary")
        st.info(result.get("analyst_summary", "No summary available."))

        # Profile Confidence Gauge
        if "profile_confidence" in result:
            show_confidence_gauge(result["profile_confidence"])

        st.markdown("---")

        # Two-column layout for profile + suspect list
        left, right = st.columns([1, 1])
        with left:
            show_offender_profile(result.get("offender_profile", {}))
        with right:
            show_suspect_shortlist(result.get("suspect_shortlist", []))

        st.markdown("---")
        show_evidence_strength(result.get("evidence_strength", {}))

        st.markdown("---")
        show_red_flags(result.get("critical_red_flags", []))

        # Evidence gaps
        st.markdown("## 🔍 Evidence Gaps")
        gaps = result.get("evidence_gaps", [])
        if gaps:
            for gap in gaps:
                st.warning(f"❗ {gap}")
        else:
            st.success("No critical evidence gaps identified.")

        # Recommended actions
        st.markdown("## ✅ Recommended Actions")
        actions = result.get("recommended_actions", [])
        if actions:
            for action in actions:
                st.markdown(f"- {action}")
        else:
            st.info("No actions generated.")

        # Download report
        st.markdown("---")
        st.markdown("### 💾 Export Report")
        report_text = build_text_report(case_info, result)
        st.download_button(
            label="📄 Download Full Profile Report (.txt)",
            data=report_text,
            file_name=f"forensic_profile_{case_info.get('case_number', 'unknown')}.txt",
            mime="text/plain",
            use_container_width=True,
        )

    # ── Final disclaimer ───────────────────────────────────────────────────────
    st.markdown("---")
    st.caption(
        "🔒 ForensiQ Forensic Profiler | AI-assisted tool only | "
        "Not a substitute for professional forensic or legal expertise | "
        "Powered by Featherless AI / Llama 3.3 70B"
    )


if __name__ == "__main__":
    main()