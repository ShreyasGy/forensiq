# pages/dashboard.py
# ForensiQ — Session 9: Master Dashboard
# Stats · Charts · Recent Tables · Full PDF Case Report Export

import os
import io
import json
import sqlite3
import datetime
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from dotenv import load_dotenv

load_dotenv()

from theme import apply_theme
from database import (
    get_connection,
    get_all_cases,
    _normalize_case,
    get_autopsy_by_case,
    get_witnesses_by_case,
    get_suspects_by_case,
    get_cctv_by_case,
    get_risk_score_by_case,
)

# ReportLab imports
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak,
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="ForensiQ — Dashboard",
    page_icon="📊",
    layout="wide",
)
apply_theme()


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def row_to_dict(row):
    if row is None:
        return {}
    try:
        return dict(row)
    except Exception:
        return {}


def fetch_tod_dict(case_id: str) -> dict:
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
        return dict(row) if row else {}
    except Exception:
        return {}


def direct_query(sql: str, params: tuple = ()) -> list:
    """Run a raw SELECT and return list of dicts."""
    try:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = cur.fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def safe_int(val, default=0):
    try:
        return int(val)
    except Exception:
        return default


def risk_badge_color(category: str) -> str:
    return {
        "low": "#28a745",
        "medium": "#ffc107",
        "high": "#fd7e14",
        "critical": "#dc3545",
    }.get(str(category).lower(), "#6c757d")


# ══════════════════════════════════════════════════════════════════════════════
# DATA AGGREGATION
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=30)
def load_dashboard_data():
    data = {}

    # ── All cases ──────────────────────────────────────────────────────────────
    all_cases_raw = get_all_cases()
    all_cases = [_normalize_case(c) for c in all_cases_raw] if all_cases_raw else []
    data["total_cases"] = len(all_cases)

    # Open cases
    data["open_cases"] = sum(
        1 for c in all_cases
        if str(c.get("status", "")).lower() in ("open", "active", "")
    )

    # ── Risk scores ────────────────────────────────────────────────────────────
    risk_rows = direct_query("SELECT * FROM risk_scores ORDER BY created_at DESC")
    data["risk_rows"] = risk_rows

    high_critical = sum(
        1 for r in risk_rows
        if str(r.get("risk_category", "")).lower() in ("high", "critical")
    )
    data["high_critical_count"] = high_critical

    # ── Evidence entry count ───────────────────────────────────────────────────
    evidence_count = 0
    for tbl in ("autopsy_reports", "witness_statements", "tod_estimates",
                "cctv_sightings", "suspects"):
        rows = direct_query(f"SELECT COUNT(*) as cnt FROM {tbl}")
        evidence_count += safe_int(rows[0].get("cnt", 0)) if rows else 0
    data["evidence_count"] = evidence_count

    # ── Cases by status ────────────────────────────────────────────────────────
    status_map = {}
    for c in all_cases:
        s = str(c.get("status", "Unknown")).strip() or "Unknown"
        status_map[s] = status_map.get(s, 0) + 1
    data["cases_by_status"] = status_map

    # ── Cases by type ──────────────────────────────────────────────────────────
    type_map = {}
    for c in all_cases:
        t = str(c.get("case_type", c.get("type", "Unknown"))).strip() or "Unknown"
        type_map[t] = type_map.get(t, 0) + 1
    data["cases_by_type"] = type_map

    # ── Cases over time ────────────────────────────────────────────────────────
    time_rows = direct_query(
        "SELECT DATE(created_at) as day, COUNT(*) as cnt "
        "FROM cases GROUP BY day ORDER BY day"
    )
    data["cases_over_time"] = time_rows

    # ── Recent cases (last 8) ──────────────────────────────────────────────────
    data["recent_cases"] = all_cases[-8:][::-1]

    # ── Recent risk scores (last 8) ────────────────────────────────────────────
    data["recent_risk"] = risk_rows[:8]

    # ── Recent CCTV sightings (last 8) ─────────────────────────────────────────
    cctv_rows = direct_query(
        "SELECT * FROM cctv_sightings ORDER BY created_at DESC LIMIT 8"
    )
    data["recent_cctv"] = cctv_rows

    # ── Recent pattern matches (last 8) ────────────────────────────────────────
    try:
        pattern_rows = direct_query(
            "SELECT * FROM pattern_matches ORDER BY created_at DESC LIMIT 8"
        )
        data["recent_patterns"] = pattern_rows
    except Exception:
        data["recent_patterns"] = []

    return data


