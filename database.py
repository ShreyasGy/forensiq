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
# NORMALIZERS
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_case(row):
    d = dict(row)
    d["case_id"] = d.get("case_number", "")
    d["name"]    = d.get("title", "")
    d["victim_name"]           = d.get("victim_name", "")
    d["case_type"]             = d.get("case_type") or d.get("crime_type", "")
    d["assigned_investigator"] = d.get("assigned_investigator", "")
    return d


def _normalize_tod(row):
    if row is None:
        return {}
    try:
        d = dict(row)
    except Exception:
        return {}

    # Canonical fields used by every module
    d["estimated_tod"]      = d.get("estimated_tod_range") or d.get("estimated_tod", "")
    d["time_window_start"]  = d.get("time_window_start")  or d.get("central_estimate", "")
    d["time_window_end"]    = d.get("time_window_end")     or str(d.get("window_hours", ""))
    d["confidence_score"]   = d.get("confidence_score", "")
    d["confidence"]         = d.get("confidence")         or d.get("confidence_score", "")
    d["method_used"]        = d.get("method_used")        or d.get("reasoning", "")
    d["notes"]              = (d.get("notes")
                               or d.get("special_notes")
                               or d.get("reasoning", ""))
    # Pass-through fields
    d["body_temp"]          = d.get("body_temp", "")
    d["ambient_temp"]       = d.get("ambient_temp", "")
    d["rigor_stage"]        = d.get("rigor_stage", "")
    d["livor_stage"]        = d.get("livor_stage", "")
    d["reasoning"]          = d.get("reasoning", "")
    d["factors_increased"]  = d.get("factors_increased", "")
    d["factors_reduced"]    = d.get("factors_reduced", "")
    d["special_notes"]      = d.get("special_notes", "")
    return d


def _normalize_suspect(row):
    if row is None:
        return {}
    try:
        d = dict(row)
    except Exception:
        return {}

    d["suspect_name"]  = d.get("suspect_name") or d.get("name", "Unknown")
    d["name"]          = d["suspect_name"]
    # priority_rank stored as threat_level (TEXT) in DB; expose both keys
    d["priority_rank"] = d.get("priority_rank") or d.get("threat_level", "")
    d["threat_level"]  = d["priority_rank"]
    d["motive"]        = d.get("motive", "")
    d["alibi"]         = d.get("alibi", "")
    d["notes"]         = d.get("notes", "")
    d["age"]           = d.get("age", "")
    d["gender"]        = d.get("gender", "")
    d["description"]   = d.get("description", "")
    return d


def _normalize_cctv(row):
    d = dict(row)
    d["camera_id"]       = d.get("camera_id")       or ""
    d["timestamp"]       = d.get("timestamp")        or ""
    d["location"]        = d.get("location")         or ""
    d["description"]     = d.get("description")      or ""
    d["latitude"]        = d.get("latitude")
    d["longitude"]       = d.get("longitude")
    d["confidence"]      = d.get("confidence")       or ""
    d["notes"]           = d.get("notes")            or ""
    d["flagged"]         = bool(d.get("flagged") or d.get("notes", ""))
    d["camera_location"] = d.get("camera_location")  or d.get("location") or ""
    return d


def _normalize_autopsy(row):
    if row is None:
        return None
    try:
        d = dict(row)
    except Exception:
        return row

    d["cause_of_death"]    = d.get("cause_of_death")    or d.get("injury_type",     "")
    d["manner_of_death"]   = d.get("manner_of_death")   or d.get("soap_assessment", "")
    d["injuries"]          = d.get("injuries")          or d.get("body_location",   "")
    d["findings"]          = d.get("findings")          or d.get("anomalies",        "")
    d["key_terms"]         = d.get("key_terms")         or d.get("time_indicators", "")
    d["weapon"]            = d.get("weapon")            or d.get("weapon_type",     "")
    d["defensive_wounds"]  = d.get("defensive_wounds",  "")
    d["signs_of_struggle"] = d.get("signs_of_struggle", "")
    d["toxicology"]        = d.get("toxicology",        "")
    d["soap_subjective"]   = d.get("soap_subjective",   "")
    d["soap_objective"]    = d.get("soap_objective",    "")
    d["soap_assessment"]   = d.get("soap_assessment",   "")
    d["soap_plan"]         = d.get("soap_plan",         "")
    return d


