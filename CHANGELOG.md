# Changelog

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
