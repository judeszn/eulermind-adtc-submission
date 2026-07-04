# Known limitations — stated, not discovered later

We think a submission is more credible when its boundaries are written
down by its authors. Every limitation below is known by measurement or
by construction, not speculation.

## Certification scope

- **Three problem families are certified:** two-variable linear
  programming (≤2 resource constraints), assignment CSPs (one
  person per slot, forbidden/either-or/conditional constraints), and
  bounded resource-allocation ("knapsack-style") problems. Outside
  these, EulerMind answers with the model and labels the result
  honestly (never "Verified").
- **Two phrasing families per domain are parsed deterministically**
  (benchmark-template phrasing and natural SME prose, e.g. the shipped
  test prompts). The parsers are closed pattern sets that fail closed —
  a phrasing they don't recognize produces an "Open" refusal, not a
  guess. They are not open-ended natural-language understanding.
- **A constraint sentence the CSP prose parser doesn't recognize is not
  captured.** "Verified" always means verified *relative to the
  formalized specification*; formalization fidelity is a separate
  property (measured extensively in the research repo, but not
  guaranteed for arbitrary phrasings).

## Model

- Qwen2.5-Math-1.5B-Instruct (Q4_K_M) scored **68% on GSM8K**
  (flexible-extract, n=50, seed 42) in our x86 CI measurement — strong
  for its size class (its same-family general sibling scored 52% under
  identical settings) but it is a 1.5B model: unassisted answers
  outside the certified domains carry ordinary small-model error rates.
  That is precisely why the certification layer exists.

## Measurements

- TPS/RAM figures were measured on 4-vCPU x86 cloud runners (the
  closest match to the audit environment, which is also a cloud VM) —
  not on a physical ADTC Standard Laptop. The audit's drift tolerances
  (±25% TPS, ±15% RAM) are the relevant yardstick; our checked-in
  baseline sits at ~24% RAM budget utilization, leaving wide margin.
- Thermal behavior on physical laptop hardware is untested (no
  throttling was observed on any CI run; cloud VMs expose no
  temperature sensors).
- GSM8K was sampled at n=50 (the profiler's own default limit) — a
  selection-grade measurement, not a leaderboard-grade one.

## Reproducibility

- The certification pipeline reproduces **byte-identically** across OS
  and CPU architecture (macOS/arm64 → Ubuntu/x86_64) in CI on every
  push — but this is *independent reproduction of the same code*, not
  yet replication by an independent team. The distinction matters and
  we keep it explicit in the research repo's evidence ladder.
