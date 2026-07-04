# EulerMind — ADTC 2026 Technical Report

**Track:** Math & Scientific Reasoning · **Model:** Qwen2.5-Math-1.5B-Instruct
(GGUF Q4_K_M, llama.cpp) · **Team:** Boluwatife Faturoti (judeszn)

Every number in this report is measured, and each one cites the run that
produced it. Full experiment history, raw reports, and reproduction
workflows: [github.com/judeszn/EulerMind](https://github.com/judeszn/EulerMind).

## 1. Problem

A university student in Lagos, an SME owner in Dakar, or an extension
officer in Arusha has quantitative decisions to make — production mixes,
staff-to-site assignments, resource budgets — and no reliable way to
check an AI's arithmetic. Cloud LLMs are blocked by cost and
connectivity; local LLMs run, but hallucinate numbers confidently.

The failure mode that matters is not "no answer" — it is a **wrong
answer presented with confidence**. EulerMind is built around that exact
risk: a math-specialized local model wrapped in a deterministic
verification pipeline, so that answers within its solvable domains are
not just generated but **independently certified**, entirely offline, on
an ordinary 8 GB laptop.

## 2. Design decisions

### Model selection — measured, not guessed

We benchmarked 8 candidate GGUF models through the **official
adtc-profiler (unmodified)** on x86 4-vCPU CI runners (the closest
available match to the audit environment), then ran the 3 finalists
through lm_eval GSM8K under identical settings (seed 42, 50 samples,
same llama-server configuration, zero per-model tuning):

| Finalist | GSM8K (flexible) | TPS | Peak RAM |
|---|---|---|---|
| **Qwen2.5-Math-1.5B-Instruct** | **68%** | 15.02 | 1,700 MB |
| DeepSeek-R1-Distill-Qwen-1.5B | 66% | 17.34 | 1,817 MB |
| Qwen2.5-1.5B-Instruct | 52% | 15.85 | 1,825 MB |

(Frontier scan: EulerMind repo, CI run 28683815170; accuracy: run
28684426883. The selection rule was committed as executable code
*before* any accuracy result existed.) The math-specialized model beats
its same-family general sibling by +16 points on GSM8K at essentially
identical cost — that specialization gap, not the 2-point edge over
DeepSeek (one question in fifty, within noise), is why it ships.
Q4_K_M was chosen as the smallest quantization tier we validated
end-to-end within budget; the 1.0 GB weight file leaves >5 GB of the
budget unused.

### The application layer: verified, not just generated

Most submissions are `question → LLM → answer`. EulerMind's application
pipeline is:

```
question → parser-first Formalizer → exact Solver → certifying Verifier
         → independently-written Checker → certified answer
```

For problems in its three validated domains — resource-allocation
optimization, constraint-satisfaction assignment, and two-variable
linear programming — the LLM's job ends at formalization. Solving is
done by exact deterministic algorithms; every answer carries a
certificate; and each certificate is re-checked by a **second,
independently-written verifier that shares no code with the solver**
(for LP, the checker uses a different *theorem* — LP duality — than the
solver's vertex enumeration). Measured across all three domains: **0%
false certification, 192/192 certificates independently agreed**
(EulerMind repo: `research/G3_cert_independence/`,
`research/D2_lp_vertical/`).

**Scope honesty:** the automated ADTC benchmarks (throughput, lm_eval
accuracy) measure the base GGUF through llama.cpp — the verification
pipeline is the application layer around it, and its guarantees apply
to problems its formalizers parse. When a problem falls outside those
domains, EulerMind answers with the model and *says so* — the trust
label is earned by machinery, never asserted by the model.

### Reproducibility as a feature

The full certification pipeline re-runs on every push via GitHub
Actions and has reproduced **byte-identically across OS and CPU
architecture** (macOS/arm64 → Ubuntu/x86_64, sha256-equal reports; run
28673053751). This submission repo carries its own workflow that
re-runs the official profiler on every push.

### Try it yourself

`python3 -m app.local_demo` from this repository root starts the
offline demo (stdlib only); both registered test prompts are built-in
example buttons and certify end-to-end.

## 3. Constraints

Designed against the ADTC Standard Laptop, measured under it:

| Constraint | Design response | Measured |
|---|---|---|
| 8 GB RAM, OOM = disqualification | 1.5B Q4_K_M model, stdlib-only pipeline | Peak RSS **1,700 MB** — ~24% of the 7 GB scoring budget |
| CPU-only (no discrete GPU) | llama.cpp CPU inference; all solvers are exact classical algorithms | 15.02 TPS generation on 4 vCPU x86 |
| Offline | Zero network calls at inference; weights fetched once by `download_model.sh` | Verified: pipeline is Python stdlib + llama.cpp only |
| Thermal | Small model, short bursts, no sustained retry loops | No throttling observed in any profiled run |
| Connectivity/data cost context | One-time 1.0 GB download, then fully local forever | — |

## 4. Benchmarks

All numbers from the **official adtc-profiler, unmodified**, on x86
4-vCPU runners; artifacts retained and linked in the evidence repo.

| Metric | Value | Source run |
|---|---|---|
| Generation throughput (selection scan) | 15.02 tok/s | 28683815170 |
| Generation throughput (checked-in baseline re-run) | 15.68 tok/s | 28691529653 — run-to-run variance well inside the audit's ±25% tolerance |
| First-token latency (512-tok prompt) | 16.8 s | 28683815170 |
| Peak RSS | 1,700 MB | 28683815170 |
| GSM8K exact-match (flexible, n=50, seed 42) | 68% | 28684426883 |
| False certification (application layer, 3 domains, 192 certs) | 0% | EulerMind repo, G3/D2 |
| Cross-environment reproduction | byte-identical (sha256) | 28673053751 |

**African use case (load-bearing):** the two registered test prompts are
real SME/community planning problems — a Lagos furniture workshop's
production mix and a Nairobi health programme's volunteer assignment —
chosen because they are exactly the problem shapes the certification
pipeline solves and certifies. This pairing is the product's purpose,
not a theme applied afterward.
