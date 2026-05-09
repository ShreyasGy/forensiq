# pages/demo_mode.py
# ForensiQ — Session 10: Demo Mode
# Loads realistic fake data so judges can explore without typing anything

import os
import datetime
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from theme import apply_theme
from database import (
    get_all_cases,
    insert_case,
    insert_autopsy_report,
    insert_witness_statement,
    insert_tod_estimate,
    insert_suspect,
    insert_cctv_sighting,
    insert_risk_score,
    _normalize_case,
    generate_case_id,
)

st.set_page_config(
    page_title="ForensiQ — Demo Mode",
    page_icon="🎬",
    layout="wide",
)
apply_theme()

# ══════════════════════════════════════════════════════════════════════════════
# DEMO DATA DEFINITIONS
# ══════════════════════════════════════════════════════════════════════════════

DEMO_CASES = [
    {
        "case_number": "FQ-2024-001",
        "title": "Riverside Warehouse Homicide",
        "status": "Open",
        "case_type": "Homicide",
        "victim_name": "Marcus J. Delano",
        "victim_age": 34,
        "assigned_investigator": "Det. Sarah Okonkwo",
        "location": "Warehouse District, Pier 7",
        "description": (
            "Victim found at 03:42 by a security guard. "
            "Single blunt-force trauma to the posterior cranium. "
            "Scene shows signs of a struggle. No wallet or phone recovered."
        ),
    },
    {
        "case_number": "FQ-2024-002",
        "title": "Hillcrest Avenue Suspicious Death",
        "status": "Under Review",
        "case_type": "Suspicious Death",
        "victim_name": "Priya Nanthakumar",
        "victim_age": 28,
        "assigned_investigator": "Det. James Reilly",
        "location": "14 Hillcrest Avenue, Apt 3B",
        "description": (
            "Victim found unresponsive by flatmate at 08:15. "
            "Toxicology screen positive for GHB. Manner of death undetermined. "
            "No forced entry. Door locked from inside."
        ),
    },
    {
        "case_number": "FQ-2024-003",
        "title": "Central Park Running Track Assault",
        "status": "Open",
        "case_type": "Aggravated Assault",
        "victim_name": "Thomas Eriksen",
        "victim_age": 41,
        "assigned_investigator": "Det. Sarah Okonkwo",
        "location": "Central Park, East Running Track",
        "description": (
            "Victim found unconscious by early-morning jogger at 05:50. "
            "Multiple lacerations to the face and torso. "
            "CCTV coverage limited due to maintenance shutdown."
        ),
    },
]

DEMO_AUTOPSIES = [
    {
        "case_number": "FQ-2024-001",
        "cause_of_death": "Blunt force trauma to the head — single blow, posterior cranium",
        "manner_of_death": "Homicide",
        "injuries": (
            "Depressed skull fracture (6 cm), subdural haematoma, "
            "bilateral periorbital ecchymosis, defensive wounds on both forearms"
        ),
        "toxicology": "Blood alcohol 0.02%. No controlled substances detected.",
        "soap_subjective": (
            "Security guard reported hearing a single loud impact sound at approximately 03:35, "
            "followed by silence. Discovered victim face-down 7 minutes later."
        ),
        "soap_objective": (
            "Core body temperature 31.2°C at scene (ambient 14°C). "
            "Full rigor mortis present. Lividity fixed, posterior distribution. "
            "Wound consistent with cylindrical object, diameter approx 4–5 cm."
        ),
        "soap_assessment": (
            "Death occurred 8–12 hours prior to discovery. "
            "Single decisive blow suggests premeditated intent. "
            "Wound geometry inconsistent with a fall."
        ),
        "soap_plan": (
            "1. Recover weapon — search for iron pipe or similar object. "
            "2. DNA swab beneath fingernails (defensive contact). "
            "3. Full financial audit of victim."
        ),
        "key_terms": "subdural haematoma, depressed fracture, lividity, rigor mortis, blunt instrument",
        "findings": "No evidence of sexual assault. Victim's watch missing (tan line present).",
    },
    {
        "case_number": "FQ-2024-002",
        "cause_of_death": "Acute GHB intoxication — respiratory depression",
        "manner_of_death": "Undetermined (pending investigation)",
        "injuries": "Petechial haemorrhaging, mild perioral cyanosis, no external trauma",
        "toxicology": "GHB 285 mg/L (lethal threshold ~200 mg/L). Ethanol 0.04%.",
        "soap_subjective": (
            "Flatmate states victim appeared normal at 22:30. "
            "Did not hear victim return after that. Found her at 08:15."
        ),
        "soap_objective": (
            "Body temperature 28.7°C. Full rigor. Fixed lividity (anterior). "
            "Empty wine glass on bedside table — trace GHB confirmed. "
            "No signs of restraint."
        ),
        "soap_assessment": (
            "GHB concentration significantly exceeds recreational threshold. "
            "Self-administration cannot be ruled out, but elevated concentration "
            "and locked-room circumstances raise suspicion of third-party involvement."
        ),
        "soap_plan": (
            "1. Source analysis of GHB — pharmaceutical vs. illicit synthesis. "
            "2. Interview victim's social contacts from prior 48 hours. "
            "3. Obtain phone records and social media."
        ),
        "key_terms": "GHB, respiratory depression, petechiae, cyanosis, toxicology",
        "findings": "Laptop open on desk, browser history shows research into drug interactions.",
    },
]