# ══════════════════════════════════════════════════════════════════════════════
# CHART BUILDERS
# ══════════════════════════════════════════════════════════════════════════════

CHART_BG = "rgba(0,0,0,0)"
FONT_COLOR = "#e0e0e0"
GRID_COLOR = "#2a2a3a"

def chart_layout(fig, title=""):
    fig.update_layout(
        title=title,
        paper_bgcolor=CHART_BG,
        plot_bgcolor=CHART_BG,
        font_color=FONT_COLOR,
        margin=dict(t=40, b=20, l=20, r=20),
        height=300,
    )
    return fig


def bar_cases_by_status(status_map: dict) -> go.Figure:
    labels = list(status_map.keys())
    values = list(status_map.values())
    color_map = {
        "open": "#e63946", "active": "#e63946",
        "under review": "#ffc107", "closed": "#28a745",
        "archived": "#6c757d",
    }
    bar_colors = [color_map.get(l.lower(), "#457b9d") for l in labels]
    fig = go.Figure(go.Bar(
        x=labels, y=values,
        marker_color=bar_colors,
        text=values, textposition="outside",
    ))
    fig.update_xaxes(showgrid=False, color=FONT_COLOR)
    fig.update_yaxes(gridcolor=GRID_COLOR, color=FONT_COLOR)
    return chart_layout(fig, "Cases by Status")


def pie_cases_by_type(type_map: dict) -> go.Figure:
    fig = go.Figure(go.Pie(
        labels=list(type_map.keys()),
        values=list(type_map.values()),
        hole=0.4,
        marker=dict(colors=px.colors.qualitative.Bold),
        textinfo="label+percent",
    ))
    return chart_layout(fig, "Cases by Type")


def bar_risk_distribution(risk_rows: list) -> go.Figure:
    if not risk_rows:
        fig = go.Figure()
        return chart_layout(fig, "Risk Score Distribution — No Data")

    # Build case_id → case_number map for labels
    all_cases_raw = get_all_cases() or []
    id_to_num = {}
    for c in all_cases_raw:
        nc = _normalize_case(c)
        cid = nc.get("case_id") or nc.get("id") or ""
        num = nc.get("case_number", cid)
        id_to_num[str(cid)] = str(num)

    labels = []
    scores = []
    bar_colors = []
    color_map = {"low": "#28a745", "medium": "#ffc107",
                 "high": "#fd7e14", "critical": "#dc3545"}

    for r in risk_rows:
        cid = str(r.get("case_id", ""))
        labels.append(id_to_num.get(cid, cid))
        scores.append(safe_int(r.get("risk_score", r.get("score", 0))))
        cat = str(r.get("risk_category", r.get("category", ""))).lower()
        bar_colors.append(color_map.get(cat, "#457b9d"))

    fig = go.Figure(go.Bar(
        x=labels, y=scores,
        marker_color=bar_colors,
        text=scores, textposition="outside",
    ))
    fig.update_xaxes(showgrid=False, color=FONT_COLOR, tickangle=-30)
    fig.update_yaxes(gridcolor=GRID_COLOR, color=FONT_COLOR, range=[0, 110])
    return chart_layout(fig, "Risk Score Distribution")


