import streamlit as st
import os
import math
import json
import plotly.graph_objects as go
from datetime import datetime, timedelta
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="ForensiQ — TOD Estimator",
    page_icon="⏱️",
    layout="wide"
)

from theme import apply_theme
apply_theme(active_page="TOD Estimator")

# ─────────────────────────────────────────────
#  Featherless AI client
# ─────────────────────────────────────────────
client = OpenAI(
    api_key=os.getenv("FEATHERLESS_AI_KEY") or os.getenv("FEATHERLESS_API_KEY"),
    base_url="https://api.featherless.ai/v1"
)

# ─────────────────────────────────────────────
#  Database import (safe — only adds, never removes)
# ─────────────────────────────────────────────
try:
    from database import insert_tod_estimate, get_all_cases
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False

# ─────────────────────────────────────────────
#  Henssge nomogram approximation
#  Formula: t = (T_rect - T_amb) / (T_normal - T_amb) corrected
#  We use the simplified double-exponential model
# ─────────────────────────────────────────────
def henssge_estimate(body_temp_c: float, ambient_temp_c: float, body_weight_kg: float = 70.0) -> dict:
    """
    Returns estimated PMI in hours using a simplified Henssge nomogram.
    Normal rectal temp assumed 37.2°C.
    Corrective factor Z depends on body weight.
    """
    T_normal = 37.2
    T_b = body_temp_c
    T_a = ambient_temp_c

    if T_b <= T_a:
        # Already at ambient — past exponential phase
        return {"hours": None, "note": "Body temperature has reached ambient — Henssge formula cannot give a precise estimate; PMI likely > 24 hrs."}

    if T_b >= T_normal:
        return {"hours": 0.0, "note": "Body temperature at or above normal — death very recent or temperature unreliable."}

    # Corrective factor Z (weight-based, from Henssge tables)
    if body_weight_kg <= 15:
        Z = 0.0
    elif body_weight_kg <= 30:
        Z = 0.25
    elif body_weight_kg <= 50:
        Z = 0.5
    elif body_weight_kg <= 70:
        Z = 0.75
    elif body_weight_kg <= 90:
        Z = 0.9
    elif body_weight_kg <= 110:
        Z = 1.0
    else:
        Z = 1.1

    cooling_constant = 1.11  # average for still air indoors
    ratio = (T_b - T_a) / (T_normal - T_a)

    try:
        # Simplified single-exponential: ratio = exp(-B * t)
        # => t = -ln(ratio) / B    where B ≈ 0.0284 (Henssge average)
        B = 0.0284 + (Z - 0.75) * 0.002
        hours = -math.log(ratio) / B
        hours = round(hours, 1)
    except (ValueError, ZeroDivisionError):
        return {"hours": None, "note": "Mathematical error — check temperature inputs."}

    return {"hours": hours, "note": f"Body cooled to {T_b}°C in ~{hours}h based on Henssge approximation."}


def rigor_to_hours(stage: str) -> tuple:
    """Returns (min_hours, max_hours) for rigor mortis stage."""
    mapping = {
        "None (0–2 hrs)":                (0,  2),
        "Beginning (2–6 hrs)":           (2,  6),
        "Full / Stiff (6–12 hrs)":       (6,  12),
        "Resolving / Loosening (12–24 hrs)": (12, 24),
        "Gone (24+ hrs)":                (24, 72),
    }
    return mapping.get(stage, (0, 72))


def livor_to_hours(stage: str) -> tuple:
    """Returns (min_hours, max_hours) for livor mortis stage."""
    mapping = {
        "Absent":                              (0,  2),
        "Present and Blanching (shifts when pressed)": (2, 8),
        "Fixed / Non-Blanching":               (8,  72),
    }
    return mapping.get(stage, (0, 72))


def decomp_to_hours(stage: str) -> tuple:
    mapping = {
        "None visible":            (0,  48),
        "Early bloating":          (48, 120),
        "Active decay / odor":     (72, 240),
        "Advanced decay":          (168, 720),
        "Skeletonization":         (720, 8760),
    }
    return mapping.get(stage, (0, 8760))


