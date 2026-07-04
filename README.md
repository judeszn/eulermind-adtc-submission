# EulerMind — ADTC 2026 Submission

**Track:** Math & Scientific Reasoning
**Model:** Qwen2.5-Math-1.5B-Instruct · GGUF Q4_K_M · llama.cpp
**What it is:** a math-specialized local model wrapped in a deterministic
verification pipeline — answers in its validated domains are formalized,
solved exactly, and certified by an independently-written checker.
Offline, CPU-only, 1.7 GB peak RAM on the 8 GB reference laptop.

Full technical writeup: [REPORT.md](REPORT.md).
Research evidence archive (experiments, raw reports, reproduction
workflows): [github.com/judeszn/EulerMind](https://github.com/judeszn/EulerMind).

## Run it

```bash
# 1. Fetch the model weights (~1.0 GB, public, idempotent)
bash download_model.sh

# 2. Profile with the official ADTC profiler
pip install "git+https://github.com/Africa-Deep-Tech-Foundation/adtc-profiler.git"
adtc-profiler run --submission . --mode participant \
  --output submission.json --skip-accuracy
```

This repository re-runs the official profiler on every push
(`.github/workflows/profile.yml`) — the checked-in `submission.json`
baseline was produced by that workflow on a clean x86 runner, not on a
development machine.
