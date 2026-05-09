import streamlit as st
import os
import json
import re
from datetime import datetime

import plotly.graph_objects as go
import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

from database import (
    get_connection,
    get_all_cases,
    get_case_by_id,
    get_autopsy_by_case,
    get_witnesses_by_case,
    get_tod_by_case,
    get_suspects_by_case,
    get_cctv_by_case,
    _normalize_case,
    insert_crime_pattern,
    get_all_patterns,
)
from theme import apply_theme

st.set_page_config(
    page_title="Pattern Engine — ForensiQ",
    page_icon="🔗",
    layout="wide"
)
apply_theme()

# ── Featherless AI client ──────────────────────────────────────────────────────
client = OpenAI(
    base_url="https://api.featherless.ai/v1",
    api_key=os.getenv("FEATHERLESS_API_KEY")
)
MODEL = "meta-llama/Llama-3.3-70B-Instruct"


# ── HELPERS ───────────────────────────────────────────────────────────────────

def build_case_summary(case_id: str) -> str:
    """Pull every piece of available evidence for a case into a plain-text block."""
    case = get_case_by_id(case_id)
    if not case:
        return f"Case {case_id}: No data found."

    c = _normalize_case(dict(case))
    lines = [
        f"CASE ID   : {c.get('case_id', case_id)}",
        f"Victim    : {c.get('victim_name', 'Unknown')}",
        f"Type      : {c.get('case_type', 'Unknown')}",
        f"Location  : {c.get('location', c.get('location_found', 'Unknown'))}",
        f"Date      : {c.get('incident_date', c.get('date_of_incident', 'Unknown'))}",
        f"Status    : {c.get('status', 'Unknown')}",
        "",
    ]

    # Autopsy
    autopsies = get_autopsy_by_case(case_id)
    if autopsies:
        a = dict(autopsies[0])
        lines += [
            "AUTOPSY FINDINGS:",
            f"  Cause of Death   : {a.get('cause_of_death', a.get('soap_assessment', 'N/A'))}",
            f"  Manner           : {a.get('manner_of_death', 'N/A')}",
            f"  Injuries         : {a.get('injury_type', 'N/A')}",
            f"  Weapon           : {a.get('weapon_type', 'N/A')}",
            f"  Defensive Wounds : {a.get('defensive_wounds', 'N/A')}",
            f"  Toxicology       : {a.get('toxicology', 'N/A')}",
            "",
        ]

    # Witnesses
    witnesses = get_witnesses_by_case(case_id)
    if witnesses:
        lines.append("WITNESS STATEMENTS:")
        for w in witnesses:
            wd = dict(w)
            lines += [
                f"  Timeline        : {str(wd.get('timeline', 'N/A'))[:250]}",
                f"  Key People      : {str(wd.get('key_people', 'N/A'))[:200]}",
                f"  Contradictions  : {str(wd.get('contradictions', 'N/A'))[:200]}",
            ]
        lines.append("")

    # TOD
    tod = get_tod_by_case(case_id)
    if tod:
        import json
        if isinstance(tod, dict):
            td = tod
        elif isinstance(tod, list):
            td = tod[0] if tod and isinstance(tod[0], dict) else {}
        elif isinstance(tod, str):
            td = json.loads(tod)
        else:
            td = {}
        lines += [
            "TIME OF DEATH:",
            f"  Window     : {td.get('estimated_tod', td.get('estimated_tod_range', 'N/A'))}",
            f"  Confidence : {td.get('confidence', td.get('confidence_score', 'N/A'))}",
            "",
        ]

    # Suspects
    suspects = get_suspects_by_case(case_id)
    if suspects:
        lines.append("SUSPECTS:")
        for s in suspects:
            sd = dict(s)
            name = sd.get('suspect_name', sd.get('name', 'Unknown'))
            history = str(sd.get('criminal_history', 'N/A'))[:180]
            lines.append(f"  - {name} | History: {history}")
        lines.append("")

    # CCTV
    sightings = get_cctv_by_case(case_id)
    if sightings:
        lines.append(f"CCTV SIGHTINGS: {len(sightings)} entries")
        for s in list(sightings)[:4]:
            sd = dict(s)
            lines.append(
                f"  [{sd.get('timestamp','?')}] {sd.get('location','?')} "
                f"— Conf: {sd.get('confidence','?')}"
            )
        lines.append("")

    return "\n".join(lines)