def _normalize_risk(row):
    if row is None:
        return {}
    try:
        d = dict(row)
    except Exception:
        return {}

    # Aliases so every module reads the same keys.
    # DB has both 'score' and 'risk_score' columns — prefer whichever is set.
    d["score"]         = d.get("risk_score") or d.get("score") or ""
    d["risk_score"]    = d["score"]
    d["risk_level"]    = d.get("risk_category") or d.get("risk_level") or ""
    d["risk_category"] = d["risk_level"]
    d["factors"]       = d.get("factors",        "")
    d["reasoning"]     = d.get("reasoning",      "")
    d["recommendations"] = d.get("recommendations", "")
    d["calculated_at"] = d.get("calculated_at") or d.get("created_at", "")

    # Parse / rebuild notes JSON so every consumer can access it.
    import json as _json
    notes_raw = d.get("notes", "")
    notes_dict = {}
    if notes_raw:
        try:
            notes_dict = _json.loads(notes_raw)
        except Exception:
            pass

    if not notes_dict:
        notes_dict = {
            "rationale":           d.get("reasoning", ""),
            "red_flags":           d.get("factors", ""),
            "recommended_actions": d.get("recommendations", ""),
        }
    d["notes"] = _json.dumps(notes_dict)
    # Expose top-level convenience keys from notes
    d["rationale"]           = notes_dict.get("rationale", d.get("reasoning", ""))
    d["red_flags"]           = notes_dict.get("red_flags", [])
    d["recommended_actions"] = notes_dict.get("recommended_actions", [])
    d["evidence_gaps"]       = notes_dict.get("evidence_gaps", [])
    d["confidence"]          = notes_dict.get("confidence", "")
    d["evidence_quality"]    = notes_dict.get("evidence_quality", {})
    return d


def _normalize_witness(row):
    if row is None:
        return {}
    try:
        d = dict(row)
    except Exception:
        return {}

    # witness_name: stored in its own column (after migration) or falls back to key_people
    d["witness_name"]      = (d.get("witness_name")
                               or d.get("key_people", "Unknown"))
    d["statement_text"]    = (d.get("statement_text")
                               or d.get("raw_text")
                               or d.get("statement", ""))
    d["statement"]         = d["statement_text"]
    d["recorded_at"]       = d.get("recorded_at") or d.get("created_at", "")
    d["reliability_score"] = (d.get("reliability_score")
                               or d.get("reliability_rating", ""))
    d["contradictions"]    = d.get("contradictions", "")
    return d


