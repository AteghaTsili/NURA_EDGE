# NURA Edge

**An offline maternal-health assistant for community health workers — Africa Deep Tech Challenge 2026 (Healthcare & Medical).**

NURA Edge runs a small quantized language model plus a local RAG pipeline and a
local database entirely on an 8 GB laptop, with **no cloud, no API fees, and no
internet at runtime**. It is the offline core of the NURA maternal-health
platform: it onboards a patient, scores her clinical risk, sends personalized
daily tips and wellness check-ins, and triages her symptoms against
clinician-approved guidance — all on hardware a clinic already owns.

---

## Why this exists

Cloud AI is locked out of frontline African maternal care by three walls at
once: recurring API fees, unreliable connectivity, and intermittent power. NURA
Edge removes all three by shrinking the model small enough to run locally. The
offline benchmark is not the goal in itself — it is proof that the model is
cheap enough to eliminate the hosting and connectivity barriers that keep AI
away from the women who most need it.

---

## What it does (the full patient journey, offline)

| Stage | What happens | How |
|---|---|---|
| **1. Onboarding** | The health worker enters the patient's intake answers | Questionnaire |
| **2. Risk scoring** | A clinical rubric assigns her a risk level and care cadence | Deterministic (no LLM) |
| **3. Daily tip** | A personalized health tip tied to her week and conditions | Local LLM |
| **4. Check-in** | A specific wellness question, never generic | Local LLM |
| **5. Triage** | She reports a symptom; NURA triages it and flags danger signs | Local LLM + offline RAG |

Every patient and every message is stored in a local SQLite database, so a
patient onboarded once is remembered and her care history accumulates — exactly
like the production platform, but in a local file instead of PostgreSQL.

---

## Architecture

```
Onboarding answers ─► Risk rubric (pure arithmetic) ─► risk level + cadence
                                                          │
Patient + messages ◄──────── SQLite (nura_edge.db) ◄──────┘
                                                          │
Symptom question ─► local embedder (MiniLM) ─► FAISS search over
                    clinician-approved corpus ─► grounded prompt ─►
                    quantized GGUF model (llama.cpp, CPU) ─► triage answer
```

Nothing reaches the network. The only online step is one-time setup (downloading
the base model and the embedder), after which everything runs offline.

---

## The model

- **Base:** Qwen2.5-1.5B-Instruct (Apache-2.0)
- **Quantization:** Q4_K_M via llama.cpp — **945 MB** on disk
- **Runtime:** llama.cpp, CPU-only (`-ngl 0`) to match the ADTC target hardware
- **RAM:** well under the 7 GB ADTC ceiling (large efficiency headroom)

A 1.5B model is weak on factual recall, so NURA Edge does not rely on it for
clinical facts. Triage answers are **grounded by RAG** in a clinician-approved
corpus; the model's job is to reason over retrieved guidance and phrase a safe
reply. Format rules the small model sometimes misses (no exclamation marks, no
preambles) are enforced deterministically in code, not left to the model —
mirroring the production backend's philosophy of enforcing safety-critical
behaviour in code rather than trusting the LLM.

---

## Quickstart

### 1. Setup (once, with internet)
```bash
pip install -r requirements.txt
pip install -U "huggingface_hub[cli]"
```

### 2. Produce the model (download → convert → quantize to Q4_K_M)
```bash
bash scripts/quantize.sh
```

### 3. Build the retrieval index (run once online so the embedder caches)
```bash
python rag/ingest.py
```

### 4. Run the full patient journey (offline)
```bash
python rag/onboarding.py            # onboard a patient → saved to the database
python rag/services.py tip Amina    # personalized daily tip (looks her up)
python rag/services.py checkin Amina# personalized wellness check-in
python rag/nura_edge.py "I have a bad headache and blurry vision"   # triage
python rag/demo.py                  # the whole journey, one command (for the video)
```

### 5. Pre-submission profiling (run with WiFi OFF)
```bash
bash eval/selfcheck.sh
```

---

## Offline proof

Turn WiFi **off**, then run any of the commands in step 4. They still work —
the model, the embedder, the database, and the retrieval index are all local.
`HF_HUB_OFFLINE=1` is set in the runtime scripts; run `rag/ingest.py` once online
first so the embedder is cached before going offline.

---

## Repo layout

```
corpus/                clinician-approved maternal-health guidance (.md)
rag/onboarding.py      intake questionnaire + clinical risk scoring
rag/services.py        personalized daily tips + wellness check-ins
rag/services_prompts.py real service prompts (verbatim from the NURA backend)
rag/nura_edge.py       offline symptom triage (local model + RAG)
rag/db.py              local SQLite datastore (patients + message history)
rag/demo.py            full end-to-end patient journey (video script)
rag/ingest.py          builds the local FAISS index from the corpus
scripts/quantize.sh    base model → Q4_K_M GGUF
eval/selfcheck.sh      ADTC profiler self-check
eval/test_prompts.md   the two required ADTC test prompts
download_model.sh      fetches the hosted GGUF (for judges)
metadata.json          ADTC submission metadata
REPORT.md              the graded report
```

---

## Relationship to the full NURA platform

NURA Edge is the offline brain of NURA, a production FastAPI maternal-health
platform (patient management, SMS + app channels, clinician takeover, hospital
alerts, scheduled care). The platform's brain is normally a hosted LLM; NURA
Edge is that same brain, quantized to run locally. The onboarding rubric and the
tip/check-in prompts here are taken **verbatim from the production backend**, so
this offline build is a faithful distillation of the real system — not a
re-imagination.

---

## Notes

- The multi-GB base model and the `.gguf` are **not** committed — the model is
  fetched via `download_model.sh`.
- Populate `corpus/` with **clinician-approved** content only; NURA's safety
  promise depends on grounding in vetted guidance.
- NURA never confirms a pregnancy loss on its own and always escalates danger
  signs to referral — a clinician has the final say.
