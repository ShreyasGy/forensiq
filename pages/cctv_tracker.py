"""
ForensiQ — CCTV & Location Tracker  (Session 5 — Rebuilt)
──────────────────────────────────────────────────────────
Tab 1 : Person Profile Builder     — store who you're looking for
Tab 2 : Log Sightings              — AI auto-rates confidence vs profile
Tab 3 : Movement Intelligence      — AI writes a full forensic brief
Tab 4 : Map & Timeline             — visual movement map + timeline table
"""

import os
import io
import json
from datetime import datetime

import pandas as pd
import folium
import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI
from streamlit_folium import st_folium

load_dotenv()

# ── Page config (MUST be first Streamlit call) ────────────────────────────────
st.set_page_config(
    page_title="ForensiQ — CCTV Tracker",
    page_icon="📹",
    layout="wide",
)

from theme import apply_theme
apply_theme(active_page="CCTV Tracker")

from database import (
    get_all_cases,
    get_cctv_by_case,
    insert_cctv_sighting,
    get_tracked_persons_by_case,
    insert_tracked_person,
)

# ── Featherless AI client ─────────────────────────────────────────────────────
_client = OpenAI(
    api_key=os.getenv("FEATHERLESS_API_KEY"),
    base_url="https://api.featherless.ai/v1",
)
MODEL = "meta-llama/Llama-3.3-70B-Instruct"


def ai_call(system_prompt: str, user_prompt: str, max_tokens: int = 1200) -> str:
    """Single wrapper for all Featherless AI calls."""
    try:
        resp = _client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content.strip()
    except Exception as exc:
        return f"⚠️ AI Error: {exc}"


# ── Confidence colour helpers ─────────────────────────────────────────────────
CONF_COLOURS = {
    "High":   ("🟢", "green"),
    "Medium": ("🟡", "orange"),
    "Low":    ("🔴", "red"),
    "Not":    ("⚫", "gray"),
}

def conf_emoji(confidence_str: str) -> str:
    for key, (emoji, _) in CONF_COLOURS.items():
        if key in confidence_str:
            return f"{emoji} {confidence_str}"
    return confidence_str

def conf_map_colour(confidence_str: str) -> str:
    for key, (_, colour) in CONF_COLOURS.items():
        if key in confidence_str:
            return colour
    return "blue"


# ─────────────────────────────────────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────────────────────────────────────

st.title("📹 CCTV & Location Tracker")
st.markdown(
    "Build a person profile, log camera sightings, then let AI analyse "
    "the full movement timeline for gaps, patterns, and alibi conflicts."
)

# ── Case selector ─────────────────────────────────────────────────────────────
cases = get_all_cases()
if not cases:
    st.warning(
        "⚠️ No cases found. Go to **Case Manager** and create a case first."
    )
    st.stop()

case_options = {f"{c['case_id']} — {c['name']}": c["case_id"] for c in cases}
selected_label   = st.selectbox("🗂️ Active Case", list(case_options.keys()))
selected_case_id = case_options[selected_label]

st.divider()


# ═════════════════════════════════════════════════════════════════════════════
# TABS
# ═════════════════════════════════════════════════════════════════════════════

tab_profile, tab_log, tab_intel, tab_map = st.tabs([
    "👤 Person Profile",
    "📝 Log Sightings",
    "🧠 Movement Intelligence",
    "🗺️ Map & Timeline",
])


# ─────────────────────────────────────────────────────────────────────────────
# TAB 1 — PERSON PROFILE BUILDER
# ─────────────────────────────────────────────────────────────────────────────