def combine_windows(*windows) -> tuple:
    """Combine multiple (min, max) hour windows by taking intersection if possible, else union."""
    valid = [(mn, mx) for mn, mx in windows if mn is not None and mx is not None]
    if not valid:
        return (0, 72)
    low = max(v[0] for v in valid)
    high = min(v[1] for v in valid)
    if low >= high:
        # No intersection — fall back to weighted average
        low = sum(v[0] for v in valid) / len(valid)
        high = sum(v[1] for v in valid) / len(valid)
        low, high = min(low, high - 1), max(low + 1, high)
    return (round(low, 1), round(high, 1))


def make_confidence_chart(score: int) -> go.Figure:
    color = "#22c55e" if score >= 70 else "#f59e0b" if score >= 45 else "#ef4444"
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        number={"suffix": "%", "font": {"size": 36, "color": "#e2e8f0"}},
        gauge={
            "axis": {"range": [0, 100], "tickcolor": "#94a3b8", "tickfont": {"color": "#94a3b8"}},
            "bar": {"color": color, "thickness": 0.25},
            "bgcolor": "#1e293b",
            "borderwidth": 0,
            "steps": [
                {"range": [0, 40],  "color": "#1e293b"},
                {"range": [40, 70], "color": "#1e293b"},
                {"range": [70, 100],"color": "#1e293b"},
            ],
            "threshold": {
                "line": {"color": color, "width": 4},
                "thickness": 0.75,
                "value": score
            }
        },
        domain={"x": [0, 1], "y": [0, 1]}
    ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"color": "#e2e8f0"},
        height=250,
        margin=dict(l=20, r=20, t=20, b=20)
    )
    return fig


# ─────────────────────────────────────────────
#  Page UI
# ─────────────────────────────────────────────
st.markdown("## ⏱️ Time-of-Death Estimator")
st.markdown("Enter the body condition data below. The AI will combine multiple forensic methods to calculate an estimated time of death.")
st.markdown("---")

col_left, col_right = st.columns([1, 1], gap="large")

with col_left:
    st.markdown("### 🌡️ Temperature Data")
    body_temp = st.number_input(
        "Body Temperature at Discovery (°C)",
        min_value=0.0, max_value=42.0, value=30.5, step=0.1,
        help="Rectal or core temperature measured at the scene."
    )
    ambient_temp = st.number_input(
        "Ambient / Room Temperature (°C)",
        min_value=-30.0, max_value=60.0, value=21.0, step=0.1,
        help="Temperature of the environment where the body was found."
    )
    body_weight = st.number_input(
        "Estimated Body Weight (kg) — for Henssge calculation",
        min_value=5.0, max_value=300.0, value=70.0, step=1.0,
        help="Used to correct the Henssge nomogram. Estimate if unknown."
    )

    st.markdown("### 💀 Rigor Mortis")
    rigor_stage = st.selectbox("Rigor Mortis Stage", [
        "None (0–2 hrs)",
        "Beginning (2–6 hrs)",
        "Full / Stiff (6–12 hrs)",
        "Resolving / Loosening (12–24 hrs)",
        "Gone (24+ hrs)"
    ])

    st.markdown("### 🔵 Livor Mortis (Lividity)")
    livor_stage = st.selectbox("Livor Mortis Stage", [
        "Absent",
        "Present and Blanching (shifts when pressed)",
        "Fixed / Non-Blanching"
    ])

    hypostasis_color = st.selectbox("Hypostasis Color", [
        "Pink / Red (fresh)",
        "Purple",
        "Cherry Red (possible CO poisoning)",
        "Dark / Black"
    ])