def line_cases_over_time(time_rows: list) -> go.Figure:
    if not time_rows:
        fig = go.Figure()
        return chart_layout(fig, "Cases Over Time — No Data")
    days = [r.get("day", "") for r in time_rows]
    counts = [safe_int(r.get("cnt", 0)) for r in time_rows]
    # Cumulative
    cumulative = []
    total = 0
    for c in counts:
        total += c
        cumulative.append(total)
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=days, y=cumulative,
        mode="lines+markers",
        line=dict(color="#457b9d", width=2),
        marker=dict(color="#e63946", size=6),
        name="Cumulative Cases",
    ))
    fig.add_trace(go.Bar(
        x=days, y=counts,
        marker_color="#2a4a6b",
        name="New Cases",
        opacity=0.6,
    ))
    fig.update_xaxes(showgrid=False, color=FONT_COLOR)
    fig.update_yaxes(gridcolor=GRID_COLOR, color=FONT_COLOR)
    return chart_layout(fig, "Cases Added Over Time")


# ══════════════════════════════════════════════════════════════════════════════
# PDF REPORT BUILDER
# ══════════════════════════════════════════════════════════════════════════════

def build_pdf_report(case_nc: dict) -> bytes:
    """Generate a full ForensiQ case report as PDF bytes."""
    buf = io.BytesIO()
    case_id = case_nc.get("case_id") or case_nc.get("id") or case_nc.get("case_number", "")
    case_num = case_nc.get("case_number", case_id)
    case_title = case_nc.get("title") or case_nc.get("name", "Unknown")

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    styles = getSampleStyleSheet()
    style_normal = styles["Normal"]
    style_normal.fontName = "Helvetica"
    style_normal.fontSize = 9
    style_normal.leading = 13

    style_h1 = ParagraphStyle(
        "H1", parent=styles["Heading1"],
        fontSize=18, textColor=colors.HexColor("#e63946"),
        spaceAfter=6, fontName="Helvetica-Bold",
    )
    style_h2 = ParagraphStyle(
        "H2", parent=styles["Heading2"],
        fontSize=13, textColor=colors.HexColor("#457b9d"),
        spaceAfter=4, fontName="Helvetica-Bold",
        spaceBefore=10,
    )
    style_label = ParagraphStyle(
        "Label", parent=style_normal,
        fontName="Helvetica-Bold", fontSize=9,
    )
    style_center = ParagraphStyle(
        "Center", parent=style_normal,
        alignment=TA_CENTER, fontSize=8,
        textColor=colors.grey,
    )
    style_disclaimer = ParagraphStyle(
        "Disclaimer", parent=style_normal,
        fontSize=7.5, textColor=colors.grey,
        borderColor=colors.HexColor("#fd7e14"),
        borderWidth=1, borderPadding=6,
        backColor=colors.HexColor("#fff3e0"),
    )

    def hr():
        return HRFlowable(width="100%", thickness=0.5,
                          color=colors.HexColor("#444"), spaceAfter=6)

    def kv(label, value):
        if not value:
            return []
        return [
            Paragraph(f"<b>{label}:</b> {str(value)}", style_normal),
            Spacer(1, 3),
        ]

    story = []
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ── Header ─────────────────────────────────────────────────────────────────
    story.append(Paragraph("⚖ ForensiQ", style_h1))
    story.append(Paragraph("AI-Powered Forensic Triage & Intelligence System", style_center))
    story.append(Spacer(1, 8))
    story.append(hr())

    # ── Case summary ───────────────────────────────────────────────────────────
    story.append(Paragraph("CASE SUMMARY", style_h2))
    summary_data = [
        ["Case Number", str(case_num)],
        ["Title", str(case_title)],
        ["Status", str(case_nc.get("status", "N/A"))],
        ["Case Type", str(case_nc.get("case_type", case_nc.get("type", "N/A")))],
        ["Victim", str(case_nc.get("victim_name", case_nc.get("victim", "N/A")))],
        ["Assigned Investigator", str(case_nc.get("assigned_investigator",
                                                   case_nc.get("investigator", "N/A")))],
        ["Report Generated", ts],
    ]
    summary_tbl = Table(summary_data, colWidths=[4 * cm, 12 * cm])
    summary_tbl.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.HexColor("#f8f9fa"), colors.white]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cccccc")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(summary_tbl)
    story.append(Spacer(1, 10))
    story.append(hr())

    # ── Autopsy ────────────────────────────────────────────────────────────────
    story.append(Paragraph("AUTOPSY / FORENSIC REPORT", style_h2))
    try:
        autopsy_row = get_autopsy_by_case(case_id)
        autopsy = row_to_dict(autopsy_row) if autopsy_row else {}
    except Exception:
        autopsy = {}

    if autopsy:
        for field, label in [
            ("cause_of_death", "Cause of Death"),
            ("manner_of_death", "Manner of Death"),
            ("injuries", "Injuries"),
            ("toxicology", "Toxicology"),
            ("soap_subjective", "SOAP — Subjective"),
            ("soap_objective", "SOAP — Objective"),
            ("soap_assessment", "SOAP — Assessment"),
            ("soap_plan", "SOAP — Plan"),
            ("key_terms", "Key Forensic Terms"),
            ("findings", "Additional Findings"),
        ]:
            story += kv(label, autopsy.get(field, ""))
    else:
        story.append(Paragraph("No autopsy report recorded for this case.", style_normal))
    story.append(hr())

    # ── Witnesses ──────────────────────────────────────────────────────────────
    story.append(Paragraph("WITNESS STATEMENTS", style_h2))
    try:
        witness_rows = get_witnesses_by_case(case_id)
        witnesses = [row_to_dict(w) for w in witness_rows] if witness_rows else []
    except Exception:
        witnesses = []

    if witnesses:
        for i, w in enumerate(witnesses, 1):
            name = w.get("witness_name") or w.get("name", f"Witness {i}")
            story.append(Paragraph(f"<b>Witness {i}: {name}</b>", style_label))
            story += kv("Statement", w.get("statement", "")[:600])
            story += kv("Reliability", w.get("reliability_score", w.get("reliability", "")))
            story += kv("Contradictions", w.get("contradictions", ""))
            story.append(Spacer(1, 4))
    else:
        story.append(Paragraph("No witness statements recorded.", style_normal))
    story.append(hr())

    # ── TOD ────────────────────────────────────────────────────────────────────
    story.append(Paragraph("TIME OF DEATH ESTIMATE", style_h2))
    tod = fetch_tod_dict(case_id)
    if tod:
        for field, label in [
            ("estimated_tod", "Estimated TOD"),
            ("time_window_start", "Window Start"),
            ("time_window_end", "Window End"),
            ("confidence_score", "Confidence Score"),
            ("method_used", "Method Used"),
            ("notes", "Notes"),
        ]:
            story += kv(label, tod.get(field, ""))
    else:
        story.append(Paragraph("No TOD estimate recorded.", style_normal))
    story.append(hr())

    # ── CCTV ───────────────────────────────────────────────────────────────────
    story.append(Paragraph("CCTV MOVEMENT TIMELINE", style_h2))
    try:
        cctv_rows = get_cctv_by_case(case_id)
        cctv = [row_to_dict(c) for c in cctv_rows] if cctv_rows else []
    except Exception:
        cctv = []

    if cctv:
        cctv_table_data = [["#", "Timestamp", "Location", "Confidence", "Description"]]
        for i, s in enumerate(cctv, 1):
            cctv_table_data.append([
                str(i),
                str(s.get("timestamp", ""))[:19],
                str(s.get("location", ""))[:30],
                str(s.get("confidence", "")),
                str(s.get("description", ""))[:60],
            ])
        cctv_tbl = Table(
            cctv_table_data,
            colWidths=[1 * cm, 3.5 * cm, 3.5 * cm, 2 * cm, 6 * cm],
        )
        cctv_tbl.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f8f9fa"), colors.white]),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cccccc")),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#457b9d")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(cctv_tbl)
    else:
        story.append(Paragraph("No CCTV sightings recorded.", style_normal))
    story.append(hr())

    # ── Suspects ───────────────────────────────────────────────────────────────
    story.append(Paragraph("SUSPECT SHORTLIST", style_h2))
    try:
        suspect_rows = get_suspects_by_case(case_id)
        suspects = [row_to_dict(s) for s in suspect_rows] if suspect_rows else []
    except Exception:
        suspects = []

    if suspects:
        for i, s in enumerate(suspects, 1):
            name = s.get("suspect_name") or s.get("name", f"Suspect {i}")
            story.append(Paragraph(f"<b>Suspect {i}: {name}</b>", style_label))
            story += kv("Priority Rank", s.get("priority_rank", s.get("priority", "")))
            story += kv("Motive", s.get("motive", ""))
            story += kv("Alibi", s.get("alibi", ""))
            story += kv("Notes", s.get("notes", ""))
            story.append(Spacer(1, 4))
    else:
        story.append(Paragraph("No suspects recorded.", style_normal))
    story.append(hr())

    # ── Risk Score ─────────────────────────────────────────────────────────────
    story.append(Paragraph("RISK ASSESSMENT", style_h2))
    try:
        risk_row = get_risk_score_by_case(case_id)
        risk = row_to_dict(risk_row) if risk_row else {}
    except Exception:
        risk = {}

    if risk:
        score = risk.get("risk_score", risk.get("score", "N/A"))
        cat = risk.get("risk_category", risk.get("category", "N/A"))
        story.append(Paragraph(
            f"<b>Risk Score: {score} / 100 — Category: {cat.upper()}</b>",
            style_label,
        ))
        story.append(Spacer(1, 4))

        # Parse notes JSON if present
        notes_raw = risk.get("notes", "")
        notes_dict = {}
        if notes_raw:
            try:
                notes_dict = json.loads(notes_raw)
            except Exception:
                pass

        if notes_dict:
            story += kv("Confidence", f"{notes_dict.get('confidence', '')}%")
            story += kv("Scoring Rationale", notes_dict.get("rationale", ""))

            red_flags = notes_dict.get("red_flags", [])
            if red_flags:
                story.append(Paragraph("<b>Top Red Flags:</b>", style_label))
                for j, rf in enumerate(red_flags[:5], 1):
                    flag_text = rf.get("flag", "") if isinstance(rf, dict) else str(rf)
                    impl_text = rf.get("implication", "") if isinstance(rf, dict) else ""
                    story.append(Paragraph(
                        f"{j}. {flag_text}" + (f" — {impl_text}" if impl_text else ""),
                        style_normal,
                    ))
                story.append(Spacer(1, 4))

            actions = notes_dict.get("recommended_actions", [])
            if actions:
                story.append(Paragraph("<b>Recommended Actions:</b>", style_label))
                for j, act in enumerate(actions, 1):
                    story.append(Paragraph(f"{j}. {act}", style_normal))
                story.append(Spacer(1, 4))

            gaps = notes_dict.get("evidence_gaps", [])
            if gaps:
                story.append(Paragraph("<b>Evidence Gaps:</b>", style_label))
                for gap in gaps:
                    story.append(Paragraph(f"• {gap}", style_normal))
    else:
        story.append(Paragraph("No risk score recorded.", style_normal))

    story.append(Spacer(1, 12))
    story.append(hr())

    # ── Disclaimer ─────────────────────────────────────────────────────────────
    story.append(Paragraph(
        "DISCLAIMER: This report was generated by ForensiQ, an AI-assisted forensic triage "
        "tool. All findings are probabilistic and AI-generated. They must not be used as the "
        "sole basis for legal, operational, or clinical decisions. Always verify all findings "
        "through qualified forensic professionals and established legal procedures. "
        "ForensiQ does not replace expert forensic analysis.",
        style_disclaimer,
    ))

    story.append(Spacer(1, 8))
    story.append(Paragraph(
        f"Generated by ForensiQ — {ts}",
        style_center,
    ))

    doc.build(story)
    return buf.getvalue()


