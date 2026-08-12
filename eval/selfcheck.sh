#!/usr/bin/env bash
# =============================================================================
# NURA Edge — pre-submission self-check
# Runs the official ADTC profiler against the quantized model so you catch RAM
# / thermal / throughput problems BEFORE submitting. Run with WiFi OFF to prove
# the offline path works in the judges' sandbox.
# =============================================================================
set -euo pipefail

MODEL="models/nura-q4_k_m.gguf"
PROFILER_DIR="adtc-profiler"

if [ ! -f "$MODEL" ]; then
  echo "!! Model not found. Run scripts/quantize.sh first."; exit 1
fi

if [ ! -d "$PROFILER_DIR" ]; then
  echo ">> Cloning ADTC profiler..."
  git clone https://github.com/Africa-Deep-Tech-Foundation/adtc-profiler "$PROFILER_DIR"
fi

echo ">> Model size on disk:"
du -h "$MODEL" | sed 's/^/     /'

echo ""
echo ">> Running ADTC profiler (throughput / peak RAM / thermal)..."
echo ">> Reminder: peak RAM must stay UNDER 7 GB or Stotal = 0."
# Follow the profiler's README for exact invocation; typically:
#   python adtc-profiler/profile.py --model models/nura-q4_k_m.gguf
( cd "$PROFILER_DIR" && python3 profile.py --model "../$MODEL" ) || \
  echo "!! Check profiler README for the exact command/flags."

echo ""
echo ">> Turn WiFi OFF and run rag/nura_edge.py once to confirm the full"
echo ">> offline path (embedder + FAISS + llama.cpp) works with no network."