# ─────────────────────────────────────────────────────────────────────────────
# PK RESOLVER
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_case_pk(case_id):
    """
    Accept an int PK or an 'FQ-YYYYMMDD-XXXX' string.
    Returns the integer id used in the cases table, or None.
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
        return int(case_id)
    except (ValueError, TypeError):
        return None
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# DATABASE INITIALISATION
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

    # Extra columns added by demo_mode.py
    for col, col_type in [
        ("cause_of_death",  "TEXT"),
        ("manner_of_death", "TEXT"),
        ("injuries",        "TEXT"),
        ("findings",        "TEXT"),
        ("key_terms",       "TEXT"),
    ]:
        try:
            c.execute(f"ALTER TABLE autopsy_reports ADD COLUMN {col} {col_type}")
        except sqlite3.OperationalError:
            pass

    # ── witness_statements ─────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS witness_statements (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id            INTEGER,
            witness_name       TEXT,
            raw_text           TEXT,
            timeline           TEXT,
            key_people         TEXT,
            key_locations      TEXT,
            key_objects        TEXT,
            contradictions     TEXT,
            reliability_rating TEXT,
            cross_references   TEXT,
            created_at         TEXT DEFAULT (datetime('now'))
        )
    """)

    # witness_name column may be absent on older DBs
    try:
        c.execute("ALTER TABLE witness_statements ADD COLUMN witness_name TEXT")
    except sqlite3.OperationalError:
        pass

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

    # Migrate any missing TOD columns
    for col, col_type in [
        ("body_weight",         "REAL"),
        ("ambient_temp",        "REAL"),
        ("body_temp",           "REAL"),
        ("rigor_stage",         "TEXT"),
        ("livor_stage",         "TEXT"),
        ("hypostasis_color",    "TEXT"),
        ("decomp_stage",        "TEXT"),
        ("body_location",       "TEXT"),
        ("clothing_coverage",   "TEXT"),
        ("discovery_datetime",  "TEXT"),
        ("estimated_tod_range", "TEXT"),
        ("central_estimate",    "TEXT"),
        ("window_hours",        "REAL"),
        ("confidence_score",    "REAL"),
        ("reasoning",           "TEXT"),
        ("factors_increased",   "TEXT"),
        ("factors_reduced",     "TEXT"),
        ("special_notes",       "TEXT"),
        # Aliases stored by demo_mode.py
        ("estimated_tod",       "TEXT"),
        ("time_window_start",   "TEXT"),
        ("time_window_end",     "TEXT"),
        ("method_used",         "TEXT"),
        ("notes",               "TEXT"),
        ("confidence",          "TEXT"),
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
            suspect_name TEXT,
            age          TEXT,
            gender       TEXT,
            description  TEXT,
            motive       TEXT,
            alibi        TEXT,
            threat_level TEXT,
            priority_rank TEXT,
            notes        TEXT,
            created_at   TEXT DEFAULT (datetime('now'))
        )
    """)

    for col, col_type in [
        ("suspect_name",  "TEXT"),
        ("priority_rank", "TEXT"),
    ]:
        try:
            c.execute(f"ALTER TABLE suspects ADD COLUMN {col} {col_type}")
        except sqlite3.OperationalError:
            pass

    # ── risk_scores ────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS risk_scores (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id         INTEGER,
            score           REAL,
            risk_score      REAL,
            risk_level      TEXT,
            risk_category   TEXT,
            reasoning       TEXT,
            factors         TEXT,
            recommendations TEXT,
            notes           TEXT,
            created_at      TEXT DEFAULT (datetime('now'))
        )
    """)

    # Migrate risk_scores columns that risk_scorer.py expects
    for col, col_type in [
        ("risk_score",    "REAL"),
        ("risk_category", "TEXT"),
        ("notes",         "TEXT"),
    ]:
        try:
            c.execute(f"ALTER TABLE risk_scores ADD COLUMN {col} {col_type}")
        except sqlite3.OperationalError:
            pass

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

    try:
        c.execute("ALTER TABLE cctv_sightings ADD COLUMN camera_id TEXT")
    except sqlite3.OperationalError:
        pass

    # ── tracked_persons ────────────────────────────────────────────────────
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

    # ── crime_patterns ─────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS crime_patterns (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            case_ids        TEXT,
            pattern_summary TEXT,
            convergence_pct REAL,
            common_factors  TEXT,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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