# ══════════════════════════════════════════════════════════════════════════════
# UI — MAIN DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════

st.title("📊 ForensiQ Command Dashboard")
st.caption("Live overview of all cases, evidence, and risk intelligence")

st.divider()

# Load data
refresh_col, _ = st.columns([1, 5])
if refresh_col.button("🔄 Refresh Dashboard"):
    st.cache_data.clear()

with st.spinner("Loading dashboard data…"):
    data = load_dashboard_data()

# ── Stat row ───────────────────────────────────────────────────────────────────
s1, s2, s3, s4 = st.columns(4)
s1.metric("🗂️ Total Cases", data["total_cases"])
s2.metric("🔴 Open Cases", data["open_cases"])
s3.metric("⚠️ High / Critical Risk", data["high_critical_count"])
s4.metric("🔬 Evidence Entries", data["evidence_count"])

st.divider()

# ── Charts row 1 ───────────────────────────────────────────────────────────────
st.subheader("📈 Case Analytics")
ch1, ch2 = st.columns(2)

with ch1:
    if data["cases_by_status"]:
        st.plotly_chart(
            bar_cases_by_status(data["cases_by_status"]),
            use_container_width=True,
        )
    else:
        st.info("No status data yet.")

with ch2:
    if data["cases_by_type"]:
        st.plotly_chart(
            pie_cases_by_type(data["cases_by_type"]),
            use_container_width=True,
        )
    else:
        st.info("No case type data yet.")