DEMO_WITNESSES = [
    {
        "case_number": "FQ-2024-001",
        "witness_name": "Raymond Osei",
        "statement": (
            "I was doing my rounds at about 3:40 in the morning. I heard a bang from behind "
            "the loading bay — like something hitting a metal container. I waited maybe two "
            "minutes, then went to check. I saw the man on the ground. I didn't see anyone "
            "running away. I called 999 immediately. I didn't touch anything."
        ),
        "reliability_score": "High",
        "contradictions": "Initially stated he heard the sound at 3:30, corrected to 3:40 under re-interview.",
    },
    {
        "case_number": "FQ-2024-001",
        "witness_name": "Diane Marsh",
        "statement": (
            "I was parked near the pier gate around half past three. I saw a dark-coloured van "
            "leave in a hurry — no headlights on. Couldn't make out the plate. Driver was "
            "wearing a dark hoodie. Didn't think anything of it until I heard the sirens."
        ),
        "reliability_score": "Medium",
        "contradictions": "Cannot confirm exact time. No corroborating CCTV of van at that gate.",
    },
    {
        "case_number": "FQ-2024-002",
        "witness_name": "Aisha Bello (flatmate)",
        "statement": (
            "Priya seemed totally fine when I saw her at half ten. She'd had a glass of wine. "
            "She said she was going to bed. The door to her room was closed all night. "
            "I found her when I knocked to ask about breakfast. She wasn't breathing."
        ),
        "reliability_score": "High",
        "contradictions": "None identified. Consistent across two interviews.",
    },
    {
        "case_number": "FQ-2024-002",
        "witness_name": "Dev Kapoor (ex-partner)",
        "statement": (
            "I haven't spoken to Priya in three months. I was at my cousin's house that night. "
            "You can check — there were six of us there. I had nothing to do with this."
        ),
        "reliability_score": "Low",
        "contradictions": (
            "Phone records show two calls to victim's number at 21:47 and 22:03 that night. "
            "Alibi not yet corroborated — cousin interview pending."
        ),
    },
]

DEMO_SUSPECTS = [
    {
        "case_number": "FQ-2024-001",
        "suspect_name": "Viktor Lenko",
        "priority_rank": 1,
        "motive": (
            "Victim owed Lenko £18,000 in outstanding debt. "
            "Text messages show Lenko threatened victim two days prior."
        ),
        "alibi": "Claims he was at a casino — CCTV review pending.",
        "notes": "Prior conviction for GBH (2019). Known associate of organised crime.",
    },
    {
        "case_number": "FQ-2024-001",
        "suspect_name": "Unknown Male (CCTV — Suspect Alpha)",
        "priority_rank": 2,
        "motive": "Unknown",
        "alibi": "Unidentified",
        "notes": (
            "5'10\", medium build, dark hoodie, gloves. "
            "Seen on Pier 6 CCTV at 03:28, moving toward Pier 7."
        ),
    },
    {
        "case_number": "FQ-2024-002",
        "suspect_name": "Dev Kapoor",
        "priority_rank": 1,
        "motive": "Recent acrimonious breakup. Victim had filed a restraining order application.",
        "alibi": "Alibi partially unverified — cousin interview pending.",
        "notes": "Phone records contradict initial statement. Access to victim's building code.",
    },
]