def insert_autopsy_report(data_or_case_id=None, filename="", raw_text="",
                           soap_subjective="", soap_objective="",
                           soap_assessment="", soap_plan="",
                           injury_type="", body_location="", weapon_type="",
                           defensive_wounds="", signs_of_struggle="",
                           toxicology="", time_indicators="", anomalies="",
                           cause_of_death="", manner_of_death="",
                           injuries="", findings="", key_terms="", **kwargs):

    if isinstance(data_or_case_id, dict):
        d = data_or_case_id
        case_id           = d.get("case_id", "")
        filename          = d.get("filename", d.get("file_name", ""))
        raw_text          = d.get("raw_text", "")
        soap_subjective   = d.get("soap_subjective", "")
        soap_objective    = d.get("soap_objective", "")
        soap_assessment   = d.get("soap_assessment", "")
        soap_plan         = d.get("soap_plan", "")
        injury_type       = d.get("injury_type", "")
        body_location     = d.get("body_location", "")
        weapon_type       = d.get("weapon_type", "")
        defensive_wounds  = d.get("defensive_wounds", "")
        signs_of_struggle = d.get("signs_of_struggle", "")
        toxicology        = d.get("toxicology", "")
        time_indicators   = d.get("time_indicators", "")
        anomalies         = d.get("anomalies", "")
        cause_of_death    = d.get("cause_of_death", "")
        manner_of_death   = d.get("manner_of_death", "")
        injuries          = d.get("injuries", "")
        findings          = d.get("findings", "")
        key_terms         = d.get("key_terms", "")
    else:
        case_id = data_or_case_id

    pk = _resolve_case_pk(case_id)
    conn = get_connection()
    conn.execute("""
        INSERT INTO autopsy_reports (
            case_id, filename, raw_text,
            soap_subjective, soap_objective, soap_assessment, soap_plan,
            injury_type, body_location, weapon_type,
            defensive_wounds, signs_of_struggle, toxicology,
            time_indicators, anomalies,
            cause_of_death, manner_of_death, injuries, findings, key_terms
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (pk, filename, raw_text,
          soap_subjective, soap_objective, soap_assessment, soap_plan,
          injury_type, body_location, weapon_type,
          defensive_wounds, signs_of_struggle, toxicology,
          time_indicators, anomalies,
          cause_of_death, manner_of_death, injuries, findings, key_terms))
    conn.commit()
    conn.close()


def get_autopsy_by_case(case_id):
    pk = _resolve_case_pk(case_id)
    if pk is None:
        return []
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM autopsy_reports WHERE case_id = ? ORDER BY id DESC",
        (pk,)
    ).fetchall()
    conn.close()

    result = []
    for row in rows:
        d = dict(row)
        # Resolve the aliases case_manager.py and others expect
        d["cause_of_death"] = (d.get("cause_of_death")
                                or d.get("injury_type")
                                or d.get("soap_assessment", ""))
        d["report_text"]    = (d.get("report_text")
                                or d.get("raw_text")
                                or d.get("soap_subjective", ""))
        d["uploaded_at"]    = d.get("uploaded_at") or d.get("created_at", "")
        result.append(d)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# WITNESS HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def insert_witness_statement(data_or_case_id=None, witness_name="",
                              raw_text="", timeline="", key_people="",
                              key_locations="", key_objects="",
                              contradictions="", reliability_rating="",
                              cross_references="", **kwargs):
    if isinstance(data_or_case_id, dict):
        d = data_or_case_id
        case_id            = d.get("case_id", "")
        # Accept every field name any caller might use
        witness_name       = (d.get("witness_name", ""))
        raw_text           = (d.get("raw_text")
                              or d.get("statement")
                              or d.get("statement_text", ""))
        timeline           = d.get("timeline", "")
        key_people         = d.get("key_people", "")
        key_locations      = d.get("key_locations", "")
        key_objects        = d.get("key_objects", "")
        contradictions     = d.get("contradictions", "")
        reliability_rating = (d.get("reliability_rating")
                              or d.get("reliability_score", ""))
        cross_references   = d.get("cross_references", "")
    else:
        case_id = data_or_case_id

    pk = _resolve_case_pk(case_id)
    conn = get_connection()
    conn.execute("""
        INSERT INTO witness_statements (
            case_id, witness_name, raw_text, timeline,
            key_people, key_locations, key_objects,
            contradictions, reliability_rating, cross_references
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (pk, witness_name, raw_text, timeline,
          key_people, key_locations, key_objects,
          contradictions, reliability_rating, cross_references))
    conn.commit()
    conn.close()


def get_witnesses_by_case(case_id):
    pk = _resolve_case_pk(case_id)
    if pk is None:
        return []
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM witness_statements WHERE case_id = ? ORDER BY id DESC",
        (pk,)
    ).fetchall()
    conn.close()
    return [_normalize_witness(r) for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# TOD HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def insert_tod_estimate(data_or_case_id=None, body_temp="", ambient_temp="",
                        body_weight="", rigor_stage="", livor_stage="",
                        hypostasis_color="", decomp_stage="", body_location="",
                        clothing_coverage="", discovery_datetime="",
                        estimated_tod_range="", central_estimate="",
                        window_hours="", confidence_score="", reasoning="",
                        factors_increased="", factors_reduced="",
                        special_notes="",
                        # aliases that demo_mode.py uses
                        estimated_tod="", time_window_start="",
                        time_window_end="", method_used="", notes="",
                        confidence="", **kwargs):

    if isinstance(data_or_case_id, dict):
        d = data_or_case_id
        case_id             = d.get("case_id", "")
        body_temp           = d.get("body_temp", "")
        ambient_temp        = d.get("ambient_temp", "")
        body_weight         = d.get("body_weight", "")
        rigor_stage         = d.get("rigor_stage", "")
        livor_stage         = d.get("livor_stage", "")
        hypostasis_color    = d.get("hypostasis_color", "")
        decomp_stage        = d.get("decomp_stage", "")
        body_location       = d.get("body_location", "")
        clothing_coverage   = d.get("clothing_coverage", "")
        discovery_datetime  = d.get("discovery_datetime", "")
        # Resolve estimated_tod_range from all possible keys
        estimated_tod_range = (d.get("estimated_tod_range")
                                or d.get("estimated_tod", ""))
        central_estimate    = (d.get("central_estimate")
                                or d.get("time_window_start", ""))
        window_hours        = (d.get("window_hours")
                                or d.get("time_window_end", ""))
        confidence_score    = (d.get("confidence_score")
                                or d.get("confidence", ""))
        reasoning           = (d.get("reasoning")
                                or d.get("notes")
                                or d.get("method_used", ""))
        factors_increased   = d.get("factors_increased", "")
        factors_reduced     = d.get("factors_reduced", "")
        special_notes       = d.get("special_notes", "")
        # Extra alias fields
        estimated_tod       = estimated_tod_range
        time_window_start   = central_estimate
        time_window_end     = str(window_hours)
        method_used         = reasoning
        notes               = reasoning
        confidence          = str(confidence_score)
    else:
        case_id = data_or_case_id
        # Fill derived aliases for non-dict calls
        estimated_tod     = estimated_tod_range
        time_window_start = central_estimate
        time_window_end   = str(window_hours)
        method_used       = reasoning
        notes             = reasoning
        confidence        = str(confidence_score)

    pk = _resolve_case_pk(case_id)
    conn = get_connection()
    conn.execute("""
        INSERT INTO tod_estimates (
            case_id, body_temp, ambient_temp, body_weight, rigor_stage,
            livor_stage, hypostasis_color, decomp_stage, body_location,
            clothing_coverage, discovery_datetime,
            estimated_tod_range, central_estimate, window_hours,
            confidence_score, reasoning, factors_increased, factors_reduced,
            special_notes,
            estimated_tod, time_window_start, time_window_end,
            method_used, notes, confidence
        ) VALUES (
            ?, ?, ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?,
            ?, ?, ?,
            ?, ?, ?, ?,
            ?,
            ?, ?, ?,
            ?, ?, ?
        )
    """, (pk, body_temp, ambient_temp, body_weight, rigor_stage,
          livor_stage, hypostasis_color, decomp_stage, body_location,
          clothing_coverage, discovery_datetime,
          estimated_tod_range, central_estimate, window_hours,
          confidence_score, reasoning, factors_increased, factors_reduced,
          special_notes,
          estimated_tod, time_window_start, time_window_end,
          method_used, notes, confidence))
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