# ── Charts row 2 ───────────────────────────────────────────────────────────────
ch3, ch4 = st.columns(2)

with ch3:
    st.plotly_chart(
        bar_risk_distribution(data["risk_rows"]),
        use_container_width=True,
    )

with ch4:
    st.plotly_chart(
        line_cases_over_time(data["cases_over_time"]),
        use_container_width=True,
    )

st.divider()

# ── Tables section ─────────────────────────────────────────────────────────────
st.subheader("📋 Recent Activity")

tab1, tab2, tab3, tab4 = st.tabs(
    ["🗂️ Recent Cases", "⚠️ Risk Scores", "📹 CCTV Flags", "🔗 Pattern Matches"]
)

# Tab 1 — Recent Cases
with tab1:
    recent_cases = data["recent_cases"]
    if recent_cases:
        for c in recent_cases:
            case_num = c.get("case_number", "?")
            title = c.get("title") or c.get("name", "Untitled")
            victim = c.get("victim_name") or c.get("victim", "N/A")
            status = c.get("status", "Unknown")
            investigator = c.get("assigned_investigator") or c.get("investigator", "N/A")
            st.markdown(
                f"**{case_num}** — {title} &nbsp;|&nbsp; "
                f"👤 Victim: `{victim}` &nbsp;|&nbsp; "
                f"📌 Status: `{status}` &nbsp;|&nbsp; "
                f"🕵️ Investigator: `{investigator}`"
            )
        st.caption(f"Showing last {len(recent_cases)} cases")
    else:
        st.info("No cases recorded yet.")

