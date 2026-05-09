# pages/case_manager.py
# ForensiQ — Case Manager
# Create, view, search, edit, and delete investigation cases.

import streamlit as st
import os
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI

# ── Page config MUST be the very first Streamlit call ─────────────────────────
st.set_page_config(
    page_title="ForensiQ — Case Manager",
    page_icon="🗂️",
    layout="wide"
)

# ── Theme + sidebar ───────────────────────────────────────────────────────────
from theme import apply_theme
apply_theme(active_page="Case Manager")

# ── Database helpers ──────────────────────────────────────────────────────────
from database import (
    generate_case_id,
    insert_case,
    get_all_cases,
    get_case_by_id,
    update_case,
    delete_case,
    get_autopsy_by_case,
    get_witnesses_by_case,
    get_tod_by_case,
    get_suspects_by_case,
    get_risk_score_by_case,
    get_cctv_by_case,
)

# ── Featherless AI client ─────────────────────────────────────────────────────
load_dotenv()
FEATHERLESS_API_KEY = os.getenv("FEATHERLESS_API_KEY")

def get_ai_client():
    """Returns an OpenAI-compatible client pointed at Featherless AI."""
    return OpenAI(
        api_key=FEATHERLESS_API_KEY,
        base_url="https://api.featherless.ai/v1"
    )


# ══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

def status_badge(status):
    """Returns a colored emoji + label for a case status."""
    badges = {
        "Open":         "🟢 Open",
        "Under Review": "🟡 Under Review",
        "Closed":       "🔴 Closed",
    }
    return badges.get(status, f"⚪ {status}")


def priority_badge(priority):
    """Returns a colored emoji + label for a priority level."""
    badges = {
        "Low":      "🔵 Low",
        "Medium":   "🟠 Medium",
        "High":     "🔺 High",
        "Critical": "🚨 Critical",
    }
    return badges.get(priority, f"⚪ {priority}")