# Keep legacy alias used by some modules
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

def insert_suspect(data_or_case_id=None, name="", age="", gender="",
                   description="", motive="", alibi="", threat_level="",
                   notes="", suspect_name="", priority_rank="", **kwargs):

    if isinstance(data_or_case_id, dict):
        d = data_or_case_id
        case_id       = d.get("case_id", "")
        suspect_name  = d.get("suspect_name") or d.get("name", "")
        name          = suspect_name
        age           = d.get("age", "")
        gender        = d.get("gender", "")
        description   = d.get("description", "")
        motive        = d.get("motive", "")
        alibi         = d.get("alibi", "")
        # priority_rank from demo_mode; threat_level from forensic_profiler
        priority_rank = str(d.get("priority_rank", d.get("threat_level", "")))
        threat_level  = priority_rank
        notes         = d.get("notes", "")
    else:
        case_id = data_or_case_id
        if not name and suspect_name:
            name = suspect_name
        if not threat_level and priority_rank:
            threat_level = str(priority_rank)

    pk = _resolve_case_pk(case_id)
    conn = get_connection()
    conn.execute("""
        INSERT INTO suspects (
            case_id, name, suspect_name, age, gender, description,
            motive, alibi, threat_level, priority_rank, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (pk, name, name, age, gender, description,
          motive, alibi, threat_level, threat_level, notes))
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

def insert_risk_score(data_or_case_id=None, score="", risk_level="",
                      reasoning="", factors="", recommendations="",
                      risk_score="", risk_category="", notes="",
                      **kwargs):
    """
    Accepts both dict and positional/keyword styles.
    Writes to ALL four columns (score, risk_score, risk_level, risk_category)
    so that every reader sees consistent data regardless of which column name
    it prefers.  Also persists the full notes JSON blob.
    """
    import json as _json

    if isinstance(data_or_case_id, dict):
        d = data_or_case_id
        case_id         = d.get("case_id", "")
        score           = d.get("score") or d.get("risk_score", "")
        risk_level      = d.get("risk_level") or d.get("risk_category", "")
        notes_raw       = d.get("notes", "")
        try:
            notes_dict  = _json.loads(notes_raw) if notes_raw else {}
        except Exception:
            notes_dict  = {}
        reasoning       = d.get("reasoning") or notes_dict.get("rationale", "")
        factors         = d.get("factors") or str(notes_dict.get("red_flags", ""))
        recommendations = d.get("recommendations") or str(notes_dict.get("recommended_actions", ""))
        notes           = notes_raw  # preserve the full JSON as-is
    else:
        case_id = data_or_case_id
        # Merge score/risk_score and risk_level/risk_category aliases
        score      = score      or risk_score
        risk_level = risk_level or risk_category
        notes_raw  = notes
        try:
            notes_dict  = _json.loads(notes_raw) if notes_raw else {}
        except Exception:
            notes_dict  = {}
        reasoning       = reasoning       or notes_dict.get("rationale", "")
        factors         = factors         or str(notes_dict.get("red_flags", ""))
        recommendations = recommendations or str(notes_dict.get("recommended_actions", ""))
        # notes stays as notes_raw (the full JSON string from risk_scorer.py)

    pk = _resolve_case_pk(case_id)
    conn = get_connection()
    # Write to ALL alias columns so every reader finds data
    conn.execute("""
        INSERT INTO risk_scores (
            case_id,
            score, risk_score,
            risk_level, risk_category,
            reasoning, factors, recommendations,
            notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        pk,
        score, score,          # score + risk_score
        risk_level, risk_level,  # risk_level + risk_category
        reasoning, factors, recommendations,
        notes,
    ))
    conn.commit()
    conn.close()


