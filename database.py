import sqlite3
import json
import os
from datetime import datetime
import random
import string

DB_PATH = "forensiq.db"


# ─────────────────────────────────────────────────────────────────────────────
# CONNECTION
# ─────────────────────────────────────────────────────────────────────────────

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ─────────────────────────────────────────────────────────────────────────────
# CASE ID GENERATOR
# ─────────────────────────────────────────────────────────────────────────────

def generate_case_id():
    date_str = datetime.now().strftime("%Y%m%d")
    suffix = "".join(random.choices(string.digits, k=4))
    return f"FQ-{date_str}-{suffix}"


# ─────────────────────────────────────────────────────────────────────────────
# NORMALIZERS  (inject alias keys that the UI pages expect)
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_case(row):
    """
    case_manager.py always reads case['case_id'] and case['name'].
    The real DB columns are 'case_number' and 'title'.
    This function injects the expected aliases so nothing breaks.
    """
    d = dict(row)
    d["case_id"] = d.get("case_number", "")
    d["name"] = d.get("title", "")
    d["victim_name"] = d.get("victim_name", "")
    d["case_type"] = d.get("case_type") or d.get("crime_type", "")
    d["assigned_investigator"] = d.get("assigned_investigator", "")
    return d


def _normalize_tod(row):
    """
    case_manager.py reads: t['estimated_tod'], t['method_used'],
    t['confidence'], t['notes'].
    The real DB columns have different names — map them here.
    """
    d = dict(row)
    d["estimated_tod"] = d.get("estimated_tod_range", "")
    d["method_used"] = "Henssge + Rigor + Livor + Decomposition"
    score = d.get("confidence_score", 0) or 0
    d["confidence"] = f"{int(score)}%" if score else "N/A"
    d["notes"] = d.get("special_notes", "") or d.get("reasoning", "")
    return d


def _normalize_suspect(row):
    """
    case_manager.py reads: s['suspect_name'], s['relation'].
    The real DB columns are 'name' and 'motive' — map them here.
    """
    d = dict(row)
    d["suspect_name"] = d.get("name", "")
    d["relation"] = d.get("motive", "")
    return d


def _normalize_cctv(row):
    """
    Ensure all CCTV sighting keys exist with safe defaults.
    Adds 'camera_id' which was a Session-5 migration column.
    """
    d = dict(row)
    d["camera_id"] = d.get("camera_id") or ""
    d["timestamp"] = d.get("timestamp") or ""
    d["location"] = d.get("location") or ""
    d["description"] = d.get("description") or ""
    d["latitude"] = d.get("latitude")
    d["longitude"] = d.get("longitude")
    d["confidence"] = d.get("confidence") or ""
    d["notes"] = d.get("notes") or ""
    return d


# ─────────────────────────────────────────────────────────────────────────────
# PK RESOLVER
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_case_pk(case_id):
    """
    Accept either an integer PK or a 'FQ-YYYYMMDD-XXXX' string.
    Returns the integer id used in the cases table, or None on failure.
    """
    if isinstance(case_id, int):
        return case_id
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id FROM cases WHERE case_number = ?", (case_id,)
        ).fetchone()
        if row:
            return row["id"]
        return int(case_id)          # handles numeric strings
    except (ValueError, TypeError):
        return None
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# DATABASE INITIALISATION  (creates tables + runs ALL migrations)
# ─────────────────────────────────────────────────────────────────────────────

