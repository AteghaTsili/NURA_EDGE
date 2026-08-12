#!/usr/bin/env python3
"""
NURA Edge — retrieval + generation (Phase 2, runtime, 100% OFFLINE)

Given a health worker's question, this:
  1. embeds the question with the local MiniLM model
  2. searches the local FAISS index for the most relevant clinician-approved chunks
  3. builds a grounded prompt (retrieved guidance + safety instructions)
  4. asks the local quantized GGUF model (via llama.cpp) to answer

No network is touched at any step. This is the behaviour NURA's cloud brain
(Groq) is replaced by — same job, running locally for near-zero cost.

Usage:
  python rag/nura_edge.py "patient has heavy bleeding at 12 weeks, what do I do?"
"""
import os, sys, json, pathlib, subprocess

os.environ.setdefault("HF_HUB_OFFLINE", "1")      # never reach for the network
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

ROOT       = pathlib.Path(__file__).parent.parent
INDEX_DIR  = ROOT / "rag" / "index"
MODEL_PATH = ROOT / "models" / "nura-q4_k_m.gguf"
LLAMA_CLI  = ROOT / "llama.cpp" / "build" / "bin" / "llama-cli"
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
TOP_K = 4                                         # keep context tight → less RAM, faster

# NURA's safety contract, enforced in the prompt: ground answers in the
# retrieved guidance, never invent, never confirm a loss, escalate danger signs.
SYSTEM = (
    "You are NURA, an offline clinical-decision-support assistant for a community "
    "health worker handling maternal health. Use ONLY the guidance provided in "
    "CONTEXT to answer. If the context does not cover it, say so and advise referral. "
    "Never invent medical facts. Never confirm a pregnancy loss yourself — only a "
    "clinician can. If any danger sign is present, clearly recommend urgent referral. "
    "Answer briefly, calmly, and in plain language the health worker can relay."
)


def retrieve(question: str):
    from sentence_transformers import SentenceTransformer
    import faiss, numpy as np

    embedder = SentenceTransformer(EMBED_MODEL)
    index = faiss.read_index(str(INDEX_DIR / "corpus.faiss"))
    chunks = json.load(open(INDEX_DIR / "chunks.json", encoding="utf-8"))

    qv = embedder.encode([question], normalize_embeddings=True).astype("float32")
    scores, idx = index.search(qv, TOP_K)
    hits = [chunks[i] for i in idx[0] if i >= 0]
    return hits


def build_prompt(question: str, hits):
    context = "\n\n".join(f"[{h['source']}] {h['text']}" for h in hits)
    return (
        f"<|im_start|>system\n{SYSTEM}<|im_end|>\n"
        f"<|im_start|>user\nCONTEXT:\n{context}\n\n"
        f"QUESTION: {question}<|im_end|>\n"
        f"<|im_start|>assistant\n"
    )


def generate(prompt: str):
    # Calls the local quantized model. -n caps output tokens; -c caps context;
    # -t sets CPU threads. All local — no API, no network.
    out = subprocess.run(
    [str(LLAMA_CLI), "-m", str(MODEL_PATH),
     "-p", prompt, "-n", "220", "-c", "2048", "-t", "4",
     "-ngl", "0", "-no-cnv",
     "--temp", "0.3", "--no-display-prompt"],
    capture_output=True, text=True,
)
    return out.stdout.strip()


def answer(question: str):
    hits = retrieve(question)
    prompt = build_prompt(question, hits)
    reply = generate(prompt)
    sources = ", ".join(sorted({h["source"] for h in hits}))
    return reply, sources


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "What are the danger signs after a miscarriage?"
    reply, sources = answer(q)
    print("\n=== NURA Edge ===")
    print(reply)
    print(f"\n[grounded in: {sources}]")