# Tab 2 — Risk Scores
with tab2:
    recent_risk = data["recent_risk"]
    if recent_risk:
        # Build case_id → label map
        all_cases_raw = get_all_cases() or []
        id_to_label = {}
        for c in all_cases_raw:
            nc = _normalize_case(c)
            cid = str(nc.get("case_id") or nc.get("id") or "")
            label = f"{nc.get('case_number','?')} — {nc.get('title', nc.get('name','?'))}"
            id_to_label[cid] = label

        for r in recent_risk:
            cid = str(r.get("case_id", ""))
            case_label = id_to_label.get(cid, cid)
            score = r.get("risk_score", r.get("score", "N/A"))
            cat = str(r.get("risk_category", r.get("category", "N/A")))
            cat_color = risk_badge_color(cat)
            created = str(r.get("created_at", ""))[:19]
            st.markdown(
                f"**{case_label}** &nbsp;|&nbsp; Score: `{score}/100` &nbsp;|&nbsp; "
                f"<span style='background:{cat_color};color:#fff;"
                f"padding:2px 8px;border-radius:6px;font-size:12px'>"
                f"{cat.upper()}</span> &nbsp;|&nbsp; {created}",
                unsafe_allow_html=True,
            )
    else:
        st.info("No risk scores recorded yet.")