def get_risk_score_by_case(case_id):
    """
    Returns the MOST RECENT risk score for a case as a single normalized dict,
    or an empty dict if none exists.
    """
    pk = _resolve_case_pk(case_id)
    if pk is None:
        return {}
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM risk_scores WHERE case_id = ? ORDER BY created_at DESC LIMIT 1",
        (pk,)
    ).fetchone()
    conn.close()
    return _normalize_risk(row) if row else {}


# ─────────────────────────────────────────────────────────────────────────────
# CCTV HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def insert_cctv_sighting(case_id, timestamp, location, description,
                          latitude, longitude, confidence, notes,
                          camera_id=""):
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
# TRACKED PERSON HELPERS
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


# ─────────────────────────────────────────────────────────────────────────────
# CRIME PATTERN HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def insert_crime_pattern(case_ids_list, pattern_summary, convergence_pct, common_factors):
    conn = get_connection()
    conn.execute("""
        INSERT INTO crime_patterns (case_ids, pattern_summary, convergence_pct, common_factors)
        VALUES (?, ?, ?, ?)
    """, (
        json.dumps(case_ids_list),
        pattern_summary,
        float(convergence_pct),
        common_factors if isinstance(common_factors, str) else json.dumps(common_factors),
    ))
    conn.commit()
    conn.close()


def get_all_patterns():
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM crime_patterns ORDER BY created_at DESC"
        ).fetchall()
    except Exception:
        rows = []
    conn.close()
    return [dict(r) for r in rows]
