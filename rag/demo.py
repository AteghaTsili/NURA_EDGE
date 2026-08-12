#!/usr/bin/env python3
"""
NURA Edge — End-to-End Demo (fully offline)

Walks through ONE patient's complete journey on a single local machine, with
no cloud and no internet, to show the judges the whole NURA system working:

  1. ONBOARDING   — she answers the intake questionnaire
  2. RISK SCORING — the clinical rubric assigns her a risk level + care cadence
  3. DAILY TIP    — a personalized health tip (local model)
  4. CHECK-IN     — a personalized wellness question (local model)
  5. TRIAGE       — she reports a symptom; NURA triages it, grounded in the
                    clinician-approved corpus (local model + offline RAG)

Every step runs on the quantized GGUF model / deterministic rubric. Zero API calls.

Usage:
  python rag/demo.py           # runs the default patient journey
"""
import os, sys, time, pathlib

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from onboarding import compute_risk, CHECK_IN_CADENCE_DAYS
from services import Patient, generate_daily_tip, generate_checkin
from nura_edge import answer as triage_answer


# ── the patient for this journey ─────────────────────────────────────────────
INTAKE = {
    "name": "Amina",
    "age": 34,
    "weeks_pregnant_at_signup": 30,
    "parity": 3,
    "previous_loss_count": 1,
    "has_hypertension": True,
    "previous_preeclampsia": True,
}

SYMPTOM = "I have a bad headache and my vision is blurry this morning"


# ── pretty printing ──────────────────────────────────────────────────────────
def banner(n, title):
    print("\n" + "═" * 66)
    print(f"  STEP {n} — {title}")
    print("═" * 66)


def slow(text=""):
    print(text)
    time.sleep(0.4)  # small pause so the video reads clearly


def main():
    print("\n" + "█" * 66)
    print("  NURA EDGE — full patient journey, 100% offline")
    print("  No cloud · no internet · running on this laptop")
    print("█" * 66)

    # 1 — ONBOARDING
    banner(1, "ONBOARDING  (patient intake at signup)")
    slow(f"  Name                : {INTAKE['name']}")
    slow(f"  Age                 : {INTAKE['age']}")
    slow(f"  Weeks pregnant      : {INTAKE['weeks_pregnant_at_signup']}")
    slow(f"  Prior births        : {INTAKE['parity']}")
    slow(f"  Previous losses     : {INTAKE['previous_loss_count']}")
    slow(f"  High blood pressure : yes")
    slow(f"  Prior pre-eclampsia : yes")

    # 2 — RISK SCORING
    banner(2, "RISK SCORING  (deterministic clinical rubric, instant)")
    result = compute_risk(INTAKE)
    cadence = CHECK_IN_CADENCE_DAYS[result["level"]]
    freq = {1: "every day", 7: "every week", 14: "every two weeks"}[cadence]
    drivers = ", ".join(f"{k} (+{v})" for k, v in result["breakdown"].items())
    slow(f"  Risk level    : {result['level'].upper()}  (score {result['score']}, rubric {result['rubric_version']})")
    slow(f"  Driven by     : {drivers}")
    slow(f"  Care plan     : NURA will check in on her {freq}.")

    # Build the patient object the services use
    patient = Patient(
        name=INTAKE["name"], week=INTAKE["weeks_pregnant_at_signup"],
        risk_level=result["level"], age=INTAKE["age"], parity=INTAKE["parity"],
        channel="sms", conditions=["hypertension", "history of pre-eclampsia"],
    )

    # 3 — DAILY TIP
    banner(3, "PERSONALIZED DAILY TIP  (local model)")
    slow("  generating...")
    slow(f"\n  \"{generate_daily_tip(patient)}\"")

    # 4 — CHECK-IN
    banner(4, "PERSONALIZED WELLNESS CHECK-IN  (local model)")
    slow("  generating...")
    slow(f"\n  \"{generate_checkin(patient)}\"")

    # 5 — TRIAGE
    banner(5, "SYMPTOM TRIAGE  (local model + offline RAG)")
    slow(f"  Patient says: \"{SYMPTOM}\"")
    slow("  triaging against clinician-approved guidance...")
    reply, sources = triage_answer(SYMPTOM)
    slow(f"\n  NURA: {reply}")
    slow(f"\n  [grounded in: {sources}]")

    print("\n" + "█" * 66)
    print("  Full journey — intake to triage — ran on one laptop, offline.")
    print("█" * 66 + "\n")


if __name__ == "__main__":
    main()