def run_pattern_analysis(selected_ids: list) -> str:
    """Bundle all case evidence and send to Featherless AI."""
    blocks = [
        f"{'=' * 55}\n{build_case_summary(cid)}"
        for cid in selected_ids
    ]
    combined = "\n".join(blocks)

    prompt = f"""You are a senior forensic investigator specialising in cross-case pattern analysis and serial crime identification.

Carefully analyse the following {len(selected_ids)} case summaries and identify patterns, links, and connections.

{combined}

Respond ONLY in this EXACT format. Label every section exactly as shown:

PHYSICAL_PATTERNS:
[Shared injury types, causes of death, weapon types, victim demographics, body condition at discovery]

LOCATION_TIME_PATTERNS:
[Shared locations, neighbourhoods, time of day, day of week, seasonal patterns]

BEHAVIOURAL_SIGNATURE:
[Perpetrator behaviours: disposal method, evidence destruction, victim selection, any signature acts]

SUSPECT_CONVERGENCE:
[Suspects appearing across multiple cases, shared criminal histories, or overlapping suspect profiles]

CONVERGENCE_SCORE:
[Single integer 0-100 — then one word: WEAK / MODERATE / STRONG / CRITICAL]

INVESTIGATOR_RECOMMENDATION:
[3-5 specific numbered actions investigators should take based on these patterns]

PATTERN_HEADLINE:
[One sentence summary of the key finding for the report header]"""

    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=2000,
        temperature=0.4,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a forensic pattern analysis expert. "
                    "Extract cross-case patterns with precision. "
                    "Follow the response format exactly — no extra text outside sections."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    )
    return response.choices[0].message.content


def parse_result(raw: str) -> dict:
    """Split AI response into a structured dict by section labels."""
    keys = [
        "PHYSICAL_PATTERNS",
        "LOCATION_TIME_PATTERNS",
        "BEHAVIOURAL_SIGNATURE",
        "SUSPECT_CONVERGENCE",
        "CONVERGENCE_SCORE",
        "INVESTIGATOR_RECOMMENDATION",
        "PATTERN_HEADLINE",
    ]
    result = {}
    for i, key in enumerate(keys):
        marker = f"{key}:"
        start = raw.find(marker)
        if start == -1:
            result[key] = "Not extracted"
            continue
        start += len(marker)
        next_marker = f"{keys[i + 1]}:" if i + 1 < len(keys) else None
        end = raw.find(next_marker) if next_marker else len(raw)
        result[key] = raw[start:end].strip()
    return result


def score_from_text(text: str) -> int:
    nums = re.findall(r'\d+', text)
    if not nums:
        return 50
    val = int(nums[0])
    return max(0, min(100, val))


def score_badge(score: int) -> tuple:
    if score < 30:
        return "🟢", "WEAK LINK"
    if score < 60:
        return "🟡", "MODERATE LINK"
    if score < 85:
        return "🟠", "STRONG LINK"
    return "🔴", "CRITICAL LINK"


def gauge_chart(score: int) -> go.Figure:
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        title={"text": "Pattern Convergence Score", "font": {"color": "white", "size": 15}},
        gauge={
            "axis": {"range": [0, 100], "tickcolor": "white"},
            "bar": {"color": "#E63946"},
            "steps": [
                {"range": [0,  30], "color": "#1A2332"},
                {"range": [30, 60], "color": "#2D4A3E"},
                {"range": [60, 85], "color": "#4A3520"},
                {"range": [85, 100], "color": "#4A1520"},
            ],
            "threshold": {
                "line": {"color": "white", "width": 3},
                "thickness": 0.75,
                "value": score,
            },
        },
        number={"font": {"color": "white"}},
    ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="white"),
        height=270,
        margin=dict(t=40, b=10, l=10, r=10),
    )
    return fig


def timeline_chart(selected_ids: list):
    """Plotly scatter timeline of all selected cases by incident date."""
    colors = ["#E63946", "#457B9D", "#2A9D8F", "#E9C46A", "#F4A261", "#A8DADC"]
    rows = []
    for i, cid in enumerate(selected_ids):
        case = get_case_by_id(cid)
        if not case:
            continue
        c = _normalize_case(dict(case))
        date_str = str(c.get("incident_date", c.get("date_of_incident", ""))).strip()
        victim = c.get("victim_name", cid)
        ctype = c.get("case_type", "Unknown")
        parsed = None
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d %b %Y"):
            try:
                parsed = datetime.strptime(date_str, fmt)
                break
            except Exception:
                continue
        if parsed:
            rows.append({
                "label": f"{cid} — {victim}",
                "type": ctype,
                "date": parsed,
                "color": colors[i % len(colors)],
            })

    if not rows:
        return None

    df = pd.DataFrame(rows).sort_values("date")
    fig = go.Figure()
    for _, row in df.iterrows():
        fig.add_trace(go.Scatter(
            x=[row["date"]],
            y=[row["label"]],
            mode="markers+text",
            marker=dict(size=20, color=row["color"], symbol="diamond"),
            text=[row["type"]],
            textposition="top center",
            name=row["label"],
        ))

    fig.update_layout(
        title="Cross-Case Incident Timeline",
        xaxis_title="Date of Incident",
        yaxis_title="",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="white"),
        height=100 + len(rows) * 80,
        showlegend=False,
        margin=dict(l=20, r=20, t=50, b=30),
    )
    fig.update_xaxes(gridcolor="#2D3748")
    fig.update_yaxes(gridcolor="#2D3748")
    return fig