def init_db():
    conn = get_connection()
    c = conn.cursor()

    # ── cases ──────────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS cases (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            case_number          TEXT    UNIQUE NOT NULL,
            title                TEXT    NOT NULL,
            status               TEXT    DEFAULT 'Open',
            priority             TEXT    DEFAULT 'Medium',
            crime_type           TEXT,
            location             TEXT,
            description          TEXT,
            created_at           TEXT    DEFAULT (datetime('now')),
            updated_at           TEXT    DEFAULT (datetime('now'))
        )
    """)

    for col, col_type in [
        ("victim_name",           "TEXT"),
        ("victim_age",            "TEXT"),
        ("victim_gender",         "TEXT"),
        ("incident_date",         "TEXT"),
        ("incident_time",         "TEXT"),
        ("assigned_investigator", "TEXT"),
        ("initial_notes",         "TEXT"),
        ("case_type",             "TEXT"),
    ]:
        try:
            c.execute(f"ALTER TABLE cases ADD COLUMN {col} {col_type}")
        except sqlite3.OperationalError:
            pass

    # ── autopsy_reports ────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS autopsy_reports (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id           INTEGER,
            filename          TEXT,
            raw_text          TEXT,
            soap_subjective   TEXT,
            soap_objective    TEXT,
            soap_assessment   TEXT,
            soap_plan         TEXT,
            injury_type       TEXT,
            body_location     TEXT,
            weapon_type       TEXT,
            defensive_wounds  TEXT,
            signs_of_struggle TEXT,
            toxicology        TEXT,
            time_indicators   TEXT,
            anomalies         TEXT,
            created_at        TEXT DEFAULT (datetime('now'))
        )
    """)

    # ── witness_statements ─────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS witness_statements (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id           INTEGER,
            raw_text          TEXT,
            timeline          TEXT,
            key_people        TEXT,
            key_locations     TEXT,
            key_objects       TEXT,
            contradictions    TEXT,
            reliability_rating TEXT,
            cross_references  TEXT,
            created_at        TEXT DEFAULT (datetime('now'))
        )
    """)

    # ── tod_estimates ──────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS tod_estimates (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id             INTEGER,
            body_temp           REAL,
            ambient_temp        REAL,
            body_weight         REAL,
            rigor_stage         TEXT,
            livor_stage         TEXT,
            hypostasis_color    TEXT,
            decomp_stage        TEXT,
            body_location       TEXT,
            clothing_coverage   TEXT,
            discovery_datetime  TEXT,
            estimated_tod_range TEXT,
            central_estimate    TEXT,
            window_hours        REAL,
            confidence_score    REAL,
            reasoning           TEXT,
            factors_increased   TEXT,
            factors_reduced     TEXT,
            special_notes       TEXT,
            created_at          TEXT DEFAULT (datetime('now'))
        )
    """)

    for col, col_type in [
        ("body_weight",          "REAL"),
        ("ambient_temp",         "REAL"),
        ("body_temp",            "REAL"),
        ("rigor_stage",          "TEXT"),
        ("livor_stage",          "TEXT"),
        ("hypostasis_color",     "TEXT"),
        ("decomp_stage",         "TEXT"),
        ("body_location",        "TEXT"),
        ("clothing_coverage",    "TEXT"),
        ("discovery_datetime",   "TEXT"),
        ("estimated_tod_range",  "TEXT"),
        ("central_estimate",     "TEXT"),
        ("window_hours",         "REAL"),
        ("confidence_score",     "REAL"),
        ("reasoning",            "TEXT"),
        ("factors_increased",    "TEXT"),
        ("factors_reduced",      "TEXT"),
        ("special_notes",        "TEXT"),
    ]:
        try:
            c.execute(f"ALTER TABLE tod_estimates ADD COLUMN {col} {col_type}")
        except sqlite3.OperationalError:
            pass

    # ── suspects ───────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS suspects (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id      INTEGER,
            name         TEXT,
            age          TEXT,
            gender       TEXT,
            description  TEXT,
            motive       TEXT,
            alibi        TEXT,
            threat_level TEXT,
            notes        TEXT,
            created_at   TEXT DEFAULT (datetime('now'))
        )
    """)

    # ── risk_scores ────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS risk_scores (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id         INTEGER,
            score           REAL,
            risk_level      TEXT,
            reasoning       TEXT,
            factors         TEXT,
            recommendations TEXT,
            created_at      TEXT DEFAULT (datetime('now'))
        )
    """)

    # ── cctv_sightings ─────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS cctv_sightings (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id     INTEGER,
            camera_id   TEXT,
            timestamp   TEXT,
            location    TEXT,
            description TEXT,
            latitude    REAL,
            longitude   REAL,
            confidence  TEXT,
            notes       TEXT,
            created_at  TEXT DEFAULT (datetime('now'))
        )
    """)

    # Migration: add camera_id if the table already existed without it
    try:
        c.execute("ALTER TABLE cctv_sightings ADD COLUMN camera_id TEXT")
    except sqlite3.OperationalError:
        pass

    # ── tracked_persons  (NEW — Session 5) ────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS tracked_persons (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id                 INTEGER,
            name                    TEXT,
            alias                   TEXT,
            height_cm               REAL,
            weight_kg               REAL,
            hair_color              TEXT,
            hair_length             TEXT,
            clothing_top            TEXT,
            clothing_bottom         TEXT,
            footwear                TEXT,
            accessories             TEXT,
            distinguishing_features TEXT,
            last_seen_location      TEXT,
            last_seen_time          TEXT,
            cctv_description        TEXT,
            created_at              TEXT DEFAULT (datetime('now'))
        )
    """)

    conn.commit()
    conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# CASE HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def get_all_cases():
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM cases ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [_normalize_case(r) for r in rows]


def get_case_by_id(case_id):
    pk = _resolve_case_pk(case_id)
    if pk is None:
        return None
    conn = get_connection()
    row = conn.execute("SELECT * FROM cases WHERE id = ?", (pk,)).fetchone()
    conn.close()
    return _normalize_case(row) if row else None


