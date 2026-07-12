# Changelog

## 2026-07-12 — Badge/trust-key terminology fix
- Re-vendored `app/local_demo.py` from the research repo at commit
  `8f1c395` (import paths only adapted). Copy-only change.
- The "Checks its own answers" badge implied universal coverage while
  the trust key two lines below reserves "Verified" for the certified
  lane only — a judge reading both together could read the 16-families
  refusal message as contradicting the badge instead of demonstrating
  it. Badge now reads "Checks its answers — and says when it can't".
  Deliberately avoids "Verifies" in the badge, since the trust key
  already reserves that word for the certified lane.
- Subtitle tightened: "tells you" / "or is an AI explanation".
- Heuristic explanation: "may contain mistakes" alone became "has not
  been machine-checked — it may contain mistakes", replacing a
  reference to "independently verified" (the certified lane's reserved
  phrase, not applicable to the tutor lane) while keeping the
  mistake-prone admission — `KNOWN_LIMITATIONS.md` states this
  outright, so softening it here would have made the UI inconsistent
  with the repo's own documented limitations.
- Data layer unchanged: `/check` and `/solve` return identical payloads
  before and after. Re-verified: Lagos test prompt still Verified
  30×30/₦345,000, same certificate ID (66D9FFF112F1) as before this
  change.

## 2026-07-12 — UI trust-legibility pass
- Re-vendored `app/local_demo.py` from the research repo at commit
  `e9856c6` (import paths only adapted, per the standing rule).
  Presentation-only change: `app/answer_checker.py` and every
  certified-lane solver/formalizer/checker file are untouched — no
  verification or label-assignment logic changed.
- Fixed a trust-copy bug: the Open badge legend read "solved step by
  step", which implies success for a refusal label. Now "could not
  answer — says so".
- Extended the display-only LaTeX prettifier (Greek letters, arrows/
  relations, blackboard-bold sets, numeric sub/superscripts). Found and
  fixed a real rendering bug in the process: the pre-existing `\pm`
  pattern had no word boundary and mangled `\pmod{n}` into garbage;
  added a dedicated handler.
- Tutor-lane verdict now shows Method/Result as separate lines (same
  underlying `method`/`note` fields the checker already returned — no
  new data), a real generation/verification/total timing breakdown
  (measured via `performance.now()` around the actual fetches, never
  estimated), and an honest "why not verified" explanation listing the
  16 real checker family names (introspected from
  `answer_checker._CHECKERS`, not hand-copied — can't drift from what's
  actually implemented). No LLM topic classification.
- Certified lane now shows a Certificate ID: sha256 of the actual
  certificate dict, first 12 hex digits. Verified deterministic (same
  problem produces the same ID across repeated runs).
- Rejected on review, not implemented: star ratings, invented confidence
  percentages, fabricated certificate IDs, LLM topic classification,
  verification-coverage percentages — none are computable from data the
  system has; inventing them would violate the project's own Law 1 in
  the part of the product that exists to demonstrate it doesn't.
- Re-verified both registered test prompts end-to-end after vendoring
  (Lagos: Verified 30×30/₦345,000; Nairobi: Verified valid assignment),
  plus `benchmark.selftest`, `research.S1_tutor_lane.test_checker`, D1,
  D5 all green.

## 2026-07-08 — Cross-repo consistency audit
- `REPORT.md`: the Peak RSS and CPU-only rows conflated two different CI
  runs' readings (1,700 MB / 15.02 TPS from the model-selection scan,
  run 28683815170) under a single unlabeled "Measured" value, while the
  Benchmarks table's throughput row already correctly distinguished
  scan vs. checked-in-baseline readings. Split the Peak RSS row the same
  way and repointed the Constraints table's headline RAM/TPS figures to
  the checked-in baseline (1,699 MB / 15.68 TPS, run 28691529653 —
  `baseline_submission_ci_28691529653.json`, already committed here).
  No new measurement — this only fixes which existing, already-committed
  number each row cites.
- Corresponding fix on the research-repo side (out of this repo's
  scope, noted for the record): `run_demo.sh` and
  `competition/PRODUCTION_SETUP.md` there cited a stale, unverified
  Hugging Face source (`huggingface.co/Qwen/...`, generic
  `models/qwen2.5-math-1.5b/model.gguf` path) predating this repo's
  CI-verified `download_model.sh` source
  (`huggingface.co/bartowski/...`, `model/Qwen2.5-Math-1.5B-Instruct-Q4_K_M.gguf`).
  Research repo now matches this repo's proven path and URL exactly.

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
