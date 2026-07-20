#!/usr/bin/env bash
# EulerMind — one-command competition stack (offline, llama.cpp + GGUF).
#
#   ./run_demo.sh            start model server + demo UI
#   ./run_demo.sh check      preflight only (no servers started)
#
# Judge-facing promise: no cloud, no internet, no Ollama. Everything runs
# from the GGUF under model/ through llama-server on 127.0.0.1.

set -euo pipefail

MODEL_DIR="model"
MODEL_GGUF="$MODEL_DIR/Qwen2.5-Math-1.5B-Instruct-Q4_K_M.gguf"
LLAMA_PORT=8080
APP_PORT=7860
CTX=4096

say()  { printf '\033[1m%s\033[0m\n' "$*"; }
fail() { printf '\033[31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- preflight
command -v llama-server >/dev/null 2>&1 \
  || fail "llama-server not found. Install llama.cpp first:
  macOS:    brew install llama.cpp
  Linux:    brew install llama.cpp   (Homebrew works on Linux too), OR:
              sudo apt install -y build-essential cmake git   # Debian/Ubuntu
              git clone https://github.com/ggml-org/llama.cpp
              cmake -B llama.cpp/build -S llama.cpp -DCMAKE_BUILD_TYPE=Release
              cmake --build llama.cpp/build --config Release -j
              export PATH=\"\$PWD/llama.cpp/build/bin:\$PATH\"
  Windows:  install WSL2 and follow the Linux steps above (this also
            matches the x86 Linux environment the ADTC profiler audits
            on), OR download a prebuilt llama-*-bin-win-*.zip from
            https://github.com/ggml-org/llama.cpp/releases and add its
            folder to PATH
  Then re-run: ./run_demo.sh"

command -v python3 >/dev/null 2>&1 || fail "python3 not found"

[ -f "$MODEL_GGUF" ] \
  || fail "model not found at $MODEL_GGUF
  Download it (one-time, ~1.0 GB):  ./download_model.sh"

say "preflight OK: llama-server + python3 + $(du -h "$MODEL_GGUF" | cut -f1) GGUF"
[ "${1:-}" = "check" ] && exit 0

# ------------------------------------------------------------- model server
if curl -s "http://127.0.0.1:$LLAMA_PORT/v1/models" >/dev/null 2>&1; then
  say "llama-server already running on :$LLAMA_PORT — reusing it"
else
  say "starting llama-server (CPU-only, fully local) on :$LLAMA_PORT …"
  llama-server -m "$MODEL_GGUF" --port "$LLAMA_PORT" -c "$CTX" \
    --host 127.0.0.1 >/tmp/eulermind-llama.log 2>&1 &
  LLAMA_PID=$!
  trap 'kill "$LLAMA_PID" 2>/dev/null || true' EXIT
  # wait for readiness (first load reads the whole GGUF from disk)
  for i in $(seq 1 120); do
    curl -s "http://127.0.0.1:$LLAMA_PORT/v1/models" >/dev/null 2>&1 && break
    [ "$i" = 120 ] && fail "llama-server did not become ready — see /tmp/eulermind-llama.log"
    sleep 1
  done
  say "model ready ($(grep -c . /tmp/eulermind-llama.log 2>/dev/null || echo '?') log lines, /tmp/eulermind-llama.log)"
fi

# ----------------------------------------------------------------- demo UI
say "starting EulerMind demo UI on http://localhost:$APP_PORT …"
say "(disconnect Wi-Fi now — everything keeps working)"
exec python3 -m app.local_demo