DEMO_TOD = [
    {
        "case_number": "FQ-2024-001",
        "estimated_tod": "2024-03-14 19:00–21:00",
        "time_window_start": "2024-03-14 19:00",
        "time_window_end": "2024-03-14 21:00",
        "confidence_score": 78,
        "method_used": "Henssge Nomogram + Rigor Mortis Staging",
        "notes": (
            "Body temp drop and full rigor consistent with 8–12 hour PMI. "
            "Ambient temperature 14°C narrows window to 19:00–21:00. "
            "Contradicts security guard timeline — victim may have been moved post-mortem."
        ),
    },
    {
        "case_number": "FQ-2024-002",
        "estimated_tod": "2024-03-21 23:00–01:00",
        "time_window_start": "2024-03-21 23:00",
        "time_window_end": "2024-03-22 01:00",
        "confidence_score": 65,
        "method_used": "Body Temperature + Livor Mortis",
        "notes": (
            "GHB half-life ~4–5 hours; blood level back-calculated to ingestion at ~22:30–23:00. "
            "Consistent with flatmate's last contact. Confidence limited by unknown GHB purity."
        ),
    },
]

DEMO_CCTV = [
    # Case 001
    {
        "case_number": "FQ-2024-001",
        "timestamp": "2024-03-14 19:12:00",
        "location": "Pier 5 Gate — East Camera",
        "description": "Male in dark hoodie and gloves enters via Pier 5 pedestrian gate. Avoids direct camera angle.",
        "latitude": 51.5074,
        "longitude": -0.1278,
        "confidence": "High",
        "notes": "Suspect Alpha — possible pre-survey of area",
        "camera_id": "CAM-P5-E01",
    },
    {
        "case_number": "FQ-2024-001",
        "timestamp": "2024-03-14 19:28:00",
        "location": "Pier 6 Loading Bay — South Camera",
        "description": "Same male observed loitering near loading bay. Checks watch twice. Partially obscures face.",
        "latitude": 51.5076,
        "longitude": -0.1282,
        "confidence": "High",
        "notes": "Suspect Alpha — timing surveillance",
        "camera_id": "CAM-P6-S02",
    },
    {
        "case_number": "FQ-2024-001",
        "timestamp": "2024-03-14 19:41:00",
        "location": "Pier 7 Access Road — North Camera",
        "description": "Suspect Alpha approaches Pier 7. Victim (Marcus Delano) visible entering from opposite direction.",
        "latitude": 51.5079,
        "longitude": -0.1290,
        "confidence": "High",
        "notes": "Last confirmed sighting before TOD window",
        "camera_id": "CAM-P7-N01",
    },
    {
        "case_number": "FQ-2024-001",
        "timestamp": "2024-03-14 21:03:00",
        "location": "Pier 5 Gate — West Exit",
        "description": "Dark-coloured van exits through Pier 5 west gate without headlights. Single occupant.",
        "latitude": 51.5073,
        "longitude": -0.1275,
        "confidence": "Medium",
        "notes": "Consistent with witness Diane Marsh statement",
        "camera_id": "CAM-P5-W01",
    },
    # Case 002
    {
        "case_number": "FQ-2024-002",
        "timestamp": "2024-03-21 21:55:00",
        "location": "Hillcrest Avenue — Street Camera 3",
        "description": "Male matching Dev Kapoor's description approaches building entrance. Does not ring buzzer.",
        "latitude": 51.5110,
        "longitude": -0.1350,
        "confidence": "Medium",
        "notes": "Unconfirmed ID — height and build match",
        "camera_id": "CAM-HC-ST03",
    },
    {
        "case_number": "FQ-2024-002",
        "timestamp": "2024-03-21 22:08:00",
        "location": "Hillcrest Avenue — Building Entrance Cam",
        "description": "Individual enters building using keypad code. Face partially obscured by collar.",
        "latitude": 51.5111,
        "longitude": -0.1352,
        "confidence": "Low",
        "notes": "Only residents and ex-residents know the door code",
        "camera_id": "CAM-HC-ENTRY",
    },
    {
        "case_number": "FQ-2024-002",
        "timestamp": "2024-03-21 22:41:00",
        "location": "Hillcrest Avenue — Street Camera 3",
        "description": "Same individual exits building, walks quickly north, hails a cab.",
        "latitude": 51.5110,
        "longitude": -0.1350,
        "confidence": "Medium",
        "notes": "Cab operator records requested",
        "camera_id": "CAM-HC-ST03",
    },
]

