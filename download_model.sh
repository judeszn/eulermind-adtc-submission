#!/usr/bin/env bash
# Download the submission model weights (Qwen2.5-Math-1.5B-Instruct, GGUF Q4_K_M).
#
# Rules (per the ADTC 2026 template):
#   - Idempotent (safe to run multiple times).
#   - No credentials required (public URL).
#   - Output path matches `_runtime.model_path` in metadata.json.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODEL_DIR="$HERE/model"
MODEL_FILE="$MODEL_DIR/Qwen2.5-Math-1.5B-Instruct-Q4_K_M.gguf"

MODEL_URL="https://huggingface.co/bartowski/Qwen2.5-Math-1.5B-Instruct-GGUF/resolve/main/Qwen2.5-Math-1.5B-Instruct-Q4_K_M.gguf"

mkdir -p "$MODEL_DIR"

if [[ -f "$MODEL_FILE" ]]; then
  echo "model already present at $MODEL_FILE - skipping download"
  exit 0
fi

echo "downloading $MODEL_URL -> $MODEL_FILE (~1.0 GB)..."

if command -v curl > /dev/null 2>&1; then
  curl -L --fail --progress-bar -o "$MODEL_FILE.partial" "$MODEL_URL"
elif command -v wget > /dev/null 2>&1; then
  wget --show-progress -O "$MODEL_FILE.partial" "$MODEL_URL"
else
  echo "error: neither curl nor wget found" >&2
  exit 1
fi

mv "$MODEL_FILE.partial" "$MODEL_FILE"
echo "done: $MODEL_FILE"
