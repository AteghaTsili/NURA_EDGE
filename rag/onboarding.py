#!/usr/bin/env python3
"""
NURA Edge — Offline Onboarding & Risk Assessment

Reproduces NURA's patient intake: the questionnaire a woman answers at signup,
and the deterministic clinical rubric that turns her answers into a risk level.
That risk level then drives everything downstream — how often she is checked on,
and how her tips and check-ins are personalized.

The rubric (weights, bands, thresholds) is copied VERBATIM from the production
backend's clinical config (app/core/risk_config.py, rubric v2.0, owned by the
clinical lead). It is pure arithmetic — no LLM, no cloud — so it runs instantly
and identically offline.

This shows the judges the FULL patient journey: intake -> risk -> personalized
care, all on a local machine.

Usage:
  python rag/onboarding.py            # interactive questionnaire
  python rag/onboarding.py demo       # scores three example patients
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))

RUBRIC_VERSION = "v2.0"

# ── rubric v2.0 — verbatim from app/core/risk_config.py ──────────────────────
AGE_WEIGHTS = {"ge40_or_lt16": 4, "35_to_39": 2, "16_to_34": 0}
PREVIOUS_LOSS_WEIGHTS = {"ge3": 5, "2": 3, "1": 2, "0": 0}
QUESTION_WEIGHTS = {
    "has_sickle_cell": 4, "has_hypertension": 3, "has_diabetes": 3,
    "previous_stillbirth": 3, "previous_preeclampsia": 3, "multiple_pregnancy": 3,
    "has_hiv": 2, "has_severe_anaemia": 2, "previous_caesarean": 1,
    "first_trimester": 1, "parity_extreme": 1,
}
RISK_THRESHOLDS = {"high": 9, "medium": 4}
CHECK_IN_CADENCE_DAYS = {"high": 1, "medium": 7, "low": 14}


def _age_band(age):
    if age >= 40 or age < 16:
        return "ge40_or_lt16"
    if 35 <= age <= 39:
        return "35_to_39"
    return "16_to_34"


def _loss_band(count):
    if count >= 3:
        return "ge3"
    if count == 2:
        return "2"
    if count == 1:
        return "1"
    return "0"


def compute_risk(answers: dict) -> dict:
    """Turn questionnaire answers into a risk level (v2 rubric). Pure function."""
    breakdown = {}
    breakdown["age"] = AGE_WEIGHTS[_age_band(answers["age"])]
    breakdown["previous_losses"] = PREVIOUS_LOSS_WEIGHTS[_loss_band(answers["previous_loss_count"])]

    derived = {
        "first_trimester": answers["weeks_pregnant_at_signup"] < 13,
        "parity_extreme": answers["parity"] == 0 or answers["parity"] >= 5,
    }
    for key, weight in QUESTION_WEIGHTS.items():
        present = derived[key] if key in derived else bool(answers.get(key, False))
        breakdown[key] = weight if present else 0

    score = sum(breakdown.values())
    if score >= RISK_THRESHOLDS["high"]:
        level = "high"
    elif score >= RISK_THRESHOLDS["medium"]:
        level = "medium"
    else:
        level = "low"

    return {"score": score, "level": level,
            "rubric_version": RUBRIC_VERSION,
            "breakdown": {k: v for k, v in breakdown.items() if v > 0}}


# ── the intake questionnaire (mirrors the backend's onboarding fields) ───────
# Each item: (key, question, type). type: "int" | "yesno"
QUESTIONS = [
    ("name", "Patient name", "text"),
    ("age", "Age (years)", "int"),
    ("weeks_pregnant_at_signup", "How many weeks pregnant are you now", "int"),
    ("parity", "How many times have you given birth before (parity)", "int"),
    ("previous_loss_count", "How many previous pregnancy losses have you had", "int"),
    ("previous_stillbirth", "Any previous stillbirth", "yesno"),
    ("previous_caesarean", "Any previous caesarean section", "yesno"),
    ("previous_preeclampsia", "Any previous pre-eclampsia", "yesno"),
    ("has_hypertension", "Do you have high blood pressure (hypertension)", "yesno"),
    ("has_diabetes", "Do you have diabetes", "yesno"),
    ("has_sickle_cell", "Do you have sickle cell disease", "yesno"),
    ("has_hiv", "Are you HIV positive", "yesno"),
    ("has_severe_anaemia", "Do you have severe anaemia", "yesno"),
    ("multiple_pregnancy", "Are you expecting twins or more", "yesno"),
]


def _explain(result: dict) -> str:
    level = result["level"]
    cadence = CHECK_IN_CADENCE_DAYS[level]
    freq = {1: "every day", 7: "every week", 14: "every two weeks"}[cadence]
    drivers = ", ".join(f"{k} (+{v})" for k, v in result["breakdown"].items()) or "no risk factors"
    return (f"Risk level: {level.upper()}  (score {result['score']}, rubric {result['rubric_version']})\n"
            f"  Contributing factors: {drivers}\n"
            f"  NURA will check in on her {freq}.")


def _interactive():
    print("\n=== NURA Edge — Patient Onboarding (offline) ===\n")
    answers = {}
    for key, q, typ in QUESTIONS:
        while True:
            raw = input(f"{q}? ").strip()
            if typ == "text":
                answers[key] = raw or "Patient"; break
            if typ == "int":
                try:
                    answers[key] = int(raw); break
                except ValueError:
                    print("  Please enter a number.")
            if typ == "yesno":
                if raw.lower() in ("y", "yes", "oui"):
                    answers[key] = True; break
                if raw.lower() in ("n", "no", "non", ""):
                    answers[key] = False; break
                print("  Please answer yes or no.")

    result = compute_risk(answers)

    # Persist the patient + risk to the local database
    import db as _db
    _db.init_db()
    patient_data = dict(answers)
    patient_data["risk_level"] = result["level"]
    patient_data["risk_score"] = result["score"]
    pid = _db.save_patient(patient_data)

    print("\n" + "-" * 60)
    print(f"Patient: {answers['name']}   (saved to database, id={pid})")
    print(_explain(result))
    print("-" * 60 + "\n")


# ── demo patients ────────────────────────────────────────────────────────────
DEMO = [
    ("Amina (34, hypertension, prior pre-eclampsia)", {
        "name": "Amina", "age": 34, "weeks_pregnant_at_signup": 30, "parity": 3,
        "previous_loss_count": 0, "has_hypertension": True, "previous_preeclampsia": True}),
    ("Grace (24, first pregnancy, healthy)", {
        "name": "Grace", "age": 24, "weeks_pregnant_at_signup": 12, "parity": 0,
        "previous_loss_count": 0}),
    ("Fatou (41, sickle cell, 2 prior losses, twins)", {
        "name": "Fatou", "age": 41, "weeks_pregnant_at_signup": 20, "parity": 1,
        "previous_loss_count": 2, "has_sickle_cell": True, "multiple_pregnancy": True}),
]


def _demo():
    print("\n" + "=" * 60)
    print("  NURA Edge — Onboarding & Risk Scoring Demo (offline)")
    print("=" * 60)
    for label, answers in DEMO:
        result = compute_risk(answers)
        print(f"\n{label}")
        print(_explain(result))
    print("\n" + "=" * 60)
    print("  Deterministic clinical rubric — instant, no model, no cloud.")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "demo":
        _demo()
    else:
        _interactive()