DEMO_RISK = [
    {
        "case_number": "FQ-2024-001",
        "risk_score": 82,
        "risk_category": "Critical",
        "notes": """{
  "confidence": 85,
  "rationale": "Strong physical evidence, identified suspect with motive and prior violence, CCTV places Suspect Alpha at scene during TOD window. Victim's phone and watch missing suggest deliberate evidence removal.",
  "red_flags": [
    {"flag": "Victim moved post-mortem", "implication": "Organised offender — crime scene is secondary location"},
    {"flag": "Suspect has prior GBH conviction", "implication": "Established propensity for violence"},
    {"flag": "Confirmed financial motive — £18,000 debt", "implication": "Clear precipitating cause"},
    {"flag": "Suspect avoided all direct CCTV angles", "implication": "Pre-operational surveillance of camera positions"},
    {"flag": "Victim's watch and phone missing", "implication": "Deliberate removal of communication and GPS evidence"}
  ],
  "evidence_gaps": [
    "Casino CCTV for Viktor Lenko alibi not yet reviewed",
    "Weapon not recovered — no forensic match possible",
    "DNA from fingernail scrapings not yet processed",
    "Van registration not identified",
    "Financial records not yet subpoenaed"
  ],
  "recommended_actions": [
    "1. Obtain casino CCTV immediately — alibi window is 19:00–21:00",
    "2. Fast-track DNA from fingernail scrapings",
    "3. Issue ANPR request for dark van, Pier 5 west gate, 21:03",
    "4. Subpoena Lenko's financial records",
    "5. Execute search warrant on Lenko's premises for blunt instrument"
  ],
  "evidence_quality": {"physical": 72, "witness": 60, "digital": 68}
}""",
    },
    {
        "case_number": "FQ-2024-002",
        "risk_score": 64,
        "risk_category": "High",
        "notes": """{
  "confidence": 70,
  "rationale": "Suspicious locked-room death with GHB above lethal threshold. Key witness (ex-partner) provided false statement — phone records contradict alibi. CCTV places unconfirmed individual at scene. Evidence gaps prevent Critical rating.",
  "red_flags": [
    {"flag": "Suspect lied about contact with victim", "implication": "Consciousness of guilt — false alibi is significant red flag"},
    {"flag": "GHB 43% above lethal threshold", "implication": "Concentration inconsistent with recreational self-administration"},
    {"flag": "Suspect knew building entry code", "implication": "Had physical means of access"},
    {"flag": "Victim researching drug interactions", "implication": "May indicate awareness of being targeted, or self-administration context"},
    {"flag": "CCTV individual entered 13 minutes after phone call", "implication": "Timeline suggests coordinated visit"}
  ],
  "evidence_gaps": [
    "Dev Kapoor alibi not corroborated — cousin interview outstanding",
    "Cab company records not yet obtained",
    "GHB source analysis (pharmaceutical vs illicit) pending",
    "Building entry log not yet pulled from management",
    "Victim's phone forensic download not completed"
  ],
  "recommended_actions": [
    "1. Interview cousin immediately — do not give Kapoor time to coordinate",
    "2. Pull building entry log from property management",
    "3. Obtain cab company records — identify driver and destination",
    "4. Fast-track GHB source analysis",
    "5. Complete phone forensic download — check all app data"
  ],
  "evidence_quality": {"physical": 55, "witness": 65, "digital": 45}
}""",
    },
]


# ══════════════════════════════════════════════════════════════════════════════
# LOADER
# ══════════════════════════════════════════════════════════════════════════════

