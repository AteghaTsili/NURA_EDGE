#!/usr/bin/env python3
"""
NURA Edge — End-to-End Demo (fully offline, database-backed)

Walks through ONE patient's complete journey on a single local machine, with
no cloud and no internet, showing the whole NURA system working AND persisting:

  1. ONBOARDING   — she answers intake; the record is SAVED to the local database
  2. RISK SCORING — the clinical rubric assigns her a risk level + care cadence
  3. DAILY TIP    — a personalized health tip (local model), logged to her history
  4. CHECK-IN     — a personalized wellness question (local model), logged
  5. TRIAGE       — she reports a symptom; NURA triages it against the
                    clinician-approved corpus (local model + offline RAG), logged
  6. HISTORY      — her full stored record is read back from the database

Everything runs on the quantized GGUF model / deterministic rubric / local
SQLite file. Zero API calls, zero network.

Usage:
  python rag/demo.py
"""
import os, sys, time, pathlib

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from onboarding import compute_risk, CHECK_IN_CADENCE_DAYS
from services import Patient, generate_daily_tip, generate_checkin, _patient_from_db
from nura_edge import answer as triage_answer
import db


INTAKE = {
    "name": "Amina",
    "age": 34,
    "weeks_pregnant_at_signup": 30,
    "parity": 3,
    "previous_loss_count": 1,
    "has_hypertension": True,
    "previous_preeclampsia": True,
    "channel": "sms",
}

SYMPTOM = "I have a bad headache and my vision is blurry this morning"


def banner(n, title):
    print("\n" + "=" * 66)
    print(f"  STEP {n} - {title}")
    print("=" * 66)


def slow(text=""):
    print(text)
    time.sleep(0.4)


def main():
    print("\n" + "#" * 66)
    print("  NURA EDGE - full patient journey, 100% offline")
    print("  No cloud - no internet - local model + local database")
    print("#" * 66)

    db.init_db()

    banner(1, "ONBOARDING  (intake at signup - saved to the database)")
    for label, key in [("Name", "name"), ("Age", "age"),
                       ("Weeks pregnant", "weeks_pregnant_at_signup"),
                       ("Prior births", "parity"),
                       ("Previous losses", "previous_loss_count")]:
        slow(f"  {label:<20}: {INTAKE[key]}")
    slow(f"  {'High blood pressure':<20}: yes")
    slow(f"  {'Prior pre-eclampsia':<20}: yes")

    banner(2, "RISK SCORING  (deterministic clinical rubric, instant)")
    result = compute_risk(INTAKE)
    cadence = CHECK_IN_CADENCE_DAYS[result["level"]]
    freq = {1: "every day", 7: "every week", 14: "every two weeks"}[cadence]
    drivers = ", ".join(f"{k} (+{v})" for k, v in result["breakdown"].items())
    slow(f"  Risk level : {result['level'].upper()}  (score {result['score']}, rubric {result['rubric_version']})")
    slow(f"  Driven by  : {drivers}")
    slow(f"  Care plan  : NURA will check in on her {freq}.")

    patient_data = dict(INTAKE)
    patient_data["risk_level"] = result["level"]
    patient_data["risk_score"] = result["score"]
    pid = db.save_patient(patient_data)
    slow(f"  Saved to database as patient id={pid}.")

    patient = _patient_from_db(db.get_patient(pid))

    banner(3, "PERSONALIZED DAILY TIP  (local model)")
    slow("  generating...")
    tip = generate_daily_tip(patient)
    db.log_message(pid, tip, message_type="tip", channel=patient.channel)
    slow(f"\n  \"{tip}\"")

    banner(4, "PERSONALIZED WELLNESS CHECK-IN  (local model)")
    slow("  generating...")
    checkin = generate_checkin(patient)
    db.log_message(pid, checkin, message_type="checkin", channel=patient.channel)
    slow(f"\n  \"{checkin}\"")

    banner(5, "SYMPTOM TRIAGE  (local model + offline RAG)")
    slow(f"  Patient says: \"{SYMPTOM}\"")
    db.log_message(pid, SYMPTOM, direction="in", message_type="chat", channel=patient.channel)
    slow("  triaging against clinician-approved guidance...")
    reply, sources = triage_answer(SYMPTOM)
    db.log_message(pid, reply, message_type="triage", channel=patient.channel)
    slow(f"\n  NURA: {reply}")
    slow(f"\n  [grounded in: {sources}]")

    banner(6, "STORED HISTORY  (read back from the local database)")
    for m in db.get_history(pid):
        who = "patient" if m["direction"] == "in" else "NURA"
        slow(f"  [{m['message_type']:<7}] {who}: {m['content'][:70]}")

    print("\n" + "#" * 66)
    print("  Full journey - intake to triage - ran and persisted on one laptop.")
    print("  Close and reopen: Amina and her history are still here. Offline.")
    print("#" * 66 + "\n")


if __name__ == "__main__":
    main()
