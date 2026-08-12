# NURA Edge — ADTC 2026 Report

**Domain:** Healthcare & Medical (clinical Q&A, triage support, patient education)
**Team:** INTELLIKAM · Cameroon

---

## 1. Problem definition

Maternal complications and pregnancy loss are common and often dangerous, yet in
much of Sub-Saharan Africa the warning signs appear in the gaps between clinic
visits, where there is no clinician on hand. Cloud AI that could help is blocked
by the same three walls everywhere: recurring API fees, unreliable connectivity,
and intermittent power. A community health worker (CHW) at a rural post cannot
depend on a system that needs fibre and a monthly subscription to answer a
triage question.

NURA Edge is the offline clinical-decision-support core of the NURA maternal-health
platform. It runs on the CHW's laptop — the hardware clinics already own — and
answers maternal-triage and patient-education questions with no cloud, no API
fees, and no internet during operation.

## 2. Constraints and how we met them

| Constraint | Approach |
|---|---|
| 7 GB RAM ceiling (hard DQ) | 1.5B base model quantized to Q4_K_M (~1 GB weights), tight RAG context — large headroom for a strong efficiency score |
| CPU-only, integrated graphics | llama.cpp CPU inference, 4 threads |
| 100% offline at eval time | Local embedder + local FAISS index + local GGUF; `HF_HUB_OFFLINE=1` |
| llama.cpp + GGUF only | Standard `convert_hf_to_gguf` → `llama-quantize` pipeline |
| Accuracy on a small model | RAG grounding over a clinician-approved corpus, not model recall |

## 3. Design decisions

**Small model + RAG instead of a large or fine-tuned medical model.** With a
1.5B model, factual recall is weak — so we do not rely on it. Clinical facts come
from a local retrieval corpus of clinician-approved guidance; the model's job is
to reason over retrieved context and phrase a safe response. This keeps RAM low,
improves accuracy, and preserves NURA's core safety promise: answers are grounded
in vetted guidance, never invented.

**Retrieval keeps the model's job small.** By supplying the relevant guidance in
the prompt, we let a small model punch above its weight on clinical Q&A while
holding context short — which also protects throughput and RAM.

**Safety by construction.** The system prompt enforces: use only retrieved
context, escalate danger signs to referral, and never confirm a pregnancy loss
(only a clinician can). Every answer reports the corpus sources it was grounded
in, giving an auditable trail.

## 4. Cross-disciplinary integration

Health + information retrieval: an offline RAG layer (local sentence-embedding
model + FAISS vector search) over a maternal-health corpus, grounding the LLM.
This is a load-bearing pairing — remove retrieval and the model loses its
clinical grounding and safety guarantee.

## 5. Tools

- **Base model:** Qwen2.5-1.5B-Instruct (Apache-2.0), chosen for its clean
  permissive license, low RAM footprint (headroom for the efficiency score), and
  strong multilingual/French support; Phi-4-mini (MIT) is the drop-in fallback if
  more reasoning capacity is needed and RAM allows.
- **Quantization/runtime:** llama.cpp, Q4_K_M GGUF.
- **Retrieval:** `all-MiniLM-L6-v2` embeddings + FAISS (flat inner-product).

## 6. Performance (self-reported telemetry)

Fill from your own profiler run on the target laptop:

| Metric | Value |
|---|---|
| Model size on disk | ___ GB |
| Peak RAM (llama.cpp process) | ___ GB (must be < 7) |
| Throughput | ___ tokens/sec |
| Peak core temp | ___ °C (penalty if > 85) |

## 7. The access-economics case

NURA currently routes reasoning through a hosted API. NURA Edge replaces that
call with a local model, removing per-token fees entirely and letting the same
capability run on a $150–$500 laptop a clinic already owns. The offline benchmark
is not the end goal in itself — it is proof that the model is small and cheap
enough to eliminate the hosting and connectivity barriers that keep AI out of
frontline African maternal care.