def get_existing_case_numbers():
    try:
        all_cases = get_all_cases()
        if not all_cases:
            return set()
        return {_normalize_case(c).get("case_number", "") for c in all_cases}
    except Exception:
        return set()


def build_case_id_map():
    """Returns {case_number: case_id} for all cases in DB."""
    try:
        all_cases = get_all_cases() or []
        result = {}
        for c in all_cases:
            nc = _normalize_case(c)
            result[nc.get("case_number", "")] = (
                nc.get("case_id") or nc.get("id") or nc.get("case_number", "")
            )
        return result
    except Exception:
        return {}


def load_demo_data():
    existing = get_existing_case_numbers()
    inserted_cases = []
    skipped_cases = []

    progress = st.progress(0, text="Starting demo load…")

    # ── Cases ──────────────────────────────────────────────────────────────────
    for i, case in enumerate(DEMO_CASES):
        if case["case_number"] in existing:
            skipped_cases.append(case["case_number"])
            continue
        try:
            insert_case({
                "case_number": case["case_number"],
                "title": case["title"],
                "status": case["status"],
                "case_type": case.get("case_type", ""),
                "victim_name": case.get("victim_name", ""),
                "victim_age": case.get("victim_age", ""),
                "assigned_investigator": case.get("assigned_investigator", ""),
                "location": case.get("location", ""),
                "description": case.get("description", ""),
            })
            inserted_cases.append(case["case_number"])
        except Exception as e:
            st.warning(f"Case insert issue ({case['case_number']}): {e}")

    progress.progress(20, text="Cases loaded…")

    # Rebuild ID map after inserting cases
    id_map = build_case_id_map()

    # ── Autopsies ──────────────────────────────────────────────────────────────
    for item in DEMO_AUTOPSIES:
        case_id = id_map.get(item["case_number"])
        if not case_id:
            continue
        try:
            insert_autopsy_report(
                case_id=case_id,
                cause_of_death=item.get("cause_of_death", ""),
                manner_of_death=item.get("manner_of_death", ""),
                injuries=item.get("injuries", ""),
                toxicology=item.get("toxicology", ""),
                soap_subjective=item.get("soap_subjective", ""),
                soap_objective=item.get("soap_objective", ""),
                soap_assessment=item.get("soap_assessment", ""),
                soap_plan=item.get("soap_plan", ""),
                key_terms=item.get("key_terms", ""),
                findings=item.get("findings", ""),
            )
        except Exception as e:
            st.warning(f"Autopsy insert issue: {e}")

    progress.progress(40, text="Autopsy reports loaded…")

    # ── Witnesses ──────────────────────────────────────────────────────────────
    for item in DEMO_WITNESSES:
        case_id = id_map.get(item["case_number"])
        if not case_id:
            continue
        try:
            insert_witness_statement(
                case_id=case_id,
                witness_name=item.get("witness_name", ""),
                statement=item.get("statement", ""),
                reliability_score=item.get("reliability_score", ""),
                contradictions=item.get("contradictions", ""),
            )
        except Exception as e:
            st.warning(f"Witness insert issue: {e}")

    progress.progress(55, text="Witness statements loaded…")

    # ── TOD ────────────────────────────────────────────────────────────────────
    for item in DEMO_TOD:
        case_id = id_map.get(item["case_number"])
        if not case_id:
            continue
        try:
            insert_tod_estimate(
                case_id=case_id,
                estimated_tod=item.get("estimated_tod", ""),
                time_window_start=item.get("time_window_start", ""),
                time_window_end=item.get("time_window_end", ""),
                confidence_score=item.get("confidence_score", 0),
                method_used=item.get("method_used", ""),
                notes=item.get("notes", ""),
            )
        except Exception as e:
            st.warning(f"TOD insert issue: {e}")

    progress.progress(65, text="TOD estimates loaded…")

    # ── Suspects ───────────────────────────────────────────────────────────────
    for item in DEMO_SUSPECTS:
        case_id = id_map.get(item["case_number"])
        if not case_id:
            continue
        try:
            insert_suspect(
                case_id=case_id,
                suspect_name=item.get("suspect_name", ""),
                priority_rank=item.get("priority_rank", 0),
                motive=item.get("motive", ""),
                alibi=item.get("alibi", ""),
                notes=item.get("notes", ""),
            )
        except Exception as e:
            st.warning(f"Suspect insert issue: {e}")

    progress.progress(75, text="Suspects loaded…")

    # ── CCTV ───────────────────────────────────────────────────────────────────
    for item in DEMO_CCTV:
        case_id = id_map.get(item["case_number"])
        if not case_id:
            continue
        try:
            insert_cctv_sighting(
                case_id=case_id,
                timestamp=item.get("timestamp", ""),
                location=item.get("location", ""),
                description=item.get("description", ""),
                latitude=item.get("latitude", 0.0),
                longitude=item.get("longitude", 0.0),
                confidence=item.get("confidence", ""),
                notes=item.get("notes", ""),
                camera_id=item.get("camera_id", ""),
            )
        except Exception as e:
            st.warning(f"CCTV insert issue: {e}")

    progress.progress(88, text="CCTV sightings loaded…")

    # ── Risk Scores ────────────────────────────────────────────────────────────
    for item in DEMO_RISK:
        case_id = id_map.get(item["case_number"])
        if not case_id:
            continue
        try:
            insert_risk_score(
                case_id=case_id,
                risk_score=item.get("risk_score", 0),
                risk_category=item.get("risk_category", ""),
                notes=item.get("notes", ""),
            )
        except Exception as e:
            st.warning(f"Risk insert issue: {e}")

    progress.progress(100, text="Demo data fully loaded ✅")

    return inserted_cases, skipped_cases