# Tab 3 — CCTV Flags
with tab3:
    recent_cctv = data["recent_cctv"]
    if recent_cctv:
        for s in recent_cctv:
            cid = str(s.get("case_id", ""))
            ts_val = str(s.get("timestamp", ""))[:19]
            loc = s.get("location", "Unknown")
            conf = s.get("confidence", "N/A")
            desc = str(s.get("description", ""))[:80]
            flags = s.get("notes", "")
            flag_str = f" 🚩 `{flags}`" if flags else ""
            st.markdown(
                f"📍 **{loc}** @ `{ts_val}` &nbsp;|&nbsp; Confidence: `{conf}` "
                f"&nbsp;|&nbsp; Case: `{cid}`{flag_str}  \n"
                f"_{desc}_"
            )
    else:
        st.info("No CCTV sightings recorded yet.")

# Tab 4 — Pattern Matches
with tab4:
    recent_patterns = data["recent_patterns"]
    if recent_patterns:
        for p in recent_patterns:
            st.markdown(
                f"🔗 Cases: `{p.get('linked_cases', 'N/A')}` &nbsp;|&nbsp; "
                f"Convergence: `{p.get('convergence', p.get('score', 'N/A'))}%` &nbsp;|&nbsp; "
                f"Date: `{str(p.get('created_at',''))[:19]}`"
            )
    else:
        st.info("No pattern matches recorded yet. Run the Pattern Engine to generate links.")

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# PDF REPORT EXPORT
# ══════════════════════════════════════════════════════════════════════════════

st.subheader("📄 Export Full Case Report (PDF)")

all_cases_raw = get_all_cases()
if not all_cases_raw:
    st.warning("No cases in database.")
else:
    case_options = {}
    for c in all_cases_raw:
        nc = _normalize_case(c)
        label = f"{nc.get('case_number','?')} — {nc.get('title', nc.get('name','Untitled'))}"
        case_options[label] = nc

    pdf_col, btn_col = st.columns([3, 2])

    with pdf_col:
        selected_pdf_label = st.selectbox(
            "Select Case for PDF Report",
            list(case_options.keys()),
            key="pdf_case_select",
        )

    selected_pdf_case = case_options[selected_pdf_label]
    pdf_case_id = (
        selected_pdf_case.get("case_id")
        or selected_pdf_case.get("id")
        or selected_pdf_case.get("case_number", "")
    )
    pdf_case_num = selected_pdf_case.get("case_number", pdf_case_id)

    with btn_col:
        st.markdown("<br>", unsafe_allow_html=True)
        generate_btn = st.button(
            "📑 Generate PDF Report", type="primary", use_container_width=True
        )

    if generate_btn:
        with st.spinner("Compiling full case report…"):
            try:
                pdf_bytes = build_pdf_report(selected_pdf_case)
                filename = f"ForensiQ_Report_{pdf_case_num}.pdf"
                st.success(f"✅ Report compiled — {filename}")
                st.download_button(
                    label=f"📥 Download {filename}",
                    data=pdf_bytes,
                    file_name=filename,
                    mime="application/pdf",
                    type="secondary",
                    use_container_width=True,
                )
            except Exception as e:
                st.error(f"PDF generation failed: {e}")
                st.exception(e)

# ── Disclaimer ─────────────────────────────────────────────────────────────────
st.divider()
st.warning(
    "⚠️ **Disclaimer:** ForensiQ is an AI-assisted investigative support tool. "
    "All data, scores, and reports are for investigative reference only and must "
    "not be used as the sole basis for legal or operational decisions. "
    "Always verify findings with qualified forensic professionals."
)