with tab_profile:
    st.subheader("👤 Person Profile Builder")
    st.markdown(
        "Describe the person you are tracking. This profile is used in "
        "**Tab 2** to automatically rate whether each camera sighting "
        "matches this person."
    )

    # ── Show existing profiles ────────────────────────────────────────────
    existing_profiles = get_tracked_persons_by_case(selected_case_id)
    if existing_profiles:
        st.markdown(f"**{len(existing_profiles)} profile(s) saved for this case:**")
        for p in existing_profiles:
            label = p["name"]
            if p.get("alias"):
                label += f"  /  {p['alias']}"
            with st.expander(f"🔍 {label}"):
                c1, c2, c3 = st.columns(3)
                c1.metric("Height", f"{p.get('height_cm', '?')} cm")
                c2.metric("Weight", f"{p.get('weight_kg', '?')} kg")
                c3.metric("Last Seen", p.get("last_seen_location") or "Unknown")
                st.markdown("**Hair:**")
                st.write(f"{p.get('hair_color','?')} — {p.get('hair_length','?')}")
                st.markdown("**Clothing:**")
                st.write(
                    f"Top: {p.get('clothing_top','—')}  |  "
                    f"Bottom: {p.get('clothing_bottom','—')}  |  "
                    f"Footwear: {p.get('footwear','—')}"
                )
                if p.get("accessories"):
                    st.markdown(f"**Accessories:** {p['accessories']}")
                if p.get("distinguishing_features"):
                    st.markdown(f"**Distinguishing Features:** {p['distinguishing_features']}")
                st.markdown("---")
                st.markdown("**📋 CCTV Identification Checklist (for camera operators):**")
                st.info(p.get("cctv_description") or "*(not generated)*")
        st.divider()

    # ── New profile form ──────────────────────────────────────────────────
    st.markdown("### ➕ Add New Person Profile")

    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown("**Identity**")
        p_name  = st.text_input("Full Name or ID *", placeholder="e.g.  John Doe  or  UNKNOWN-01")
        p_alias = st.text_input("Alias / Nickname", placeholder="e.g.  'The Limping Man'")

        st.markdown("**Build**")
        p_height = st.number_input("Height (cm)", min_value=100, max_value=250, value=170)
        p_weight = st.number_input("Weight (kg)", min_value=30,  max_value=200, value=70)

        st.markdown("**Hair**")
        p_hair_color  = st.selectbox("Hair Colour",
            ["Black","Dark Brown","Brown","Light Brown","Blonde",
             "Red / Auburn","Grey","White","Bald","Other"])
        p_hair_length = st.selectbox("Hair Length",
            ["Bald / Shaved","Very Short (buzz cut)","Short (above ears)",
             "Medium (ear to shoulder)","Long (below shoulder)","Very Long"])

    with col_right:
        st.markdown("**Clothing**")
        p_top      = st.text_input("Top",      placeholder="e.g.  Red hoodie")
        p_bottom   = st.text_input("Bottom",   placeholder="e.g.  Dark blue jeans")
        p_footwear = st.text_input("Footwear", placeholder="e.g.  White sneakers")
        p_access   = st.text_input("Accessories / Bags", placeholder="e.g.  Blue backpack, Black cap")

        st.markdown("**Distinguishing Features**")
        p_features = st.text_area(
            "Visible marks, gait, behaviour",
            placeholder="e.g.  Limp on right leg\nTattoo on left forearm\nFrequently checks phone",
            height=115,
        )

    st.markdown("**📍 Last Confirmed Alive Sighting**")
    loc_col, time_col = st.columns(2)
    with loc_col:
        p_last_loc  = st.text_input("Location", placeholder="e.g.  Central Market Gate 3")
    with time_col:
        p_last_time = st.text_input("Date & Time", placeholder="e.g.  2025-05-09 14:30")

    st.markdown("---")
    if st.button("🤖 Generate Identification Checklist with AI", type="primary", use_container_width=True):
        if not p_name.strip():
            st.error("❌ Please enter a Name or ID before generating.")
        else:
            profile_text = f"""
Name/ID         : {p_name}
Alias           : {p_alias or 'None'}
Height          : approximately {p_height} cm
Weight          : approximately {p_weight} kg
Hair            : {p_hair_color}, {p_hair_length}
Top clothing    : {p_top or 'Unknown'}
Bottom clothing : {p_bottom or 'Unknown'}
Footwear        : {p_footwear or 'Unknown'}
Accessories     : {p_access or 'None'}
Distinguishing  : {p_features or 'None noted'}
Last seen at    : {p_last_loc or 'Unknown location'}
Last seen time  : {p_last_time or 'Unknown time'}
"""
            system = (
                "You are a forensic intelligence analyst. Your job is to produce "
                "a structured CCTV Operator Identification Checklist.\n\n"
                "Format your output EXACTLY like this:\n\n"
                "BUILD: [one sentence — height, weight, body type]\n"
                "HAIR: [one sentence — colour and length]\n"
                "TOP: [exact garment description]\n"
                "BOTTOM: [exact garment description]\n"
                "FOOTWEAR: [exact description]\n"
                "ACCESSORIES: [bags, hats, jewellery — or 'None visible']\n"
                "IDENTIFIERS: [distinguishing marks, gait, behaviour — most important for matching]\n"
                "LAST SEEN: [location and time]\n\n"
                "Rules:\n"
                "- Be precise. Use only the information provided.\n"
                "- Write IDENTIFIERS as the most actionable field — "
                "  this is what camera operators scan for first.\n"
                "- Do not include the person's name.\n"
                "- Keep every line to one sentence maximum."
            )
            with st.spinner("AI is generating the identification checklist…"):
                result = ai_call(system, f"Generate identification checklist:\n{profile_text}")

            st.session_state["cctv_checklist_result"]  = result
            st.session_state["cctv_checklist_profile"] = {
                "name": p_name, "alias": p_alias,
                "height_cm": p_height, "weight_kg": p_weight,
                "hair_color": p_hair_color, "hair_length": p_hair_length,
                "clothing_top": p_top, "clothing_bottom": p_bottom,
                "footwear": p_footwear, "accessories": p_access,
                "distinguishing_features": p_features,
                "last_seen_location": p_last_loc,
                "last_seen_time": p_last_time,
            }

    if st.session_state.get("cctv_checklist_result"):
        st.success("✅ Identification checklist generated!")
        st.markdown("**📋 CCTV Operator Identification Checklist** *(edit if needed before saving)*")
        edited = st.text_area(
            "Review / edit:",
            value=st.session_state["cctv_checklist_result"],
            height=200,
        )

        if st.button("💾 Save Profile to Case", use_container_width=True):
            prof = st.session_state.get("cctv_checklist_profile", {})
            try:
                insert_tracked_person(
                    case_id                 = selected_case_id,
                    name                    = prof.get("name", p_name),
                    alias                   = prof.get("alias", p_alias),
                    height_cm               = prof.get("height_cm", p_height),
                    weight_kg               = prof.get("weight_kg", p_weight),
                    hair_color              = prof.get("hair_color", p_hair_color),
                    hair_length             = prof.get("hair_length", p_hair_length),
                    clothing_top            = prof.get("clothing_top", p_top),
                    clothing_bottom         = prof.get("clothing_bottom", p_bottom),
                    footwear                = prof.get("footwear", p_footwear),
                    accessories             = prof.get("accessories", p_access),
                    distinguishing_features = prof.get("distinguishing_features", p_features),
                    last_seen_location      = prof.get("last_seen_location", p_last_loc),
                    last_seen_time          = prof.get("last_seen_time", p_last_time),
                    cctv_description        = edited,
                )
                st.success(f"✅ Profile saved for **{prof.get('name', p_name)}**!")
                del st.session_state["cctv_checklist_result"]
                del st.session_state["cctv_checklist_profile"]
                st.rerun()
            except Exception as exc:
                st.error(f"❌ Save failed: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# TAB 2 — LOG SIGHTINGS  (AI auto-rates confidence)
# ─────────────────────────────────────────────────────────────────────────────

with tab_log:
    st.subheader("📝 Log Sightings")
    st.markdown(
        "Describe what a camera captured. AI will compare it against the "
        "saved person profile and **automatically suggest the confidence rating**."
    )

    # ── Load profile for this case ────────────────────────────────────────
    profiles = get_tracked_persons_by_case(selected_case_id)
    active_profile_text = ""
    if profiles:
        profile_names = [
            f"{p['name']}" + (f" / {p['alias']}" if p.get("alias") else "")
            for p in profiles
        ]
        chosen_profile_idx = st.selectbox(
            "Which profile are you logging sightings for?",
            range(len(profiles)),
            format_func=lambda i: profile_names[i],
        )
        chosen_profile = profiles[chosen_profile_idx]
        active_profile_text = chosen_profile.get("cctv_description", "")
        with st.expander("📋 Active Profile Checklist"):
            st.info(active_profile_text or "*(no checklist saved — go to Person Profile tab)*")
    else:
        st.info(
            "ℹ️ No person profile saved for this case yet. "
            "Go to **Person Profile** tab first. "
            "You can still log sightings manually without AI rating."
        )

    st.divider()

    # ── Two sub-tabs: Manual and CSV ──────────────────────────────────────
    sub_manual, sub_csv = st.tabs(["📝 Single Entry", "📁 Bulk CSV Upload"])

    # ── SINGLE ENTRY ──────────────────────────────────────────────────────
    with sub_manual:
        st.markdown("#### Add One Sighting")

        col_a, col_b = st.columns(2)
        with col_a:
            m_camera    = st.text_input("Camera ID", placeholder="e.g.  CAM-001")
            m_location  = st.text_input("Location Name *", placeholder="e.g.  North Entrance, Level 1")
            m_timestamp = st.text_input(
                "Timestamp *",
                value=datetime.now().strftime("%Y-%m-%d %H:%M"),
                placeholder="YYYY-MM-DD HH:MM",
            )
        with col_b:
            st.markdown("**GPS Coordinates** *(optional — enables movement map)*")
            m_lat = st.number_input("Latitude",  value=0.0, format="%.6f")
            m_lng = st.number_input("Longitude", value=0.0, format="%.6f")
            st.caption("💡 Right-click in Google Maps → first line = lat, lng")

        m_description = st.text_area(
            "What did the camera capture? *",
            placeholder=(
                "Describe exactly what was visible.\n"
                "e.g.  Person in red hoodie and dark jeans entered through north door "
                "carrying a blue backpack. Clear limp on right leg. Did not look at camera."
            ),
            height=130,
        )
        m_notes = st.text_area(
            "Additional Notes *(optional)*",
            placeholder="e.g.  Camera angle partially obstructed. Face not clearly captured.",
            height=60,
        )

        if st.button("🤖 Rate & Save Sighting", type="primary", use_container_width=True):
            if not m_location.strip() or not m_description.strip():
                st.error("❌ Location and Description are required.")
            else:
                # ── AI rates the confidence ────────────────────────────────
                if active_profile_text:
                    with st.spinner("AI is comparing this sighting against the profile…"):
                        rate_system = (
                            "You are a forensic intelligence analyst assessing CCTV footage.\n"
                            "You will be given a CCTV Operator Identification Checklist for "
                            "a target person, and a description of what a camera captured.\n\n"
                            "Your job: Rate how likely it is that the camera captured the target.\n\n"
                            "Respond with EXACTLY this format (no extra text):\n"
                            "CONFIDENCE: [High — Definite Match / Medium — Likely Match / "
                            "Low — Possible Match / Not Seen]\n"
                            "REASON: [One sentence explaining why you chose that rating, "
                            "listing which features matched or didn't match.]\n\n"
                            "Matching rules:\n"
                            "- High: 3+ distinctive features clearly match (clothing, gait, accessories)\n"
                            "- Medium: 1-2 features match but others are unclear or missing\n"
                            "- Low: Only vague similarities, nothing distinctive confirmed\n"
                            "- Not Seen: No match at all, or camera captured a different person entirely"
                        )
                        rate_user = (
                            f"TARGET PROFILE CHECKLIST:\n{active_profile_text}\n\n"
                            f"CAMERA SIGHTING DESCRIPTION:\n{m_description}"
                        )
                        rating_raw = ai_call(rate_system, rate_user, max_tokens=200)

                    # Parse CONFIDENCE line
                    confidence_val = "Low — Possible Match"
                    reason_val = ""
                    for line in rating_raw.splitlines():
                        if line.startswith("CONFIDENCE:"):
                            confidence_val = line.replace("CONFIDENCE:", "").strip()
                        elif line.startswith("REASON:"):
                            reason_val = line.replace("REASON:", "").strip()

                    # Show the AI's verdict before saving
                    emoji = conf_emoji(confidence_val)
                    st.markdown(f"### AI Confidence Rating: {emoji}")
                    if reason_val:
                        st.info(f"**Reasoning:** {reason_val}")

                    # Offer override
                    final_confidence = st.selectbox(
                        "Accept AI rating or override:",
                        [
                            confidence_val,
                            "High — Definite Match",
                            "Medium — Likely Match",
                            "Low — Possible Match",
                            "Not Seen",
                        ],
                        index=0,
                        key="confidence_override",
                    )
                    # Merge reason into notes
                    merged_notes = m_notes
                    if reason_val:
                        merged_notes = f"[AI Rating Reason: {reason_val}] {m_notes}".strip()

                else:
                    # No profile — manual confidence
                    final_confidence = st.selectbox(
                        "Confidence Level *",
                        ["High — Definite Match", "Medium — Likely Match",
                         "Low — Possible Match", "Not Seen"],
                    )
                    merged_notes = m_notes

                if st.button("💾 Confirm & Save", use_container_width=True):
                    lat = m_lat if m_lat != 0.0 else None
                    lng = m_lng if m_lng != 0.0 else None
                    try:
                        insert_cctv_sighting(
                            case_id     = selected_case_id,
                            timestamp   = m_timestamp,
                            location    = m_location,
                            description = m_description,
                            latitude    = lat,
                            longitude   = lng,
                            confidence  = final_confidence,
                            notes       = merged_notes,
                            camera_id   = m_camera,
                        )
                        st.success(f"✅ Sighting saved! {m_camera} | {m_location} | {m_timestamp}")
                        st.balloons()
                    except Exception as exc:
                        st.error(f"❌ Save failed: {exc}")

    # ── BULK CSV UPLOAD ───────────────────────────────────────────────────
    with sub_csv:
        st.markdown("#### Bulk Upload via CSV")
        st.markdown("""
**Required columns** (exact names, lowercase):
`camera_id` · `location` · `timestamp` · `description`

**Optional columns:**
`confidence` · `latitude` · `longitude` · `notes`

If `confidence` column is missing or blank, AI will auto-rate every row against the saved profile.
""")

        with st.expander("📋 Download a filled sample CSV"):
            sample = pd.DataFrame({
                "camera_id":   ["CAM-001","CAM-004","CAM-007","CAM-012","CAM-015","CAM-018"],
                "location":    [
                    "Main Entrance — Ground Floor",
                    "Escalator to Level 2",
                    "Food Court — Level 2",
                    "Emergency Exit — Level 2 East",
                    "Parking Lot B — Row 3",
                    "Parking Lot B — Exit Barrier",
                ],
                "timestamp":   [
                    "2025-05-09 08:15","2025-05-09 08:23","2025-05-09 08:31",
                    "2025-05-09 08:47","2025-05-09 08:52","2025-05-09 09:01",
                ],
                "description": [
                    "Person in red hoodie and dark jeans entered through main door. Blue backpack. Noticeable limp on right leg.",
                    "Same individual boarded escalator to Level 2. Did not look at cameras. Blue backpack under right arm.",
                    "Individual matching description seated at corner table. Backpack under chair. Made phone call for approx 4 minutes.",
                    "Subject exited via emergency door, triggering alarm briefly. Moved quickly toward parking. Running gait.",
                    "Figure in red hoodie approached blue sedan near Row 3. Retrieved item from boot of vehicle.",
                    "Blue sedan with tinted windows exited parking at speed. Subject not observed on foot after this point.",
                ],
                "confidence":  [
                    "High — Definite Match","Medium — Likely Match","High — Definite Match",
                    "High — Definite Match","Medium — Likely Match","Low — Possible Match",
                ],
                "latitude":  [13.082700,13.082750,13.082900,13.083100,13.083300,13.083400],
                "longitude": [80.270700,80.270800,80.271000,80.271200,80.271500,80.271600],
                "notes": [
                    "Clear footage — face partially captured",
                    "Side-angle view only",
                    "Face captured at 08:34 — extract clip",
                    "Motion-triggered — 12 second clip only",
                    "Low-light — reduced quality",
                    "Partial plate visible: TN 09",
                ],
            })
            st.dataframe(sample, use_container_width=True)
            st.download_button(
                "⬇️ Download sample_cctv_log.csv",
                data=sample.to_csv(index=False).encode(),
                file_name="sample_cctv_log.csv",
                mime="text/csv",
            )

        uploaded = st.file_uploader("Upload your CCTV log CSV", type=["csv"])

        if uploaded is not None:
            try:
                df = pd.read_csv(uploaded)
            except Exception as exc:
                st.error(f"❌ Could not read file: {exc}")
                df = None

            if df is not None:
                df.columns = df.columns.str.lower()
                st.success(f"✅ File loaded — **{len(df)} rows** detected.")
                st.dataframe(df, use_container_width=True)

                required_cols = {"camera_id", "location", "timestamp", "description"}
                missing = required_cols - set(df.columns)
                if missing:
                    st.error(f"❌ Missing required column(s): **{', '.join(sorted(missing))}**")
                else:
                    needs_rating = (
                        "confidence" not in df.columns
                        or df["confidence"].isna().any()
                        or (df["confidence"].astype(str).str.strip() == "").any()
                    )
                    if needs_rating and active_profile_text:
                        st.info(
                            "ℹ️ Some or all rows are missing confidence ratings. "
                            "AI will auto-rate them against the saved profile."
                        )

                    if st.button(
                        f"📥 Import all {len(df)} rows into case {selected_case_id}",
                        type="primary",
                        use_container_width=True,
                    ):
                        ok, fail = 0, 0
                        bar = st.progress(0, text="Importing…")

                        for i, row in df.iterrows():
                            try:
                                # Determine confidence
                                conf_val = str(row.get("confidence", "")).strip()
                                if (
                                    not conf_val
                                    or conf_val.lower() in ("nan", "none", "")
                                ) and active_profile_text:
                                    # AI rates this row
                                    rate_sys = (
                                        "You are a forensic analyst. Rate whether a camera "
                                        "sighting matches a target profile. Reply with ONLY:\n"
                                        "CONFIDENCE: [High — Definite Match / Medium — Likely Match / "
                                        "Low — Possible Match / Not Seen]"
                                    )
                                    rate_u = (
                                        f"PROFILE:\n{active_profile_text}\n\n"
                                        f"SIGHTING:\n{row['description']}"
                                    )
                                    ai_out = ai_call(rate_sys, rate_u, max_tokens=60)
                                    for ln in ai_out.splitlines():
                                        if ln.startswith("CONFIDENCE:"):
                                            conf_val = ln.replace("CONFIDENCE:", "").strip()
                                            break
                                    if not conf_val:
                                        conf_val = "Low — Possible Match"
                                elif not conf_val:
                                    conf_val = "Low — Possible Match"

                                lat = (
                                    float(row["latitude"])
                                    if "latitude" in df.columns
                                    and pd.notna(row.get("latitude"))
                                    and str(row.get("latitude")).strip() not in ("", "0")
                                    else None
                                )
                                lng = (
                                    float(row["longitude"])
                                    if "longitude" in df.columns
                                    and pd.notna(row.get("longitude"))
                                    and str(row.get("longitude")).strip() not in ("", "0")
                                    else None
                                )
                                notes_val = (
                                    str(row["notes"])
                                    if "notes" in df.columns and pd.notna(row.get("notes"))
                                    else ""
                                )
                                insert_cctv_sighting(
                                    case_id     = selected_case_id,
                                    timestamp   = str(row["timestamp"]),
                                    location    = str(row["location"]),
                                    description = str(row["description"]),
                                    latitude    = lat,
                                    longitude   = lng,
                                    confidence  = conf_val,
                                    notes       = notes_val,
                                    camera_id   = str(row.get("camera_id", "")),
                                )
                                ok += 1
                            except Exception:
                                fail += 1

                            bar.progress((i + 1) / len(df), text=f"Importing row {i+1} of {len(df)}…")

                        if fail == 0:
                            st.success(f"✅ All **{ok}** entries imported successfully!")
                            st.balloons()
                        else:
                            st.warning(f"Import finished: **{ok}** saved, **{fail}** failed.")


# ─────────────────────────────────────────────────────────────────────────────
# TAB 3 — MOVEMENT INTELLIGENCE  (the real AI work)
# ─────────────────────────────────────────────────────────────────────────────

with tab_intel:
    st.subheader("🧠 Movement Intelligence Brief")
    st.markdown(
        "AI reads **every sighting** logged for this case and produces a "
        "structured forensic intelligence brief covering timeline gaps, "
        "suspicious patterns, alibi checks, and next-camera recommendations."
    )

    sightings = get_cctv_by_case(selected_case_id)

    if not sightings:
        st.info(
            "No sightings logged yet. Use the **Log Sightings** tab to add entries first."
        )
    else:
        st.metric("Sightings available for analysis", len(sightings))

        # ── Optional alibi input ──────────────────────────────────────────
        st.markdown("#### 📋 Optional: Enter Stated Alibi")
        st.caption(
            "If the suspect has given an alibi, enter it here. "
            "AI will flag any conflicts with the camera timeline."
        )
        alibi_input = st.text_area(
            "Stated Alibi *(leave blank if none)*",
            placeholder=(
                "e.g.  Suspect claims they were at home between 08:00 and 10:00, "
                "then drove to their office on Anna Salai, arriving at 10:30."
            ),
            height=80,
        )

        st.markdown("---")

        if st.button(
            "🤖 Generate Movement Intelligence Brief",
            type="primary",
            use_container_width=True,
        ):
            # ── Build the sightings summary for the AI ────────────────────
            sighting_lines = []
            for i, s in enumerate(sightings, 1):
                line = (
                    f"Sighting #{i}\n"
                    f"  Camera   : {s.get('camera_id') or 'Unknown'}\n"
                    f"  Time     : {s.get('timestamp', 'Unknown')}\n"
                    f"  Location : {s.get('location', 'Unknown')}\n"
                    f"  Confidence: {s.get('confidence', 'Unknown')}\n"
                    f"  Observed : {s.get('description', '')}\n"
                    f"  GPS      : {s.get('latitude','—')}, {s.get('longitude','—')}\n"
                    f"  Notes    : {s.get('notes','')}"
                )
                sighting_lines.append(line)

            sightings_block = "\n\n".join(sighting_lines)

            alibi_block = (
                f"\nSTATED ALIBI:\n{alibi_input.strip()}"
                if alibi_input.strip()
                else "\nSTATED ALIBI: None provided."
            )

            intel_system = (
                "You are a senior forensic intelligence analyst with 20 years of "
                "experience reviewing CCTV movement data for criminal investigations.\n\n"
                "You will be given a list of camera sightings for a single target person "
                "across multiple locations and times, and optionally a stated alibi.\n\n"
                "Produce a structured MOVEMENT INTELLIGENCE BRIEF using EXACTLY "
                "these sections:\n\n"

                "## CHRONOLOGICAL MOVEMENT TIMELINE\n"
                "List every confirmed sighting in time order. Format each as:\n"
                "[TIME] — [LOCATION] — Confidence: [level]\n"
                "Brief note of what was observed.\n\n"

                "## UNACCOUNTED GAPS\n"
                "Identify every gap between consecutive sightings where "
                "the subject's location is unknown. For each gap state:\n"
                "- Start time and end time of the gap\n"
                "- Duration in minutes\n"
                "- Last known location before gap\n"
                "- First known location after gap\n"
                "- Whether this gap duration is suspicious (e.g. enough time "
                "  to reach the crime scene and return, or implausibly fast travel)\n\n"

                "## SUSPICIOUS PATTERNS\n"
                "Flag any of the following if present:\n"
                "- Subject returns to same location more than once (possible surveillance)\n"
                "- Subject avoids cameras (gaps in known camera-rich areas)\n"
                "- Unusually fast movement between distant locations (possible vehicle use)\n"
                "- Behaviour changes between sightings (calm → rushed → calm)\n"
                "- Any other pattern an experienced investigator would flag\n"
                "If no suspicious patterns, write: None identified.\n\n"

                "## ALIBI ASSESSMENT\n"
                "If an alibi was provided: Cross-reference each alibi claim "
                "against the camera timeline. State clearly:\n"
                "- SUPPORTED: [alibi element] — matches camera evidence\n"
                "- CONTRADICTED: [alibi element] — conflicts with camera evidence\n"
                "- UNVERIFIED: [alibi element] — no camera evidence either way\n"
                "If no alibi was provided: Write 'No alibi provided — recommend interview.'\n\n"

                "## MOVEMENT ROUTE ASSESSMENT\n"
                "Describe the apparent route the subject took based on all sightings. "
                "Identify if this route is consistent with:\n"
                "a) A planned, deliberate movement\n"
                "b) Random or opportunistic movement\n"
                "c) An escape or evasion route\n\n"

                "## RECOMMENDED NEXT CAMERAS\n"
                "Based on the gaps and route, list specific locations or camera types "
                "investigators should check next. Explain why each is recommended.\n\n"

                "## INTELLIGENCE SUMMARY\n"
                "Write 3-5 sentences summarising the overall picture. "
                "State the strongest conclusion the camera evidence supports, "
                "and the single most important gap to fill.\n\n"

                "Be precise and analytical. Use the evidence only. "
                "Do not speculate beyond what the data supports."
            )

            intel_user = (
                f"CCTV SIGHTING DATA ({len(sightings)} sightings):\n\n"
                f"{sightings_block}"
                f"{alibi_block}"
            )

            with st.spinner(
                "AI is analysing all sightings and writing the intelligence brief… "
                "This may take 20-40 seconds."
            ):
                brief = ai_call(intel_system, intel_user, max_tokens=2000)

            st.session_state["movement_brief"] = brief
            st.session_state["movement_brief_case"] = selected_case_id

        # ── Display the brief ─────────────────────────────────────────────
        if st.session_state.get("movement_brief") and \
           st.session_state.get("movement_brief_case") == selected_case_id:

            st.divider()
            st.markdown("## 📄 Movement Intelligence Brief")

            brief_text = st.session_state["movement_brief"]
            st.markdown(brief_text)

            st.divider()

            # Download as text
            st.download_button(
                "⬇️ Download Brief as .txt",
                data=brief_text.encode(),
                file_name=f"movement_brief_{selected_case_id}.txt",
                mime="text/plain",
                use_container_width=True,
            )

            st.caption(
                "⚠️ This brief is AI-generated for investigative guidance only. "
                "All findings must be verified against original footage and reviewed "
                "by a qualified investigator before use in legal proceedings."
            )


# ─────────────────────────────────────────────────────────────────────────────
# TAB 4 — MAP & TIMELINE
# ─────────────────────────────────────────────────────────────────────────────

with tab_map:
    st.subheader("🗺️ Movement Map & Timeline")

    sightings = get_cctv_by_case(selected_case_id)

    if not sightings:
        st.info(
            "No sightings logged yet. Use the **Log Sightings** tab first."
        )
    else:
        total = len(sightings)
        high  = sum(1 for s in sightings if "High"   in s.get("confidence", ""))
        med   = sum(1 for s in sightings if "Medium" in s.get("confidence", ""))
        low_  = sum(1 for s in sightings if "Low"    in s.get("confidence", ""))

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Sightings",    total)
        m2.metric("🟢 High Confidence", high)
        m3.metric("🟡 Medium",          med)
        m4.metric("🔴 Low",             low_)

        st.divider()

        # ── Timeline table ────────────────────────────────────────────────
        st.markdown("### 🕐 Sighting Timeline")
        table_rows = []
        for s in sightings:
            desc = s.get("description", "")
            table_rows.append({
                "#":           s.get("id", ""),
                "Camera":      s.get("camera_id") or "—",
                "Time":        s.get("timestamp", ""),
                "Location":    s.get("location", ""),
                "Confidence":  conf_emoji(s.get("confidence", "")),
                "Observation": (desc[:90] + "…") if len(desc) > 90 else desc,
            })
        st.dataframe(
            pd.DataFrame(table_rows),
            use_container_width=True,
            hide_index=True,
        )

        # ── Full detail expander ──────────────────────────────────────────
        with st.expander("🔍 View Full Details for Every Sighting"):
            for idx, s in enumerate(sightings, 1):
                st.markdown(
                    f"**#{idx} — {s.get('camera_id') or 'Unknown Camera'}  |  "
                    f"{s.get('location', '')}  |  {s.get('timestamp', '')}**"
                )
                st.markdown(
                    f"Confidence: {conf_emoji(s.get('confidence', ''))}  "
                    f"| GPS: {s.get('latitude', '—')}, {s.get('longitude', '—')}"
                )
                st.write(s.get("description", ""))
                if s.get("notes"):
                    st.caption(f"📌 Notes: {s['notes']}")
                st.markdown("---")

        # ── Movement map ──────────────────────────────────────────────────
        st.markdown("### 📍 Movement Map")

        map_pts = [
            s for s in sightings
            if s.get("latitude") and s.get("longitude")
            and float(s["latitude"]) != 0.0
            and float(s["longitude"]) != 0.0
        ]

        if not map_pts:
            st.info(
                "No GPS coordinates in your sightings yet. "
                "Add latitude and longitude when logging entries to see the map."
            )
        else:
            avg_lat = sum(float(s["latitude"])  for s in map_pts) / len(map_pts)
            avg_lng = sum(float(s["longitude"]) for s in map_pts) / len(map_pts)

            fmap = folium.Map(location=[avg_lat, avg_lng], zoom_start=16, tiles="OpenStreetMap")

            # Movement path (drawn first so markers sit on top)
            if len(map_pts) > 1:
                path = [[float(s["latitude"]), float(s["longitude"])] for s in map_pts]
                folium.PolyLine(
                    path,
                    color="purple",
                    weight=3,
                    opacity=0.7,
                    tooltip="Movement Path (chronological)",
                    dash_array="6",
                ).add_to(fmap)

            for seq, s in enumerate(map_pts, 1):
                colour = conf_map_colour(s.get("confidence", ""))
                popup_html = f"""
<div style="font-family:Arial,sans-serif;min-width:220px;font-size:13px">
  <b>#{seq} &mdash; {s.get('camera_id') or 'Camera unknown'}</b><br>
  <b>📍</b> {s.get('location','')}<br>
  <b>🕐</b> {s.get('timestamp','')}<br>
  <b>🎯</b> {s.get('confidence','')}<br>
  <hr style="margin:6px 0">
  {s.get('description','')[:250]}{'…' if len(s.get('description',''))>250 else ''}
  {'<br><br><i>' + s['notes'] + '</i>' if s.get('notes') else ''}
</div>
"""
                folium.Marker(
                    location=[float(s["latitude"]), float(s["longitude"])],
                    popup=folium.Popup(popup_html, max_width=290),
                    tooltip=f"#{seq}  {s.get('location','')} — {s.get('timestamp','')}",
                    icon=folium.Icon(color=colour, icon="camera", prefix="fa"),
                ).add_to(fmap)

            st_folium(fmap, height=520, width=None)
            st.caption(
                "🟢 High confidence  ·  🟡 Medium  ·  🔴 Low  "
                "·  ╌╌ Purple dashed line = movement path in time order  "
                "·  Click a pin for full sighting details"
            )

        st.divider()

        # ── Export ────────────────────────────────────────────────────────
        st.markdown("### 📤 Export")
        export_df = pd.DataFrame([dict(s) for s in sightings])
        st.download_button(
            "⬇️ Export all sightings as CSV",
            data=export_df.to_csv(index=False).encode(),
            file_name=f"cctv_sightings_{selected_case_id}.csv",
            mime="text/csv",
            use_container_width=True,
        )