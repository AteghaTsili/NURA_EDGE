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
MODEL_PATH = ROOT / "models" / "nura-q3_k_m.gguf"
LLAMA_CLI  = ROOT / "llama.cpp" / "build" / "bin" / "llama-cli"
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
TOP_K = 3                                         # keep context tight → less RAM, faster

# NURA's safety contract, enforced in the prompt: ground answers in the
# retrieved guidance, never invent, never confirm a loss, escalate danger signs.
# NURA speaks to whoever is asking — the pregnant woman herself, or a community
# health worker on her behalf — mirroring the production NURA platform.
SYSTEM = (
    "You are NURA, a warm, calm, offline maternal-health assistant working in "
    "sub-Saharan Africa. You answer questions from pregnant and postpartum women "
    "directly, and also from community health workers asking on a woman's behalf. "
    "Speak in simple, reassuring language the reader can act on. "
    "Use ONLY the guidance provided in CONTEXT to answer. If the context does not "
    "cover the question, say so plainly and advise seeing a clinician. "
    "Never invent medical facts and never prescribe medicines or doses. "
    "Never confirm a pregnancy loss yourself — only a clinician can do that. "
    "EMERGENCY RULE: if a danger sign is present (for example heavy bleeding, "
    "severe headache, blurred vision, fits, high fever, severe abdominal pain, no "
    "fetal movement, or a newborn who cannot feed or breathe well), begin your "
    "reply DIRECTLY with the instruction to get to a health facility now — no "
    "preamble — then briefly what to do (do not travel alone if possible, what to "
    "bring). One short reassuring sentence may come at the end, never the start. "
    "Answer briefly and calmly."
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


def _strip_noise(raw: str) -> str:
    """Keep only generated text, drop llama-cli banner/log lines."""
    NOISE = ("██", "▄▄", "▀", "build ", "build:", "model ", "ftype", "modalities",
             "available commands", "/exit", "/regen", "/clear", "/read", "/glob",
             "Loading model", "<|im_start|>", "<|im_end|>", "Exiting", "t/s",
             "llama_", "llm_load", "print_info", "load:", "main:", "system_info",
             "sampler", "generate:", "warning", "Warning", "n_ctx", "n_batch",
             "ggml_", "metal", "Metal", "eval time", "total time", "load time",
             "prompt eval", "NotOpenSSL", "urllib3")
    keep = []
    for ln in raw.splitlines():
        s = ln.strip()
        if not s:
            continue
        if any(t in s for t in NOISE):
            continue
        if s == ">" or s.startswith("> "):
            s = s[1:].strip()
            if not s:
                continue
        keep.append(s)
    return "\n".join(keep).strip()


def generate(prompt: str):
    # Calls the local quantized model. -ngl 0 forces CPU (matches ADTC target);
    # -no-cnv/-st run one prompt and exit. Output is redirected to a file because
    # llama-cli can write straight to the terminal, bypassing subprocess pipes.
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tf:
        tmp_path = tf.name
    cmd = [str(LLAMA_CLI), "-m", str(MODEL_PATH),
           "-p", prompt, "-n", "120", "-c", "2048", "-t", "8",
           "-ngl", "0", "-no-cnv", "-st",
           "--temp", "0.3", "--no-display-prompt"]
    with open(tmp_path, "w") as fout:
        subprocess.run(cmd, stdout=fout, stderr=fout,
                       stdin=subprocess.DEVNULL, text=True)
    with open(tmp_path, "r", errors="ignore") as fin:
        raw = fin.read()
    try:
        os.remove(tmp_path)
    except OSError:
        pass
    return _strip_noise(raw)


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
