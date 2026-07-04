# EulerMind — ADTC 2026 Submission

**Track:** Math & Scientific Reasoning ·
**Model:** Qwen2.5-Math-1.5B-Instruct (GGUF Q4_K_M, llama.cpp) ·
**Peak RAM:** 1.7 GB measured · **Fully offline** · CPU-only

A math-specialized local model wrapped in a deterministic verification
pipeline. For production-planning, assignment, and resource-allocation
problems, the language model only *reads* the problem — an exact solver
computes the answer, a verifier certifies it, and a **second,
independently-written checker re-proves it before anything is labeled
"Verified."** Measured across three domains: 192/192 certificates
agreed, **0% false certification**.

## Try it in 60 seconds (no installs, no internet, no GPU)

```bash
python3 -m app.local_demo        # → open http://localhost:7860
```

Pure Python standard library. Click **"Lagos workshop (test prompt 1)"**
— one of this submission's registered test prompts — and press Solve.
You'll see all four pipeline stages certify and a Verified answer
(30 chairs, 30 tables, ₦345,000). Then paste any out-of-scope question:
the label becomes **Open**, because EulerMind never fabricates
certainty it hasn't earned.

## Run the official profiler

```bash
bash download_model.sh           # fetches the 1.0 GB model weights (public URL)
pip install "git+https://github.com/Africa-Deep-Tech-Foundation/adtc-profiler.git"
adtc-profiler run --submission . --mode participant \
  --output submission.json --skip-accuracy
```

The checked-in [`baseline_submission_ci_28691529653.json`](baseline_submission_ci_28691529653.json)
was produced by this repo's own CI workflow on a clean x86 runner —
[`.github/workflows/profile.yml`](.github/workflows/profile.yml) re-runs
the official profiler on every push.

## What the trust labels mean

| Label | Earned by | You should |
|---|---|---|
| **Verified** | Exact solver + certificate + a second independently-written checker all agree | Act on it |
| **Derived** | Computed, but certification did not fully succeed | Treat as a draft |
| **Heuristic** | Model-generated approximation | Double-check |
| **Open** | Outside the certified domains, or unverifiable | EulerMind is telling you it doesn't know |

The label is assigned by running code — never asserted by the model.

## The pipeline

```
problem text
   → Formalizer   (deterministic parser — zero hallucination surface)
   → Solver       (exact algorithm: vertex enumeration / exhaustive search)
   → Verifier     (issues a re-checkable certificate)
   → Independent  (separately-written checker; for LP it uses a DIFFERENT
     checker       theorem — duality — than the solver. Both must agree.)
   → answer + trust label
```

`app/` is a verbatim copy of the certified pipeline from the
[research repository](https://github.com/judeszn/EulerMind) (import
paths only adapted) — where every claim above has a registered
experiment, raw reports, and CI reproduction behind it, including
byte-identical reproduction across OS and CPU architecture.

## Honest scope

Certification covers three problem families (two-variable LP,
assignment CSPs, bounded resource allocation) in two phrasing families.
Everything else gets a model answer with an honest non-Verified label.
Full details, including what we tested and what we didn't:
[KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md).

One research result we kept rather than buried: our original hypothesis
(verifier-*guided retry* beats blind retry) was **rejected by our own
pre-registered decision rule**. The certification architecture is what
the evidence actually supports.

## Documentation

- [REPORT.md](REPORT.md) — the ADTC technical report (every number cites its CI run)
- [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) — scope, honestly
- [CHANGELOG.md](CHANGELOG.md) — release history
- [Research repository](https://github.com/judeszn/EulerMind) — experiments, evidence, reproduction workflows

## License

MIT — see [LICENSE](LICENSE).