# ══════════════════════════════════════════════════════════════════════════════
# UI
# ══════════════════════════════════════════════════════════════════════════════

st.title("🎬 ForensiQ Demo Mode")
st.caption("Load realistic fake case data so judges can explore every module instantly")

st.divider()

st.markdown("""
### What this loads

| Module | Demo Data |
|---|---|
| Case Manager | 3 cases — Homicide, Suspicious Death, Assault |
| Report Analyzer | 2 full SOAP autopsy reports |
| Witness Statements | 4 witness statements with reliability scores |
| TOD Estimator | 2 TOD estimates with Henssge method |
| Suspects | 3 suspects with motives, alibis, priority ranks |
| CCTV Tracker | 7 sightings across 2 cases with GPS coordinates |
| Risk Scorer | 2 full AI risk assessments (Critical + High) |
| Dashboard | All charts and PDF export populated |

All data is **fictional** and created for demonstration purposes only.
If demo cases already exist, they are **skipped** (not duplicated).
""")

st.divider()

col_btn, col_warn = st.columns([2, 3])
with col_btn:
    load_btn = st.button(
        "🚀 Load Demo Data",
        type="primary",
        use_container_width=True,
    )

with col_warn:
    st.info(
        "Safe to run multiple times — existing demo cases are detected and skipped automatically."
    )

if load_btn:
    with st.spinner("Loading demo data into ForensiQ database…"):
        try:
            inserted, skipped = load_demo_data()
        except Exception as e:
            st.error(f"Demo load failed: {e}")
            st.exception(e)
            st.stop()

    st.success("✅ Demo data loaded successfully!")

    if inserted:
        st.markdown(f"**Cases inserted:** {', '.join(inserted)}")
    if skipped:
        st.markdown(f"**Cases already existed (skipped):** {', '.join(skipped)}")

    st.markdown("---")
    st.markdown("### ▶ Where to go next")
    st.markdown("""
1. **Case Manager** — view FQ-2024-001 (Riverside Warehouse Homicide) in full detail
2. **Risk Scorer** — select FQ-2024-001 and view the Critical risk assessment
3. **CCTV Tracker** — view the 4 sightings plotted on the live Folium map
4. **Dashboard** — all charts now populated; generate a PDF report
5. **Report Analyzer** — review the full SOAP autopsy for FQ-2024-002
""")

st.divider()
st.warning(
    "⚠️ **Disclaimer:** All names, cases, and events in Demo Mode are entirely fictional "
    "and created solely for demonstration purposes. Any resemblance to real persons or "
    "events is coincidental. ForensiQ is an AI-assisted investigative support tool and "
    "must not be used as the sole basis for legal decisions."
)