with col_right:
    st.markdown("### 🧫 Decomposition")
    decomp_stage = st.selectbox("Decomposition Stage", [
        "None visible",
        "Early bloating",
        "Active decay / odor",
        "Advanced decay",
        "Skeletonization"
    ])

    st.markdown("### 📍 Scene Conditions")
    body_location = st.selectbox("Body Location", [
        "Indoors — controlled temperature",
        "Indoors — uncontrolled temperature",
        "Outdoors — shaded",
        "Outdoors — direct sunlight",
        "Submerged in water",
        "Buried"
    ])

    clothing_coverage = st.selectbox("Clothing Coverage", [
        "None",
        "Light (t-shirt, shorts)",
        "Heavy (jacket, multiple layers)"
    ])

    st.markdown("### 📅 Discovery Date & Time")
    discovery_date = st.date_input("Discovery Date", value=datetime.today())
    discovery_time = st.time_input("Discovery Time", value=datetime.now().time())

    st.markdown("### 💾 Link to Case (Optional)")
    case_id = None
    case_label = "— No case selected —"
    if DB_AVAILABLE:
        try:
            cases = get_all_cases()
            case_options = ["— No case selected —"] + [f"[{c['id']}] {c['name']}" for c in cases]
            selected_case = st.selectbox("Save result to case", case_options)
            if selected_case != "— No case selected —":
                case_id = int(selected_case.split("]")[0].replace("[", "").strip())
                case_label = selected_case
        except Exception:
            st.info("Could not load cases — result won't be saved.")
    else:
        st.info("Database not connected — result won't be saved.")

st.markdown("---")

