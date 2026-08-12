#!/usr/bin/env python3
"""
NURA Edge — Local database (SQLite, fully offline)

A single-file SQL database that mirrors the real NURA backend's core tables
(patients + messages) but runs with zero setup, zero server, zero network.
Python's built-in sqlite3 — nothing to install.

This gives the offline demo real persistence: a patient onboarded once is
remembered, her risk level is stored, and every tip / check-in / triage
exchange is logged as conversation history — exactly like the production
platform, just in a local file instead of PostgreSQL.

The DB file lives at  nura-edge/nura_edge.db

Public API:
    init_db()                       create tables if missing
    save_patient(dict) -> id        insert a patient (from onboarding answers + risk)
    get_patient(name_or_id) -> dict find a patient by name (case-insensitive) or id
    list_patients() -> list[dict]   all patients
    log_message(patient_id, ...)    record a tip / checkin / triage / chat turn
    get_history(patient_id) -> list  that patient's messages, oldest first
"""
from __future__ import annotations
import sqlite3, pathlib, datetime, json

DB_PATH = pathlib.Path(__file__).parent.parent / "nura_edge.db"

# Patient columns we persist (subset of the real backend, the demo-relevant ones)
_PATIENT_COLS = [
    "name", "age", "weeks_pregnant_at_signup", "parity", "previous_loss_count",
    "previous_stillbirth", "previous_caesarean", "previous_preeclampsia",
    "has_hypertension", "has_diabetes", "has_sickle_cell", "has_hiv",
    "has_severe_anaemia", "multiple_pregnancy", "language", "channel",
    "risk_level", "risk_score", "status", "created_at",
]


def _conn():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row          # rows behave like dicts
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init_db():
    """Create the tables if they don't exist yet. Safe to call every run."""
    con = _conn()
    con.executescript("""
    CREATE TABLE IF NOT EXISTS patients (
        id                       INTEGER PRIMARY KEY AUTOINCREMENT,
        name                     TEXT NOT NULL,
        age                      INTEGER,
        weeks_pregnant_at_signup INTEGER,
        parity                   INTEGER DEFAULT 0,
        previous_loss_count      INTEGER DEFAULT 0,
        previous_stillbirth      INTEGER DEFAULT 0,
        previous_caesarean       INTEGER DEFAULT 0,
        previous_preeclampsia    INTEGER DEFAULT 0,
        has_hypertension         INTEGER DEFAULT 0,
        has_diabetes             INTEGER DEFAULT 0,
        has_sickle_cell          INTEGER DEFAULT 0,
        has_hiv                  INTEGER DEFAULT 0,
        has_severe_anaemia       INTEGER DEFAULT 0,
        multiple_pregnancy       INTEGER DEFAULT 0,
        language                 TEXT DEFAULT 'en',
        channel                  TEXT DEFAULT 'app',
        risk_level               TEXT,
        risk_score               INTEGER,
        status                   TEXT DEFAULT 'active',
        created_at               TEXT
    );

    CREATE TABLE IF NOT EXISTS messages (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id    INTEGER NOT NULL REFERENCES patients(id),
        direction     TEXT NOT NULL,          -- 'in' | 'out'
        channel       TEXT DEFAULT 'app',
        content       TEXT NOT NULL,
        message_type  TEXT DEFAULT 'chat',    -- 'chat' | 'tip' | 'checkin' | 'triage'
        triage_level  TEXT,
        created_at    TEXT
    );
    """)
    con.commit()
    con.close()


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def save_patient(data: dict) -> int:
    """Insert a patient from onboarding answers (+ computed risk). Returns new id."""
    row = {c: data.get(c) for c in _PATIENT_COLS}
    # normalize booleans to 0/1
    for k, v in row.items():
        if isinstance(v, bool):
            row[k] = int(v)
    row["created_at"] = row.get("created_at") or _now()
    row.setdefault("status", "active")

    cols = ", ".join(row.keys())
    placeholders = ", ".join("?" for _ in row)
    con = _conn()
    cur = con.execute(f"INSERT INTO patients ({cols}) VALUES ({placeholders})",
                      list(row.values()))
    con.commit()
    pid = cur.lastrowid
    con.close()
    return pid


def get_patient(name_or_id) -> dict | None:
    """Find a patient by integer id or by name (case-insensitive)."""
    con = _conn()
    if isinstance(name_or_id, int) or str(name_or_id).isdigit():
        cur = con.execute("SELECT * FROM patients WHERE id = ?", (int(name_or_id),))
    else:
        cur = con.execute("SELECT * FROM patients WHERE lower(name) = lower(?)",
                          (str(name_or_id),))
    r = cur.fetchone()
    con.close()
    return dict(r) if r else None


def list_patients() -> list[dict]:
    con = _conn()
    rows = con.execute("SELECT * FROM patients ORDER BY created_at").fetchall()
    con.close()
    return [dict(r) for r in rows]


def log_message(patient_id: int, content: str, *, direction: str = "out",
                message_type: str = "chat", channel: str = "app",
                triage_level: str | None = None):
    """Record one message (tip, check-in, triage, or chat turn)."""
    con = _conn()
    con.execute(
        "INSERT INTO messages (patient_id, direction, channel, content, "
        "message_type, triage_level, created_at) VALUES (?,?,?,?,?,?,?)",
        (patient_id, direction, channel, content, message_type, triage_level, _now()),
    )
    con.commit()
    con.close()


def get_history(patient_id: int) -> list[dict]:
    """Return a patient's messages, oldest first."""
    con = _conn()
    rows = con.execute(
        "SELECT * FROM messages WHERE patient_id = ? ORDER BY created_at, id",
        (patient_id,),
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]


def recent_checkins(patient_id: int, limit: int = 5) -> list[str]:
    """Last few check-in questions — lets the generator avoid repeating itself,
    mirroring the backend's _recent_checkins()."""
    con = _conn()
    rows = con.execute(
        "SELECT content FROM messages WHERE patient_id = ? AND message_type = 'checkin' "
        "AND direction = 'out' ORDER BY created_at DESC, id DESC LIMIT ?",
        (patient_id, limit),
    ).fetchall()
    con.close()
    return [r["content"] for r in rows]


if __name__ == "__main__":
    # quick self-test: create db, add a patient, log a message, read it back
    init_db()
    pid = save_patient({
        "name": "TestPatient", "age": 30, "weeks_pregnant_at_signup": 20,
        "parity": 1, "risk_level": "medium", "risk_score": 6,
        "has_hypertension": True, "channel": "sms",
    })
    log_message(pid, "How are you feeling this week?", message_type="checkin")
    log_message(pid, "I have a headache", direction="in", message_type="chat")
    print(f"Created patient id={pid}")
    print("Lookup by name:", get_patient("testpatient")["risk_level"])
    print("History:")
    for m in get_history(pid):
        print(f"  [{m['direction']}] ({m['message_type']}) {m['content']}")