def insert_case(data: dict):
    conn = get_connection()
    conn.execute("""
        INSERT INTO cases (
            case_number, title, status, priority, crime_type, location,
            description, victim_name, victim_age, victim_gender,
            incident_date, incident_time, assigned_investigator,
            initial_notes, case_type
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data.get("case_id", generate_case_id()),
        data.get("title", data.get("name", "")),
        data.get("status", "Open"),
        data.get("priority", "Medium"),
        data.get("crime_type", data.get("case_type", "")),
        data.get("location", ""),
        data.get("description", ""),
        data.get("victim_name", ""),
        data.get("victim_age", ""),
        data.get("victim_gender", ""),
        data.get("incident_date", ""),
        data.get("incident_time", ""),
        data.get("assigned_investigator", ""),
        data.get("initial_notes", ""),
        data.get("case_type", data.get("crime_type", "")),
    ))
    conn.commit()
    conn.close()


def update_case(case_id, **kwargs):
    pk = _resolve_case_pk(case_id)
    if pk is None:
        return
    conn = get_connection()
    kwargs["updated_at"] = datetime.now().isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [pk]
    conn.execute(f"UPDATE cases SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()


def delete_case(case_id):
    pk = _resolve_case_pk(case_id)
    if pk is None:
        return
    conn = get_connection()
    conn.execute("DELETE FROM cases WHERE id = ?", (pk,))
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# AUTOPSY HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def insert_autopsy_report(case_id, filename, raw_text, soap_subjective,
                           soap_objective, soap_assessment, soap_plan,
                           injury_type, body_location, weapon_type,
                           defensive_wounds, signs_of_struggle,
                           toxicology, time_indicators, anomalies):
    pk = _resolve_case_pk(case_id)
    conn = get_connection()
    conn.execute("""
        INSERT INTO autopsy_reports (
            case_id, filename, raw_text, soap_subjective, soap_objective,
            soap_assessment, soap_plan, injury_type, body_location,
            weapon_type, defensive_wounds, signs_of_struggle,
            toxicology, time_indicators, anomalies
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (pk, filename, raw_text, soap_subjective, soap_objective,
          soap_assessment, soap_plan, injury_type, body_location,
          weapon_type, defensive_wounds, signs_of_struggle,
          toxicology, time_indicators, anomalies))
    conn.commit()
    conn.close()


def get_autopsy_by_case(case_id):
    pk = _resolve_case_pk(case_id)
    if pk is None:
        return []
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM autopsy_reports WHERE case_id = ? ORDER BY created_at DESC",
        (pk,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# WITNESS HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def insert_witness_statement(case_id, raw_text, timeline, key_people,
                              key_locations, key_objects, contradictions,
                              reliability_rating, cross_references):
    pk = _resolve_case_pk(case_id)
    conn = get_connection()
    conn.execute("""
        INSERT INTO witness_statements (
            case_id, raw_text, timeline, key_people, key_locations,
            key_objects, contradictions, reliability_rating, cross_references
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (pk, raw_text, timeline, key_people, key_locations,
          key_objects, contradictions, reliability_rating, cross_references))
    conn.commit()
    conn.close()


def get_witnesses_by_case(case_id):
    pk = _resolve_case_pk(case_id)
    if pk is None:
        return []
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM witness_statements WHERE case_id = ? ORDER BY created_at DESC",
        (pk,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# TOD HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def insert_tod_estimate(case_id, body_temp, ambient_temp, body_weight,
                         rigor_stage, livor_stage, hypostasis_color,
                         decomp_stage, body_location, clothing_coverage,
                         discovery_datetime, estimated_tod_range,
                         central_estimate, window_hours, confidence_score,
                         reasoning, factors_increased, factors_reduced,
                         special_notes):
    pk = _resolve_case_pk(case_id)
    conn = get_connection()
    conn.execute("""
        INSERT INTO tod_estimates (
            case_id, body_temp, ambient_temp, body_weight, rigor_stage,
            livor_stage, hypostasis_color, decomp_stage, body_location,
            clothing_coverage, discovery_datetime, estimated_tod_range,
            central_estimate, window_hours, confidence_score, reasoning,
            factors_increased, factors_reduced, special_notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (pk, body_temp, ambient_temp, body_weight, rigor_stage,
          livor_stage, hypostasis_color, decomp_stage, body_location,
          clothing_coverage, discovery_datetime, estimated_tod_range,
          central_estimate, window_hours, confidence_score, reasoning,
          factors_increased, factors_reduced, special_notes))
    conn.commit()
    conn.close()


def get_tod_by_case(case_id):
    pk = _resolve_case_pk(case_id)
    if pk is None:
        return []
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM tod_estimates WHERE case_id = ? ORDER BY created_at DESC",
        (pk,)
    ).fetchall()
    conn.close()
    return [_normalize_tod(r) for r in rows]


def get_tod_estimates_by_case(case_id):
    return get_tod_by_case(case_id)


def get_all_tod_estimates():
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM tod_estimates ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [_normalize_tod(r) for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# SUSPECT HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def insert_suspect(case_id, name, age, gender, description,
                   motive, alibi, threat_level, notes):
    pk = _resolve_case_pk(case_id)
    conn = get_connection()
    conn.execute("""
        INSERT INTO suspects (
            case_id, name, age, gender, description,
            motive, alibi, threat_level, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (pk, name, age, gender, description,
          motive, alibi, threat_level, notes))
    conn.commit()
    conn.close()


def get_suspects_by_case(case_id):
    pk = _resolve_case_pk(case_id)
    if pk is None:
        return []
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM suspects WHERE case_id = ? ORDER BY created_at DESC",
        (pk,)
    ).fetchall()
    conn.close()
    return [_normalize_suspect(r) for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# RISK SCORE HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def insert_risk_score(case_id, score, risk_level, reasoning,
                      factors, recommendations):
    pk = _resolve_case_pk(case_id)
    conn = get_connection()
    conn.execute("""
        INSERT INTO risk_scores (
            case_id, score, risk_level, reasoning, factors, recommendations
        ) VALUES (?, ?, ?, ?, ?, ?)
    """, (pk, score, risk_level, reasoning, factors, recommendations))
    conn.commit()
    conn.close()


def get_risk_score_by_case(case_id):
    pk = _resolve_case_pk(case_id)
    if pk is None:
        return []
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM risk_scores WHERE case_id = ? ORDER BY created_at DESC",
        (pk,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# CCTV HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def insert_cctv_sighting(case_id, timestamp, location, description,
                          latitude, longitude, confidence, notes,
                          camera_id=""):
    """
    Save one CCTV sighting row.
    camera_id is optional (empty string by default) for backward compatibility
    with any code that was calling the old 8-parameter version.
    """
    pk = _resolve_case_pk(case_id)
    conn = get_connection()
    conn.execute("""
        INSERT INTO cctv_sightings (
            case_id, camera_id, timestamp, location, description,
            latitude, longitude, confidence, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (pk, camera_id, timestamp, location, description,
          latitude, longitude, confidence, notes))
    conn.commit()
    conn.close()


def get_cctv_by_case(case_id):
    pk = _resolve_case_pk(case_id)
    if pk is None:
        return []
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM cctv_sightings WHERE case_id = ? ORDER BY timestamp ASC",
        (pk,)
    ).fetchall()
    conn.close()
    return [_normalize_cctv(r) for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# TRACKED PERSON HELPERS  (NEW — Session 5)
# ─────────────────────────────────────────────────────────────────────────────

def insert_tracked_person(case_id, name, alias, height_cm, weight_kg,
                           hair_color, hair_length, clothing_top,
                           clothing_bottom, footwear, accessories,
                           distinguishing_features, last_seen_location,
                           last_seen_time, cctv_description):
    pk = _resolve_case_pk(case_id)
    conn = get_connection()
    conn.execute("""
        INSERT INTO tracked_persons (
            case_id, name, alias, height_cm, weight_kg,
            hair_color, hair_length, clothing_top, clothing_bottom,
            footwear, accessories, distinguishing_features,
            last_seen_location, last_seen_time, cctv_description
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (pk, name, alias, height_cm, weight_kg,
          hair_color, hair_length, clothing_top, clothing_bottom,
          footwear, accessories, distinguishing_features,
          last_seen_location, last_seen_time, cctv_description))
    conn.commit()
    conn.close()


def get_tracked_persons_by_case(case_id):
    pk = _resolve_case_pk(case_id)
    if pk is None:
        return []
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM tracked_persons WHERE case_id = ? ORDER BY created_at DESC",
        (pk,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_tracked_person_by_id(person_id):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM tracked_persons WHERE id = ?", (person_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None

# ── CRIME PATTERNS ─────────────────────────────────────────────────────────────

def insert_crime_pattern(case_ids_list, pattern_summary, convergence_pct, common_factors):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS crime_patterns (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            case_ids        TEXT,
            pattern_summary TEXT,
            convergence_pct REAL,
            common_factors  TEXT,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        INSERT INTO crime_patterns (case_ids, pattern_summary, convergence_pct, common_factors)
        VALUES (?, ?, ?, ?)
    """, (
        json.dumps(case_ids_list),
        pattern_summary,
        float(convergence_pct),
        common_factors if isinstance(common_factors, str) else json.dumps(common_factors)
    ))
    conn.commit()
    conn.close()


def get_all_patterns():
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM crime_patterns ORDER BY created_at DESC")
        rows = cursor.fetchall()
    except Exception:
        rows = []
    conn.close()
    return [dict(r) for r in rows]