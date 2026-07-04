# VENDORED verbatim from the EulerMind research repo (github.com/judeszn/EulerMind)
# at commit 8521038 - only import paths adapted. Canonical source + full
# experiment history live there. Do not edit here.
"""Real (LLM-backed) stage implementations for edge_ai_deployment.

This is what Oracle Mode was rehearsing for (kernel/oracle.py's own
docstring: "if the kernel cannot pass with an oracle, the LLM will never
save it"). Milestone 2/3 (WIN.md): same kernel, same Policy, same
FailureSignal contract — only the stage implementations changed from
mechanical/ground-truth-cheating to LLM-backed/real.

Guardrail 2 in concrete form: the Attempter proposes ONLY integer counts.
It is never asked to compute or self-report RAM/FLOPS/latency/score —
that arithmetic is the Executor's job, deterministically, every time.
This is deliberate: asking the model to also verify its own numbers is
exactly L1's measured failure mode (research/L1_reasoning_prompt/RESULTS.md
— the model hallucinated constraints, "verified" them against itself, and
returned a confident wrong answer).

Deliberately independent of benchmark/ (kernel must never import the
instrument that measures it) - the score formula is duplicated from
benchmark/generator/edge_ai.py's _score(), matching the precedent already
set by kernel/oracle.py's MechanicalVerifier.

BlindAttempter (B2, the H1 control) ignores state.verifier_result
entirely and resamples at nonzero temperature — "blind resampling at
temperature," per H1's registered text. GuidedAttempter (B3, the
treatment) reads the previous FailureSignals into the prompt and samples
at temperature 0 (the correction should come from the signal, not luck).
"""

from __future__ import annotations

import json
import urllib.request

OLLAMA_URL = "http://localhost:11434/api/generate"


def _score(acc: float, latency_ms: float) -> int:
    """Duplicated from benchmark/generator/edge_ai.py by design - see
    module docstring. Must stay numerically identical to that function."""
    return round(1000 * (0.7 * acc + 0.3 * (1.0 / latency_ms)))


