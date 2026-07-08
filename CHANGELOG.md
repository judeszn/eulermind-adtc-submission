# Changelog

## 2026-07-08 — Gate 1 sync audit (no code changes)
- Audited this repository file-by-file against the research repo's
  finalized Gate 1 state ([judeszn/EulerMind@v1.0-gate1](https://github.com/judeszn/EulerMind/tree/v1.0-gate1), tag only, no formal release).
- Result: no drift found. All vendored `app/*.py` files are pinned to
  commits (`d44a160`, `8521038`) that carry zero content changes up to
  the Gate 1 tag — verified by diffing each pinned commit against
  `v1.0-gate1` in the research repo (`git log <pin>..v1.0-gate1 --
  <path>`, empty for every vendored file). `LICENSE` is byte-identical.
  README/REPORT/KNOWN_LIMITATIONS numbers (192/192 certificates, 1.7 GB
  peak RAM, 15.68/15.02 TPS, 12/20 real-WAEC) already match the
  research repo's finalized figures.
- The Gate 1 lockdown in the research repo was documentation-only
  (README rewrite, LICENSE addition, competition/ doc consolidation) —
  nothing in that pass touched code this repository vendors.
- No file changes required in this repository beyond this entry.

## 2026-07-05 — Tutor lane synchronized
- Vendored the tutor lane from the research repo at commit d44a160:
  local-model streaming (llama.cpp), deterministic answer checker
  (16 question families, fail-closed), trust labels with plain-English
  rationale, truncation guard, one-question-at-a-time gate.
- `run_demo.sh`: one command starts llama-server + the demo UI.
- Measured on 20 real WAEC past-paper questions (user-sourced, live
  model): 12/20 machine-checked (Derived), 8 honest Heuristics,
  0 false verifications, 0 truncations.
- Certified lane unchanged: both registered test prompts still certify
  (Lagos LP re-verified end-to-end during this sync).

## 2026-07-04 — Release candidate
- Vendored the certified pipeline (`app/`) so the demo runs from this
  repository with one command and zero dependencies.
- Both registered test prompts certify end-to-end in the local demo
  (Lagos LP: Verified, 30+30, ₦345,000; Nairobi CSP: Verified
  assignment) — regression-tested in the research repo.
- Added LICENSE (MIT), KNOWN_LIMITATIONS.md, release-quality README.

## 2026-07-04 — Gate 1 baseline
- Official adtc-profiler green on this repo's own CI (clean x86 runner):
  15.68 tok/s, 1,699 MB peak RSS, fraud-check pass, no throttling.
- Baseline archived: `baseline_submission_ci_28691529653.json`.

## 2026-07-04 — Initial submission repository
- Template-conformant structure; metadata.json (model:
  Qwen2.5-Math-1.5B-Instruct Q4_K_M, selected by measured benchmark);
  download_model.sh; REPORT.md with run-ID-cited numbers.
