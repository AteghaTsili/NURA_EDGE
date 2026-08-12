#!/usr/bin/env python3
"""
NURA Edge — RAG ingestion (Phase 1, run once during development)

Reads every clinician-approved document in corpus/, splits it into chunks,
embeds each chunk with a SMALL LOCAL embedding model, and saves a FAISS index
+ the chunk texts to disk. That index file ships inside the repo and is read
at runtime with ZERO network access.

The embedding model downloads from HuggingFace the FIRST time only. For a truly
offline submission, pre-download it (see rag/README) and set HF_HUB_OFFLINE=1.

Usage:  python rag/ingest.py
"""
import os, json, glob, pathlib
import numpy as np

# Local, CPU-friendly embedding model (~90 MB). NOT the LLM — this only turns
# text into vectors so we can search by meaning. It does not count against the
# ADTC model RAM budget (only the llama.cpp process is profiled).
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

CORPUS_DIR = pathlib.Path(__file__).parent.parent / "corpus"
INDEX_DIR  = pathlib.Path(__file__).parent / "index"
INDEX_DIR.mkdir(exist_ok=True)

CHUNK_WORDS   = 220     # target words per chunk
CHUNK_OVERLAP = 40      # words shared between neighbouring chunks (keeps context)


def chunk_text(text: str):
    """Split text into overlapping word windows."""
    words = text.split()
    if not words:
        return []
    chunks, i = [], 0
    step = CHUNK_WORDS - CHUNK_OVERLAP
    while i < len(words):
        chunks.append(" ".join(words[i : i + CHUNK_WORDS]))
        i += step
    return chunks


def load_corpus():
    """Read every .txt / .md file in corpus/ into (source, chunk) records."""
    records = []
    files = glob.glob(str(CORPUS_DIR / "**" / "*.*"), recursive=True)
    for fp in files:
        if not fp.endswith((".txt", ".md")):
            continue
        source = os.path.basename(fp)
        with open(fp, "r", encoding="utf-8") as f:
            for c in chunk_text(f.read()):
                records.append({"source": source, "text": c})
    return records


def main():
    from sentence_transformers import SentenceTransformer
    import faiss

    print(f">> Loading embedding model: {EMBED_MODEL}")
    embedder = SentenceTransformer(EMBED_MODEL)

    print(f">> Reading corpus from {CORPUS_DIR}")
    records = load_corpus()
    if not records:
        print("!! No corpus files found. Add .txt/.md files to corpus/ first.")
        return
    print(f">> {len(records)} chunks from corpus")

    texts = [r["text"] for r in records]
    print(">> Embedding chunks (CPU)...")
    vecs = embedder.encode(
        texts, batch_size=32, show_progress_bar=True, normalize_embeddings=True
    ).astype("float32")

    # Cosine similarity via inner product on normalized vectors.
    index = faiss.IndexFlatIP(vecs.shape[1])
    index.add(vecs)

    faiss.write_index(index, str(INDEX_DIR / "corpus.faiss"))
    with open(INDEX_DIR / "chunks.json", "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f">> Saved index ({index.ntotal} vectors) to {INDEX_DIR}")


if __name__ == "__main__":
    main()