def _ollama_json(model: str, prompt: str, *, temperature: float = 0.0,
                 num_predict: int = 600, timeout_s: int = 120, seed: int = 0) -> dict | None:
    """Call Ollama with JSON-forced output. Returns the parsed dict, or
    None if the model didn't produce valid JSON even after one retry with
    a stricter instruction — callers must treat None as a real outcome
    (a malformed-output FailureSignal), never crash on it."""
    for attempt_prompt in (prompt, prompt + "\n\nRespond with ONLY the JSON object, nothing else."):
        try:
            payload = json.dumps({
                "model": model, "prompt": attempt_prompt, "stream": False,
                "format": "json",
                "options": {"temperature": temperature, "num_predict": num_predict, "seed": seed},
            }).encode()
            req = urllib.request.Request(OLLAMA_URL, data=payload,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                out = json.loads(resp.read())
            parsed = json.loads(out.get("response", "") or "{}")
            if isinstance(parsed, dict):
                return {"_parsed": parsed, "_tokens": out.get("eval_count", 0)}
        except Exception:
            continue
    return None


class LLMFormalizer:
    """NL text -> {models: {name: {ram_gb, flops_g, accuracy, latency_ms}},
    budgets: {ram_gb, flops_g, latency_ms}, high_acc_threshold}.

    Target schema is NOT invented here - it's the same spec shape Oracle
    Mode already validated (benchmark/generator/edge_ai.py's ground truth
    shape). Only the extraction-from-text step was unvalidated; see
    research/edge_ai_family_decision.md's "Trap 2" note.
    """

    def __init__(self, model: str = "llama3.2:1b"):
        self.model = model

    def formalize(self, state) -> dict:
        prompt = (
            "Extract the mathematical model from this edge AI deployment "
            "problem. Ignore any sentences irrelevant to models, budgets, "
            "or the accuracy requirement. Respond with ONLY this JSON shape:\n"
            '{"models": {"<model name>": {"ram_gb": <number>, "flops_g": <number>, '
            '"accuracy": <number>, "latency_ms": <number>}, ...}, '
            '"budgets": {"ram_gb": <number>, "flops_g": <number>, "latency_ms": <number>}, '
            '"high_acc_threshold": <number>}\n'
            "Convert any units to match: RAM in GB, latency in ms.\n\n"
            f"Problem:\n{state.problem_text}\n"
        )
        result = _ollama_json(self.model, prompt, temperature=0.0)
        tokens = result["_tokens"] if result else 0
        spec = result["_parsed"] if result else None
        valid = (isinstance(spec, dict) and isinstance(spec.get("models"), dict)
                 and spec["models"] and isinstance(spec.get("budgets"), dict)
                 and isinstance(spec.get("high_acc_threshold"), (int, float)))
        if valid:
            for m in spec["models"].values():
                try:
                    m["score"] = _score(float(m["accuracy"]), float(m["latency_ms"]))
                except (KeyError, TypeError, ValueError, ZeroDivisionError):
                    valid = False
                    break
        return {"kind": "knapsack", "spec": spec if valid else None,
                "formalizer_tokens": tokens}


class BlindAttempter:
    """B2 / H1 control: ignores state.verifier_result entirely. Resamples
    at nonzero temperature - "blind resampling at temperature" per H1's
    registered hypothesis text, not a deterministic repeat of the same
    wrong answer."""

    def __init__(self, model: str = "llama3.2:1b"):
        self.model = model

    def attempt(self, state) -> dict:
        spec = state.formalization.get("spec")
        if spec is None:
            return {"counts": None, "tokens": 0}
        prompt = _propose_prompt(spec)
        result = _ollama_json(self.model, prompt, temperature=0.6,
                              seed=state.attempt)
        counts = result["_parsed"].get("counts") if result else None
        tokens = result["_tokens"] if result else 0
        return {"counts": counts, "tokens": tokens}


class GuidedAttempter:
    """B3 / H1 treatment: reads the previous attempt's FailureSignals into
    the prompt, temperature 0 (the correction should come from the
    signal, not from luck)."""

    def __init__(self, model: str = "llama3.2:1b"):
        self.model = model

    def attempt(self, state) -> dict:
        spec = state.formalization.get("spec")
        if spec is None:
            return {"counts": None, "tokens": 0}
        prompt = _propose_prompt(spec)
        prior = state.verifier_result
        if prior and not prior.get("ok") and prior.get("signals"):
            prompt += "\n\nYour previous attempt failed these checks:\n"
            for s in prior["signals"]:
                prompt += f"- {s['kind']} at {s['location']}: {s['evidence']}\n"
            prompt += "Propose a different plan that fixes these specific problems."
        result = _ollama_json(self.model, prompt, temperature=0.0)
        counts = result["_parsed"].get("counts") if result else None
        tokens = result["_tokens"] if result else 0
        return {"counts": counts, "tokens": tokens}


def _propose_prompt(spec: dict) -> str:
    lines = "\n".join(
        f"- {name}: {m['ram_gb']}GB RAM, {m['flops_g']} GFLOPS, "
        f"accuracy={m['accuracy']}, latency={m['latency_ms']}ms"
        for name, m in spec["models"].items())
    b = spec["budgets"]
    return (
        "Propose how many units of each model to deploy (non-negative "
        "integers) to maximize total weighted score, given these budgets: "
        f"{b['ram_gb']}GB RAM, {b['flops_g']} GFLOPS, {b['latency_ms']}ms "
        f"latency, and at least one deployed model with accuracy >= "
        f"{spec['high_acc_threshold']}.\n\nModels:\n{lines}\n\n"
        'Respond with ONLY: {"counts": {"<model name>": <integer>, ...}}'
    )


class DeterministicExecutor:
    """Guardrail 2 enforced: computes RAM/FLOPS/latency/score from the
    Attempter's proposed counts. The model never has to get its own
    arithmetic right - it only has to propose counts."""

    def execute(self, state, attempt: dict) -> dict:
        spec = state.formalization.get("spec")
        counts = attempt.get("counts")
        if spec is None or not isinstance(counts, dict):
            return {"tool": "arithmetic", "answer": None,
                    "tokens": attempt.get("tokens", 0)}
        models = spec["models"]
        resolved = {}
        for name in models:
            c = counts.get(name, 0)
            try:
                resolved[name] = max(0, round(float(c)))
            except (TypeError, ValueError):
                resolved[name] = 0
        score = sum(resolved[n] * models[n]["score"] for n in models)
        return {"tool": "arithmetic",
                "answer": {"counts": resolved, "score": score},
                "tokens": attempt.get("tokens", 0)}


class KnapsackVerifier:
    """Deterministic, structurally identical to MechanicalVerifier's
    _check_lp - but checks against the LLM's OWN formalization, not
    ground truth. This is the concrete mechanism behind Law 1's caveat:
    "Verified" here means internally consistent with what the model
    extracted, which is why the False-Verification-Rate metric (computed
    OUTSIDE the kernel, against benchmark.metrics.grade()) exists at all."""

    TOL = 1e-6

    def verify(self, state, execution: dict) -> dict:
        spec = state.formalization.get("spec")
        if spec is None:
            return {"ok": False, "failure_type": "formalization", "signals": [
                {"kind": "formalization_shape", "location": "formalization",
                 "evidence": {"detail": "formalizer produced no usable spec"}}]}
        answer = execution.get("answer")
        if not isinstance(answer, dict) or not isinstance(answer.get("counts"), dict):
            return {"ok": False, "failure_type": "execution", "signals": [
                {"kind": "answer_shape", "location": "counts",
                 "evidence": {"detail": "missing or malformed counts"}}]}

        models = spec["models"]
        counts = answer["counts"]
        signals = []
        ram = sum(counts.get(n, 0) * models[n]["ram_gb"] for n in models)
        flops = sum(counts.get(n, 0) * models[n]["flops_g"] for n in models)
        latency = sum(counts.get(n, 0) * models[n]["latency_ms"] for n in models)
        b = spec["budgets"]
        if ram > b["ram_gb"] + self.TOL:
            signals.append({"kind": "constraint_violation", "location": "ram_budget",
                            "evidence": {"used": ram, "budget": b["ram_gb"],
                                        "violated_by": ram - b["ram_gb"]}})
        if flops > b["flops_g"] + self.TOL:
            signals.append({"kind": "constraint_violation", "location": "flops_budget",
                            "evidence": {"used": flops, "budget": b["flops_g"],
                                        "violated_by": flops - b["flops_g"]}})
        if latency > b["latency_ms"] + self.TOL:
            signals.append({"kind": "constraint_violation", "location": "latency_budget",
                            "evidence": {"used": latency, "budget": b["latency_ms"],
                                        "violated_by": latency - b["latency_ms"]}})
        high_acc_units = sum(counts.get(n, 0) for n in models
                             if models[n]["accuracy"] >= spec["high_acc_threshold"])
        if high_acc_units < 1:
            signals.append({"kind": "constraint_violation", "location": "high_acc_requirement",
                            "evidence": {"high_acc_units": high_acc_units}})
        computed_score = sum(counts.get(n, 0) * models[n]["score"] for n in models)
        if abs(computed_score - answer.get("score", -1)) > self.TOL:
            signals.append({"kind": "profit_consistency", "location": "score",
                            "evidence": {"claimed": answer.get("score"),
                                        "computed": computed_score}})

        if signals:
            return {"ok": False, "failure_type": "verification", "signals": signals}
        return {"ok": True, "trust_label": "Verified", "failure_type": None, "signals": []}
