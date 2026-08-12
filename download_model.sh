#!/usr/bin/env bash
# =============================================================================
# ADTC requires a working download_model.sh that fetches your model artifact.
# The judges run this to obtain your GGUF before evaluating it offline.
#
# Host your quantized model somewhere durable (HuggingFace model repo or a
# release asset) and fetch it here. Do NOT commit the multi-GB GGUF to git.
# =============================================================================
set -euo pipefail

MODEL_URL="${MODEL_URL:-https://huggingface.co/<your-username>/nura-edge/resolve/main/nura-q4_k_m.gguf}"
DEST="models/nura-q4_k_m.gguf"

mkdir -p models
if [ -f "$DEST" ]; then
  echo ">> Model already present: $DEST"; exit 0
fi

echo ">> Downloading quantized model..."
# curl or huggingface-cli both fine; curl keeps deps minimal.
curl -L "$MODEL_URL" -o "$DEST"
echo ">> Saved to $DEST"