def download_report(parsed: dict, selected_ids: list, score: int, label: str) -> str:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sep = "=" * 60
    return "\n".join([
        sep,
        "FORENSIQ — CROSS-CRIME PATTERN ANALYSIS REPORT",
        f"Generated : {ts}",
        f"Cases     : {', '.join(selected_ids)}",
        sep, "",
        f"HEADLINE  : {parsed.get('PATTERN_HEADLINE', 'N/A')}", "",
        f"CONVERGENCE SCORE : {score}/100  —  {label}", "",
        "PHYSICAL PATTERNS:",
        parsed.get("PHYSICAL_PATTERNS", "N/A"), "",
        "LOCATION & TIME PATTERNS:",
        parsed.get("LOCATION_TIME_PATTERNS", "N/A"), "",
        "BEHAVIOURAL SIGNATURE:",
        parsed.get("BEHAVIOURAL_SIGNATURE", "N/A"), "",
        "SUSPECT CONVERGENCE:",
        parsed.get("SUSPECT_CONVERGENCE", "N/A"), "",
        "INVESTIGATOR RECOMMENDATIONS:",
        parsed.get("INVESTIGATOR_RECOMMENDATION", "N/A"), "",
        sep,
        "DISCLAIMER: This report is AI-assisted and intended solely to",
        "support human investigative decision-making. All findings must",
        "be independently verified by qualified forensic professionals.",
        "Not admissible as standalone legal evidence.",
        sep,
    ])


# ── PAGE ──────────────────────────────────────────────────────────────────────

st.title("🔗 Cross-Crime Pattern Recognition Engine")
st.markdown(
    "Select two or more cases to identify shared patterns, "
    "behavioural signatures, and possible suspect links."
)
st.markdown("---")

tab_run, tab_history = st.tabs(["🔍 Run Analysis", "📂 Previous Analyses"])

