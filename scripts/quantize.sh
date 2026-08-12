#!/usr/bin/env bash
# =============================================================================
# NURA Edge — Model quantization
# Turns a full-precision base model into a small Q4_K_M GGUF that runs on the
# ADTC Standard Laptop (7 GB RAM ceiling, CPU-only).
#
# This is a DEVELOPMENT-time script. You run it ONCE on your dev machine to
# produce the small model file. Internet is used here only to fetch the base
# model and build llama.cpp — the FINAL model then runs fully offline.
#
# Run from repo root:  bash scripts/quantize.sh
# =============================================================================
set -euo pipefail

# ---- config -----------------------------------------------------------------
BASE_MODEL_REPO="Qwen/Qwen2.5-1.5B-Instruct" # primary pick: Apache-2.0, lightest RAM (swap for Phi-4-mini if needed)
BASE_DIR="models/base"                        # where the full model is downloaded
GGUF_F16="models/nura-f16.gguf"               # intermediate full-precision GGUF
GGUF_Q4="models/nura-q4_k_m.gguf"             # FINAL quantized model → this is the deliverable
QUANT_TYPE="Q4_K_M"                           # the sweet-spot quantization level
LLAMA_CPP_DIR="llama.cpp"

# ---- 1. build llama.cpp (has both the converter and the quantizer) ----------
if [ ! -d "$LLAMA_CPP_DIR" ]; then
  echo ">> Cloning llama.cpp..."
  git clone https://github.com/ggml-org/llama.cpp "$LLAMA_CPP_DIR"
fi
echo ">> Building llama.cpp..."
cmake -S "$LLAMA_CPP_DIR" -B "$LLAMA_CPP_DIR/build" -DGGML_NATIVE=ON >/dev/null
cmake --build "$LLAMA_CPP_DIR/build" --config Release -j >/dev/null

# ---- 2. download the full-precision base model ------------------------------
# The base model ships as 16-bit weights (~6 GB for a 3B model). Too big to run
# under our RAM budget as-is — that's exactly what quantization fixes below.
if [ ! -d "$BASE_DIR" ]; then
  echo ">> Downloading base model: $BASE_MODEL_REPO ..."
  pip install -q "huggingface_hub[cli]"
  huggingface-cli download "$BASE_MODEL_REPO" \
    --local-dir "$BASE_DIR" --exclude "*.pth" "original/*"
fi

# ---- 3. convert HF weights → GGUF (still full precision, F16) ----------------
# GGUF is the file format llama.cpp uses. This step just re-packages the model;
# it does NOT shrink it yet.
echo ">> Converting to F16 GGUF..."
python3 "$LLAMA_CPP_DIR/convert_hf_to_gguf.py" "$BASE_DIR" \
  --outfile "$GGUF_F16" --outtype f16

# ---- 4. THE QUANTIZATION STEP -----------------------------------------------
# This is the single command that answers "how do you quantize a model".
# It rewrites every weight from 16-bit → 4-bit (Q4_K_M), shrinking the file
# ~4x and cutting RAM use enough to fit under the 7 GB ADTC ceiling.
echo ">> Quantizing  $GGUF_F16  →  $GGUF_Q4  ($QUANT_TYPE)"
"$LLAMA_CPP_DIR/build/bin/llama-quantize" "$GGUF_F16" "$GGUF_Q4" "$QUANT_TYPE"

# ---- 5. report sizes --------------------------------------------------------
echo ""
echo ">> Done. Size comparison:"
du -h "$GGUF_F16" "$GGUF_Q4" 2>/dev/null | sed 's/^/     /'
echo ""
echo ">> FINAL deliverable model:  $GGUF_Q4"
echo ">> You can now delete the F16 intermediate to save space:  rm $GGUF_F16"