# ─────────────────────────────────────────────
#  Run estimation
# ─────────────────────────────────────────────
if st.button("⏱️ Estimate Time of Death", type="primary", use_container_width=True):

    discovery_datetime = datetime.combine(discovery_date, discovery_time)

    # Step 1: Local formula estimates
    henssge = henssge_estimate(body_temp, ambient_temp, body_weight)
    rigor_window   = rigor_to_hours(rigor_stage)
    livor_window   = livor_to_hours(livor_stage)
    decomp_window  = decomp_to_hours(decomp_stage)

    # Step 2: Combine windows
    windows_to_combine = [rigor_window, livor_window]
    if henssge["hours"] is not None:
        h = henssge["hours"]
        # ±30% uncertainty band around Henssge result
        windows_to_combine.append((max(0, h * 0.7), h * 1.3))

    # Only add decomp if it's informative (not "None visible" at short range)
    if decomp_stage != "None visible":
        windows_to_combine.append(decomp_window)

    combined_min, combined_max = combine_windows(*windows_to_combine)
    central_hours = (combined_min + combined_max) / 2

    # Step 3: Calculate actual date/time range
    tod_latest = discovery_datetime - timedelta(hours=combined_min)
    tod_earliest = discovery_datetime - timedelta(hours=combined_max)
    tod_central = discovery_datetime - timedelta(hours=central_hours)

    # Step 4: Build AI prompt
    system_prompt = """You are a board-certified forensic pathologist with 25 years of experience in time-of-death estimation. 
You combine the Henssge nomogram, rigor mortis staging, livor mortis fixation, hypostasis coloration, 
decomposition staging, and environmental factors to produce a scientifically rigorous TOD estimate.
You always respond in valid JSON only — no markdown, no preamble."""

    user_prompt = f"""A body was discovered on {discovery_date.strftime('%B %d, %Y')} at {discovery_time.strftime('%H:%M')}.

TEMPERATURE DATA:
- Body temperature at discovery: {body_temp}°C
- Ambient/room temperature: {ambient_temp}°C
- Estimated body weight: {body_weight} kg
- Henssge formula estimate: {f"{henssge['hours']} hours PMI" if henssge['hours'] is not None else henssge['note']}

FORENSIC OBSERVATIONS:
- Rigor mortis stage: {rigor_stage} → suggests {rigor_window[0]}–{rigor_window[1]} hours PMI
- Livor mortis stage: {livor_stage} → suggests {livor_window[0]}–{livor_window[1]} hours PMI
- Hypostasis color: {hypostasis_color}
- Decomposition stage: {decomp_stage} → suggests {decomp_window[0]}–{decomp_window[1]} hours PMI

SCENE CONDITIONS:
- Body location: {body_location}
- Clothing coverage: {clothing_coverage}

COMBINED MATHEMATICAL ESTIMATE:
- PMI window: {combined_min}–{combined_max} hours before discovery
- Which places estimated TOD between: {tod_earliest.strftime('%I:%M %p, %B %d %Y')} and {tod_latest.strftime('%I:%M %p, %B %d %Y')}

Please analyze all the above and respond with ONLY a JSON object in this exact structure:
{{
  "confidence_score": <integer 0-100>,
  "estimated_tod_range": "<human-readable date/time range e.g. Between 9:00 PM – 1:00 AM on 8 May 2025>",
  "central_estimate": "<single most likely date and time e.g. 11:00 PM on 8 May 2025>",
  "window_hours_plus_minus": <float>,
  "reasoning": "<plain English 3–5 sentence explanation of how each factor contributed to the estimate>",
  "factors_increased_accuracy": ["<factor 1>", "<factor 2>", "<factor 3>"],
  "factors_reduced_accuracy": ["<factor 1>", "<factor 2>"],
  "special_notes": "<any special concerns such as CO poisoning flag, outdoor heat acceleration, etc. or empty string>"
}}"""

    with st.spinner("🔬 Analysing forensic data and estimating time of death..."):
        try:
            response = client.chat.completions.create(
                model="meta-llama/Llama-3.3-70B-Instruct",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_prompt}
                ],
                temperature=0.2,
                max_tokens=1000
            )
            raw = response.choices[0].message.content.strip()

            # Clean JSON fences if model returns them
            raw = raw.replace("```json", "").replace("```", "").strip()
            result = json.loads(raw)

        except json.JSONDecodeError:
            st.error("⚠️ The AI returned a response that could not be parsed. Try again.")
            st.code(raw, language="text")
            st.stop()
        except Exception as e:
            st.error(f"⚠️ API error: {e}")
            st.stop()

    # ─────────────────────────────────────────────
    #  Display results
    # ─────────────────────────────────────────────
    st.markdown("---")
    st.markdown("## 📋 Time-of-Death Estimation Report")

    # Top result card
    res_col1, res_col2 = st.columns([2, 1], gap="large")

    with res_col1:
        st.markdown("### ⏱️ Estimated Time of Death")
        st.markdown(
            f"""
            <div style="
                background: linear-gradient(135deg, #1e3a5f 0%, #0f172a 100%);
                border: 1px solid #3b82f6;
                border-radius: 12px;
                padding: 24px;
                margin-bottom: 16px;
            ">
                <div style="font-size: 22px; font-weight: 700; color: #60a5fa; margin-bottom: 8px;">
                    📅 {result.get('estimated_tod_range', 'Unable to determine')}
                </div>
                <div style="font-size: 15px; color: #94a3b8;">
                    Central estimate: <span style="color:#e2e8f0; font-weight:600;">{result.get('central_estimate', '—')}</span>
                </div>
                <div style="font-size: 15px; color: #94a3b8; margin-top: 6px;">
                    Uncertainty window: <span style="color:#e2e8f0; font-weight:600;">± {result.get('window_hours_plus_minus', '—')} hours</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        st.markdown("### 🔎 Scientific Reasoning")
        st.info(result.get("reasoning", "No reasoning provided."))

        if result.get("special_notes"):
            st.warning(f"⚠️ **Special Note:** {result['special_notes']}")

    with res_col2:
        st.markdown("### 📊 Confidence Score")
        score = result.get("confidence_score", 50)
        fig = make_confidence_chart(score)
        st.plotly_chart(fig, use_container_width=True)

        confidence_label = "HIGH" if score >= 70 else "MODERATE" if score >= 45 else "LOW"
        confidence_color = "#22c55e" if score >= 70 else "#f59e0b" if score >= 45 else "#ef4444"
        st.markdown(
            f'<div style="text-align:center; font-size:18px; font-weight:700; color:{confidence_color};">'
            f'{confidence_label} CONFIDENCE</div>',
            unsafe_allow_html=True
        )

    # Factors
    factor_col1, factor_col2 = st.columns(2, gap="large")

    with factor_col1:
        st.markdown("### ✅ Factors That Increased Accuracy")
        factors_good = result.get("factors_increased_accuracy", [])
        if factors_good:
            for f in factors_good:
                st.markdown(
                    f'<div style="background:#052e16; border-left:4px solid #22c55e; '
                    f'border-radius:6px; padding:10px 14px; margin-bottom:8px; color:#d1fae5;">'
                    f'✅ {f}</div>',
                    unsafe_allow_html=True
                )
        else:
            st.markdown("_None identified._")

    with factor_col2:
        st.markdown("### ⚠️ Factors That Reduced Accuracy")
        factors_bad = result.get("factors_reduced_accuracy", [])
        if factors_bad:
            for f in factors_bad:
                st.markdown(
                    f'<div style="background:#431407; border-left:4px solid #f97316; '
                    f'border-radius:6px; padding:10px 14px; margin-bottom:8px; color:#fed7aa;">'
                    f'⚠️ {f}</div>',
                    unsafe_allow_html=True
                )
        else:
            st.markdown("_None identified._")

    # Method breakdown table
    st.markdown("### 📐 Method Breakdown")
    method_data = {
        "Method": ["Henssge Nomogram (Temperature)", "Rigor Mortis Stage", "Livor Mortis Stage", "Decomposition Stage"],
        "PMI Window (hours)": [
            f"{round(henssge['hours']*0.7,1)}–{round(henssge['hours']*1.3,1)}" if henssge["hours"] else "Not calculable",
            f"{rigor_window[0]}–{rigor_window[1]}",
            f"{livor_window[0]}–{livor_window[1]}",
            f"{decomp_window[0]}–{decomp_window[1]}",
        ],
        "Reliability": ["High (if temp accurate)", "Moderate", "Moderate-High", "Low-Moderate"]
    }
    import pandas as pd
    st.dataframe(pd.DataFrame(method_data), use_container_width=True, hide_index=True)

    # Save to database
    if DB_AVAILABLE and case_id:
        try:
            insert_tod_estimate(
                case_id=case_id,
                body_temp=body_temp,
                ambient_temp=ambient_temp,
                body_weight=body_weight,
                rigor_stage=rigor_stage,
                livor_stage=livor_stage,
                hypostasis_color=hypostasis_color,
                decomp_stage=decomp_stage,
                body_location=body_location,
                clothing_coverage=clothing_coverage,
                discovery_datetime=str(discovery_datetime),
                estimated_tod_range=result.get("estimated_tod_range", ""),
                central_estimate=result.get("central_estimate", ""),
                window_hours=result.get("window_hours_plus_minus", 0),
                confidence_score=score,
                reasoning=result.get("reasoning", ""),
                factors_increased=json.dumps(result.get("factors_increased_accuracy", [])),
                factors_reduced=json.dumps(result.get("factors_reduced_accuracy", [])),
                special_notes=result.get("special_notes", "")
            )
            st.success(f"✅ Result saved to case: {case_label}")
        except Exception as e:
            st.warning(f"⚠️ Could not save to database: {e}")

    # Disclaimer
    st.markdown("---")
    st.markdown(
        """
        <div style="
            background: #1c1917;
            border: 1px solid #78716c;
            border-radius: 8px;
            padding: 16px 20px;
            color: #a8a29e;
            font-size: 13px;
            line-height: 1.6;
        ">
        ⚠️ <strong style="color:#e7e5e4;">DISCLAIMER</strong><br>
        This is an AI-assisted estimate based on the data provided. Accuracy depends on the completeness 
        and correctness of input. Environmental factors not captured here (insect activity, humidity, 
        wind exposure) may significantly affect actual time of death. 
        <strong style="color:#fcd34d;">This estimate must be reviewed and verified by a certified forensic pathologist 
        before use in any investigation or legal proceeding.</strong>
        </div>
        """,
        unsafe_allow_html=True
    )