# ─── TAB 1: RUN ───────────────────────────────────────────────────────────────
with tab_run:

    all_cases = get_all_cases()

    if len(all_cases) < 2:
        st.warning(
            "⚠️ You need at least **2 cases** in the system to run a pattern analysis. "
            "Go to Case Manager and create more cases first."
        )
        st.stop()

    # Build label → case_id map
    case_map = {}
    for raw in all_cases:
        c = _normalize_case(dict(raw))
        cid = c.get("case_id", "?")
        victim = c.get("victim_name", "Unknown")
        ctype = c.get("case_type", "?")
        case_map[f"{cid} — {victim} ({ctype})"] = cid

    st.subheader("① Select Cases to Compare")
    selected_labels = st.multiselect(
        "Choose 2 or more cases:",
        options=list(case_map.keys()),
    )
    selected_ids = [case_map[lbl] for lbl in selected_labels]

    if len(selected_ids) == 1:
        st.info("Select at least one more case to enable analysis.")

    if len(selected_ids) >= 2:
        st.success(f"✅ {len(selected_ids)} cases selected: **{', '.join(selected_ids)}**")

        # Timeline
        st.subheader("② Incident Timeline Preview")
        tfig = timeline_chart(selected_ids)
        if tfig:
            st.plotly_chart(tfig, use_container_width=True)
        else:
            st.info(
                "Timeline could not be rendered — incident dates may be missing "
                "or in an unrecognised format in one or more cases."
            )

        # Evidence preview
        with st.expander("📋 Preview Evidence Pulled for Each Case"):
            for cid in selected_ids:
                st.markdown(f"**{cid}**")
                st.code(build_case_summary(cid), language=None)

        st.subheader("③ Run AI Pattern Analysis")
        if st.button(
            "🔗 Analyse Patterns Across Cases",
            use_container_width=True,
            type="primary",
        ):
            with st.spinner("🧠 ForensiQ AI is cross-referencing all case evidence — please wait…"):
                raw = run_pattern_analysis(selected_ids)
                parsed = parse_result(raw)
                score = score_from_text(parsed.get("CONVERGENCE_SCORE", "50"))
                icon, label = score_badge(score)
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Persist in session state so results survive re-runs
            st.session_state.update({
                "pe_parsed": parsed,
                "pe_score": score,
                "pe_label": label,
                "pe_icon": icon,
                "pe_ids": selected_ids,
                "pe_ts": ts,
                "pe_raw": raw,
            })

        # Show results if available in session state
        if "pe_parsed" in st.session_state and st.session_state["pe_ids"] == selected_ids:
            parsed = st.session_state["pe_parsed"]
            score  = st.session_state["pe_score"]
            label  = st.session_state["pe_label"]
            icon   = st.session_state["pe_icon"]
            ts     = st.session_state["pe_ts"]

            st.markdown("---")
            st.subheader("📊 Pattern Analysis Results")

            # Headline
            st.markdown(
                f"### 📌 {parsed.get('PATTERN_HEADLINE', 'Pattern Analysis Complete')}"
            )

            # Gauge + badge
            col_g, col_b = st.columns([1, 1])
            with col_g:
                st.plotly_chart(gauge_chart(score), use_container_width=True)
            with col_b:
                st.markdown("<br><br>", unsafe_allow_html=True)
                st.markdown(f"## {icon} {label}")
                st.markdown(f"**Convergence Score: {score} / 100**")
                st.caption(parsed.get("CONVERGENCE_SCORE", ""))

            st.markdown("---")

            # Six result panels
            sections = [
                ("🩸 Physical Patterns",          "PHYSICAL_PATTERNS",           "info"),
                ("📍 Location & Time Patterns",   "LOCATION_TIME_PATTERNS",      "info"),
                ("🎭 Behavioural Signature",       "BEHAVIOURAL_SIGNATURE",       "warning"),
                ("👤 Suspect Convergence",         "SUSPECT_CONVERGENCE",         "warning"),
                ("✅ Investigator Recommendations","INVESTIGATOR_RECOMMENDATION", "error"),
            ]

            for title, key, style in sections:
                st.markdown(f"#### {title}")
                content = parsed.get(key, "Not extracted")
                if style == "info":
                    st.info(content)
                elif style == "warning":
                    st.warning(content)
                else:
                    st.error(content)

            # Save to DB
            insert_crime_pattern(
                selected_ids,
                parsed.get("PATTERN_HEADLINE", ""),
                float(score),
                parsed.get("PHYSICAL_PATTERNS", ""),
            )
            st.success("✅ Pattern analysis saved to database.")

            # Download
            report_txt = download_report(parsed, selected_ids, score, label)
            st.download_button(
                label="⬇️ Download Pattern Report (.txt)",
                data=report_txt,
                file_name=(
                    f"ForensiQ_Pattern_{'_'.join(selected_ids)}_"
                    f"{datetime.now().strftime('%Y%m%d')}.txt"
                ),
                mime="text/plain",
                use_container_width=True,
            )

            st.markdown("---")
            st.warning(
                "⚠️ **Disclaimer:** This pattern analysis is AI-assisted and intended "
                "to support investigative decision-making only. All findings must be "
                "independently verified by qualified forensic professionals. "
                "Not admissible as standalone legal evidence."
            )


# ─── TAB 2: HISTORY ───────────────────────────────────────────────────────────
with tab_history:
    st.subheader("Previous Pattern Analyses")

    history = get_all_patterns()

    if not history:
        st.info("No pattern analyses have been saved yet. Run your first analysis above.")
    else:
        for p in history:
            try:
                case_ids = json.loads(p.get("case_ids", "[]"))
            except Exception:
                case_ids = [str(p.get("case_ids", ""))]

            s = p.get("convergence_pct", 0)
            ico, lbl = score_badge(int(s))

            with st.expander(
                f"{ico} {lbl}  |  Cases: {', '.join(case_ids)}"
                f"  |  Score: {s}  |  {str(p.get('created_at',''))[:10]}"
            ):
                st.markdown(f"**Headline:** {p.get('pattern_summary', 'N/A')}")
                st.markdown(f"**Cases Linked:** {', '.join(case_ids)}")
                st.markdown(f"**Score:** {s}/100  —  {ico} {lbl}")
                st.markdown(f"**Key Physical Pattern:** {p.get('common_factors', 'N/A')}")
                st.caption(f"Saved: {p.get('created_at', '')}")