def ai_summarize_case(case):
    """
    Calls Featherless AI to generate a concise intelligence summary
    of the case. Returns the summary string or an error message.
    """
    if not FEATHERLESS_API_KEY:
        return "⚠️ No API key found. Add FEATHERLESS_API_KEY to your .env file."

    prompt = f"""You are a forensic intelligence analyst. Based on the following case data, write a concise 3–5 sentence intelligence summary that highlights key facts, identifies any immediate investigative priorities, and flags anything unusual.

Case ID         : {case['case_id']}
Victim          : {case['victim_name']}, {case['victim_age']} years old, {case['victim_gender']}
Case Type       : {case['case_type']}
Incident Date   : {case['incident_date'] or '—'} {case['incident_time'] or ''}
Location        : {case['location']}
Status          : {case['status']}
Priority        : {case['priority']}
Investigator    : {case['assigned_investigator']}
Initial Notes   : {case['initial_notes']}

Write your summary now:"""

    try:
        client = get_ai_client()
        response = client.chat.completions.create(
            model="Qwen/Qwen2.5-72B-Instruct",
            messages=[
                {
                    "role": "system",
                    "content": "You are ForensiQ, an AI forensic intelligence assistant. Be precise, professional, and factual."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            max_tokens=400,
            temperature=0.3,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"⚠️ AI Error: {str(e)}"


# ══════════════════════════════════════════════════════════════════════════════
# SESSION STATE SETUP
# ══════════════════════════════════════════════════════════════════════════════
# Session state lets us remember which view the user is on
# without resetting every time they click something.

if "cm_view" not in st.session_state:
    st.session_state.cm_view = "list"          # 'list', 'detail', 'new'

if "cm_selected_case_id" not in st.session_state:
    st.session_state.cm_selected_case_id = None

if "cm_delete_confirm" not in st.session_state:
    st.session_state.cm_delete_confirm = False

if "cm_ai_summary" not in st.session_state:
    st.session_state.cm_ai_summary = ""

if "cm_edit_mode" not in st.session_state:
    st.session_state.cm_edit_mode = False


# ══════════════════════════════════════════════════════════════════════════════
# VIEW ROUTER — decides which screen to show
# ══════════════════════════════════════════════════════════════════════════════

def show_new_case_form():
    """Renders the New Case creation form."""

    st.markdown("## 🆕 New Investigation Case")
    st.markdown("Fill in all fields below. Case ID is auto-generated.")
    st.markdown("---")

    # Auto-generate Case ID and show it (read-only)
    new_case_id = generate_case_id()
    st.markdown(
        f"""
        <div style="
            background: #1a2a1a;
            border: 1px solid #00ff88;
            border-radius: 8px;
            padding: 12px 20px;
            margin-bottom: 20px;
            display: inline-block;
        ">
            <span style="color: #888; font-size: 13px;">AUTO-GENERATED CASE ID</span><br>
            <span style="color: #00ff88; font-size: 22px; font-weight: bold; 
                         letter-spacing: 2px;">{new_case_id}</span>
        </div>
        """,
        unsafe_allow_html=True
    )

    # ── FORM ──────────────────────────────────────────────────────────────────
    with st.form("new_case_form", clear_on_submit=True):

        st.markdown("### 👤 Victim Information")
        col1, col2, col3 = st.columns([3, 1, 1])
        with col1:
            victim_name = st.text_input(
                "Victim Full Name *",
                placeholder="e.g. Rajesh Kumar"
            )
        with col2:
            victim_age = st.number_input(
                "Age", min_value=0, max_value=120, value=30, step=1
            )
        with col3:
            victim_gender = st.selectbox(
                "Gender", ["Male", "Female", "Unknown", "Other"]
            )

        st.markdown("### 📅 Incident Details")
        col4, col5 = st.columns(2)
        with col4:
            incident_date = st.date_input("Date of Incident *")
        with col5:
            incident_time = st.time_input("Time of Incident")

        location = st.text_input(
            "Location of Discovery *",
            placeholder="e.g. Warehouse near NH-44, Ambattur, Chennai"
        )

        col6, col7 = st.columns(2)
        with col6:
            case_type = st.selectbox(
                "Case Type *",
                ["Homicide", "Suspicious Death", "Accident",
                 "Missing Person", "Unknown"]
            )
        with col7:
            priority = st.selectbox(
                "Priority Level *",
                ["Low", "Medium", "High", "Critical"]
            )

        st.markdown("### 🕵️ Assignment")
        assigned_investigator = st.text_input(
            "Assigned Investigator Name *",
            placeholder="e.g. Inspector Priya Nair"
        )

        st.markdown("### 📝 Initial Notes")
        initial_notes = st.text_area(
            "Initial Notes / Observations",
            placeholder="Describe the scene, first observations, any immediate leads...",
            height=150
        )

        st.markdown("---")
        col_btn1, col_btn2 = st.columns([1, 4])
        with col_btn1:
            submitted = st.form_submit_button(
                "✅ Create Case", use_container_width=True
            )
        with col_btn2:
            cancelled = st.form_submit_button(
                "← Back to Case List", use_container_width=False
            )

    # ── Handle form submission ─────────────────────────────────────────────
    if submitted:
        # Validate required fields
        if not victim_name.strip():
            st.error("❌ Victim Full Name is required.")
        elif not location.strip():
            st.error("❌ Location of Discovery is required.")
        elif not assigned_investigator.strip():
            st.error("❌ Assigned Investigator Name is required.")
        else:
            # Combine date + time into one string
            incident_datetime = f"{incident_date} {incident_time}"

            insert_case({
                "case_id": new_case_id,
                "victim_name": victim_name.strip(),
                "victim_age": victim_age,
                "victim_gender": victim_gender,
                "incident_date": str(incident_date),
                "incident_time": str(incident_time),
                "location": location.strip(),
                "case_type": case_type,
                "priority": priority,
                "assigned_investigator": assigned_investigator.strip(),
                "initial_notes": initial_notes.strip(),
                "status": "Open",
            })

            st.success(f"✅ Case **{new_case_id}** created successfully!")
            st.balloons()

            # Go back to list view after a moment
            st.session_state.cm_view = "list"
            st.rerun()

    if cancelled:
        st.session_state.cm_view = "list"
        st.rerun()


def show_case_list():
    """Renders the searchable case list."""

    # ── Header row ─────────────────────────────────────────────────────────
    col_title, col_btn = st.columns([5, 1])
    with col_title:
        st.markdown("## 🗂️ Case Manager")
        st.markdown("All active and closed investigation cases.")
    with col_btn:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("➕ New Case", use_container_width=True):
            st.session_state.cm_view = "new"
            st.rerun()

    st.markdown("---")

    # ── Fetch all cases ────────────────────────────────────────────────────
    all_cases = get_all_cases()

    if not all_cases:
        st.info("📂 No cases yet. Click **➕ New Case** to create the first one.")
        return

    # ── Search bar + filters ───────────────────────────────────────────────
    st.markdown("### 🔍 Search & Filter")
    col_search, col_status, col_priority = st.columns([3, 1.5, 1.5])

    with col_search:
        search_query = st.text_input(
            "Search",
            placeholder="Search by victim name, location, investigator, case ID...",
            label_visibility="collapsed"
        )
    with col_status:
        status_filter = st.selectbox(
            "Status",
            ["All Statuses", "Open", "Under Review", "Closed"],
            label_visibility="collapsed"
        )
    with col_priority:
        priority_filter = st.selectbox(
            "Priority",
            ["All Priorities", "Critical", "High", "Medium", "Low"],
            label_visibility="collapsed"
        )

    # ── Apply filters ──────────────────────────────────────────────────────
    filtered = []
    q = search_query.lower().strip()

    for case in all_cases:
        # Search filter
        if q:
            searchable = " ".join([
                str(case["case_id"] or ""),
                str(case["victim_name"] or ""),
                str(case["location"] or ""),
                str(case["assigned_investigator"] or ""),
                str(case["case_type"] or ""),
            ]).lower()
            if q not in searchable:
                continue

        # Status filter
        if status_filter != "All Statuses" and case["status"] != status_filter:
            continue

        # Priority filter
        if priority_filter != "All Priorities" and case["priority"] != priority_filter:
            continue

        filtered.append(case)

    # ── Results count ──────────────────────────────────────────────────────
    total = len(all_cases)
    shown = len(filtered)
    st.markdown(
        f"<p style='color:#888; font-size:13px;'>"
        f"Showing {shown} of {total} cases</p>",
        unsafe_allow_html=True
    )

    if not filtered:
        st.warning("🔍 No cases match your search. Try different keywords.")
        return

    st.markdown("---")

    # ── Case cards ─────────────────────────────────────────────────────────
    for case in filtered:
        _render_case_card(case)


def _render_case_card(case):
    """Renders a single case as a clickable card in the list."""

    status_text  = status_badge(case["status"])
    priority_text = priority_badge(case["priority"])
    created = case["created_at"][:10] if case["created_at"] else "Unknown"

    # Card container
    with st.container():
        st.markdown(
            f"""
            <div style="
                background: #1a1a2e;
                border: 1px solid #2a2a4a;
                border-left: 4px solid #00ff88;
                border-radius: 10px;
                padding: 16px 20px;
                margin-bottom: 12px;
            ">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <div>
                        <span style="color:#00ff88; font-weight:bold; font-size:16px;">
                            {case['case_id']}
                        </span>
                        &nbsp;&nbsp;
                        <span style="color:#fff; font-size:15px;">
                            {case['victim_name'] or 'Unknown Victim'}
                        </span>
                    </div>
                    <div style="text-align:right;">
                        <span style="
                            background:#222244; 
                            padding:3px 10px; 
                            border-radius:20px;
                            font-size:12px;
                            margin-right:8px;
                        ">{status_text}</span>
                        <span style="
                            background:#222244; 
                            padding:3px 10px; 
                            border-radius:20px;
                            font-size:12px;
                        ">{priority_text}</span>
                    </div>
                </div>
                <div style="color:#aaa; font-size:13px; margin-top:8px;">
                    📍 {case['location'] or 'Location unknown'} &nbsp;|&nbsp;
                    🔬 {case['case_type'] or 'Type unknown'} &nbsp;|&nbsp;
                    🕵️ {case['assigned_investigator'] or 'Unassigned'} &nbsp;|&nbsp;
                    📅 {created}
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        # "Open Case" button — sits right below the card
        if st.button(
            f"📂 Open  {case['case_id']}",
            key=f"open_{case['case_id']}",
            use_container_width=False
        ):
            st.session_state.cm_selected_case_id = case["case_id"]
            st.session_state.cm_view = "detail"
            st.session_state.cm_edit_mode = False
            st.session_state.cm_delete_confirm = False
            st.session_state.cm_ai_summary = ""
            st.rerun()


def show_case_detail():
    """Renders the full detail page for a selected case."""

    case_id = st.session_state.cm_selected_case_id
    case = get_case_by_id(case_id)

    if not case:
        st.error(f"Case {case_id} not found.")
        if st.button("← Back"):
            st.session_state.cm_view = "list"
            st.rerun()
        return

    # ── Back button + header ────────────────────────────────────────────────
    col_back, col_header = st.columns([1, 6])
    with col_back:
        if st.button("← Back"):
            st.session_state.cm_view = "list"
            st.session_state.cm_edit_mode = False
            st.session_state.cm_delete_confirm = False
            st.session_state.cm_ai_summary = ""
            st.rerun()
    with col_header:
        st.markdown(
            f"## 📁 Case Detail — "
            f"<span style='color:#00ff88'>{case['case_id']}</span>",
            unsafe_allow_html=True
        )

    st.markdown("---")

    # ── Status + priority badges ────────────────────────────────────────────
    col_s, col_p, col_t = st.columns(3)
    with col_s:
        st.markdown(
            f"<div style='text-align:center; background:#1a2a1a; "
            f"border-radius:8px; padding:10px;'>"
            f"<span style='color:#888; font-size:11px;'>STATUS</span><br>"
            f"<span style='font-size:18px;'>{status_badge(case['status'])}</span>"
            f"</div>",
            unsafe_allow_html=True
        )
    with col_p:
        st.markdown(
            f"<div style='text-align:center; background:#1a1a2a; "
            f"border-radius:8px; padding:10px;'>"
            f"<span style='color:#888; font-size:11px;'>PRIORITY</span><br>"
            f"<span style='font-size:18px;'>{priority_badge(case['priority'])}</span>"
            f"</div>",
            unsafe_allow_html=True
        )
    with col_t:
        st.markdown(
            f"<div style='text-align:center; background:#2a1a1a; "
            f"border-radius:8px; padding:10px;'>"
            f"<span style='color:#888; font-size:11px;'>CASE TYPE</span><br>"
            f"<span style='font-size:18px; color:#ff8888;'>{case['case_type'] or 'Unknown'}</span>"
            f"</div>",
            unsafe_allow_html=True
        )

    st.markdown("---")

    # ── Victim + Incident Information ───────────────────────────────────────
    st.markdown("### 👤 Victim & Incident Information")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**Victim Name:** {case['victim_name'] or '—'}")
        st.markdown(f"**Age:** {case['victim_age'] or '—'}")
        st.markdown(f"**Gender:** {case['victim_gender'] or '—'}")
    with col2:
        st.markdown(f"**Incident Date/Time:** {case['incident_date'] or '—'}  {case['incident_time'] or ''}")
        st.markdown(f"**Location:** {case['location'] or '—'}")
        st.markdown(f"**Assigned Investigator:** {case['assigned_investigator'] or '—'}")

    st.markdown("---")

    # ── Initial Notes ───────────────────────────────────────────────────────
    st.markdown("### 📝 Initial Notes")
    st.markdown(
        f"""
        <div style="background:#111122; border-left:3px solid #00ff88;
                    padding:15px; border-radius:5px; color:#ccc;">
            {case['initial_notes'] or '<em style="color:#555">No initial notes recorded.</em>'}
        </div>
        """,
        unsafe_allow_html=True
    )

    st.markdown("---")

    # ── Linked Evidence (from other modules) ────────────────────────────────
    st.markdown("### 🔗 Linked Evidence & Records")

    # Autopsy Reports
    with st.expander("🧬 Autopsy Reports"):
        reports = get_autopsy_by_case(case_id)
        if reports:
            for r in reports:
                st.markdown(f"**Cause of Death:** {r['cause_of_death']}")
                st.markdown(r["report_text"])
                st.markdown(f"*Uploaded: {r['uploaded_at']}*")
                st.markdown("---")
        else:
            st.info("No autopsy reports linked to this case yet. "
                    "Add them in the Report Analyzer module.")

    # Witnesses
    with st.expander("🗣️ Witness Statements"):
        witnesses = get_witnesses_by_case(case_id)
        if witnesses:
            for w in witnesses:
                st.markdown(f"**{w['witness_name']}** — {w['recorded_at']}")
                st.markdown(w["statement_text"])
                st.markdown("---")
        else:
            st.info("No witness statements linked to this case yet.")

    # TOD Estimate
    with st.expander("⏱️ Time of Death Estimate"):
        tod = get_tod_by_case(case_id)
        if tod:
            for t in tod:
                st.markdown(f"**Estimated TOD:** {t['estimated_tod']}")
                st.markdown(f"**Method:** {t['method_used']}")
                st.markdown(f"**Confidence:** {t['confidence']}")
                if t["notes"]:
                    st.markdown(f"*Notes: {t['notes']}*")
        else:
            st.info("No TOD estimate yet. Use the TOD Estimator module.")

    # Suspects
    with st.expander("🚨 Suspects"):
        suspects = get_suspects_by_case(case_id)
        if suspects:
            for s in suspects:
                st.markdown(
                    f"**{s['suspect_name']}** — {s['age']} yrs, {s['gender']} — "
                    f"Relation: {s['relation']}"
                )
                if s["notes"]:
                    st.markdown(f"*{s['notes']}*")
                st.markdown("---")
        else:
            st.info("No suspects added yet. Use the Forensic Profiler module.")

    # Risk Score
    with st.expander("📊 Risk Score"):
        risk = get_risk_score_by_case(case_id)
        if risk:
            st.markdown(f"**Score:** {risk['score']}")
            st.markdown(f"**Risk Level:** {risk['risk_level']}")
            st.markdown(f"**Factors:** {risk['factors']}")
            st.markdown(f"*Calculated: {risk['calculated_at']}*")
        else:
            st.info("No risk score calculated yet. Use the Risk Scorer module.")

    # CCTV Logs
    with st.expander("📹 CCTV Logs"):
        cctv = get_cctv_by_case(case_id)
        if cctv:
            for c in cctv:
                flag = "🚩 FLAGGED" if c["flagged"] else ""
                st.markdown(
                    f"**{c['camera_location']}** — {c['timestamp']} {flag}"
                )
                st.markdown(c["description"])
                st.markdown("---")
        else:
            st.info("No CCTV logs linked yet. Use the CCTV Tracker module.")

    st.markdown("---")

    # ── Action Buttons Row ──────────────────────────────────────────────────
    st.markdown("### ⚙️ Case Actions")
    col_edit, col_ai, col_del = st.columns([1, 1, 1])

    with col_edit:
        edit_label = "💾 Save Changes" if st.session_state.cm_edit_mode else "✏️ Edit Case"
        if st.button(edit_label, use_container_width=True):
            st.session_state.cm_edit_mode = not st.session_state.cm_edit_mode
            st.rerun()

    with col_ai:
        if st.button("🤖 AI Summary", use_container_width=True):
            with st.spinner("ForensiQ AI is analyzing the case..."):
                summary = ai_summarize_case(case)
                st.session_state.cm_ai_summary = summary
            st.rerun()

    with col_del:
        if st.button("🗑️ Delete Case", use_container_width=True):
            st.session_state.cm_delete_confirm = True
            st.rerun()

    # ── Edit Form ───────────────────────────────────────────────────────────
    if st.session_state.cm_edit_mode:
        st.markdown("---")
        st.markdown("### ✏️ Edit Case Details")

        status_options   = ["Open", "Under Review", "Closed"]
        priority_options = ["Low", "Medium", "High", "Critical"]

        current_status_idx   = status_options.index(case["status"]) \
                               if case["status"] in status_options else 0
        current_priority_idx = priority_options.index(case["priority"]) \
                               if case["priority"] in priority_options else 1

        with st.form("edit_case_form"):
            new_status = st.selectbox(
                "Status", status_options, index=current_status_idx
            )
            new_priority = st.selectbox(
                "Priority", priority_options, index=current_priority_idx
            )
            new_notes = st.text_area(
                "Update Notes",
                value=case["initial_notes"] or "",
                height=150
            )
            save_btn = st.form_submit_button("💾 Save Changes")

        if save_btn:
            update_case(case_id, new_status, new_priority, new_notes)
            st.success("✅ Case updated successfully!")
            st.session_state.cm_edit_mode = False
            st.rerun()

    # ── AI Summary Display ──────────────────────────────────────────────────
    if st.session_state.cm_ai_summary:
        st.markdown("---")
        st.markdown("### 🤖 AI Intelligence Summary")
        st.markdown(
            f"""
            <div style="
                background: #0d1a0d;
                border: 1px solid #00ff88;
                border-left: 5px solid #00ff88;
                border-radius: 8px;
                padding: 20px;
                color: #ccffcc;
                font-size: 15px;
                line-height: 1.8;
            ">
                {st.session_state.cm_ai_summary}
            </div>
            """,
            unsafe_allow_html=True
        )

    # ── Delete Confirmation ─────────────────────────────────────────────────
    if st.session_state.cm_delete_confirm:
        st.markdown("---")
        st.warning(
            f"⚠️ **Are you sure you want to permanently delete case "
            f"{case_id}?**\n\n"
            f"This will also delete ALL linked records "
            f"(autopsy reports, witnesses, suspects, etc.). "
            f"This action **cannot be undone.**"
        )
        col_yes, col_no = st.columns(2)
        with col_yes:
            if st.button("🗑️ Yes, Delete Permanently", use_container_width=True):
                delete_case(case_id)
                st.success(f"Case {case_id} has been deleted.")
                st.session_state.cm_view = "list"
                st.session_state.cm_selected_case_id = None
                st.session_state.cm_delete_confirm = False
                st.rerun()
        with col_no:
            if st.button("❌ Cancel — Keep Case", use_container_width=True):
                st.session_state.cm_delete_confirm = False
                st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# MAIN — VIEW ROUTER
# ══════════════════════════════════════════════════════════════════════════════

def main():
    if st.session_state.cm_view == "new":
        show_new_case_form()
    elif st.session_state.cm_view == "detail":
        show_case_detail()
    else:
        show_case_list()


main()