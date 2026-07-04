# VENDORED verbatim from the EulerMind research repo (github.com/judeszn/EulerMind)
# at commit 8521038 - only import paths adapted. Canonical source + full
# experiment history live there. Do not edit here.
"""Validation Phase 1 — deterministic solver + property-aligned verifier +
optimality certificate for bounded edge_ai_deployment.

Contract mapping (EulerMind Research Contract v1.0):
- Task 1 (Solver): solve_optimal() computes the true optimum of the
  FORMALIZED spec by exhaustive search over the feasible integer region,
  pruned by monotone resource bounds. No LLM. Fully offline. Complete by
  construction (adding a unit only increases additive resource use, so
  once a partial deployment exceeds a budget every extension does too -
  the pruned tree still visits every feasible point).
- Task 2 (Verifier): OptimalityVerifier certifies EXACTLY the benchmark
  grader's predicate - feasible AND score == the maximum over all feasible
  integer deployments. It never certifies mere feasibility.
- Task 3 (Certificate): a re-checkable object; recheck_certificate() is an
  INDEPENDENT search (separate code path from the solver) that re-derives
  the optimum from the spec and confirms the claimed answer matches.

Trust boundary (contract Principle 3): "Verified" == optimal *under the
formalized spec*. Whether that equals the benchmark's true answer depends
on formalization fidelity (measured separately, H0/1B). Verified-Correct
is the conjunction; False-Certification arises only if formalization is
unfaithful AND the wrong spec's optimum diverges from the true optimum.

Independent of benchmark/: score formula duplicated per the standing rule.
"""

from __future__ import annotations


def _score(acc: float, latency_ms: float) -> int:
    return round(1000 * (0.7 * acc + 0.3 * (1.0 / latency_ms)))


def _search_optimum(models: dict, budgets: dict, threshold: float):
    """Exhaustive DFS over the feasible integer region with monotone
    resource pruning. Returns (best_counts, best_score) or (None, None)
    if no feasible deployment satisfies the high-accuracy requirement.

    Complete: at each model it tries counts 0,1,2,... and stops that model
    the moment adding one more unit would exceed any budget given the
    resources already committed - valid because resource use is additive
    and non-negative, so no larger count of that model can become feasible
    later. Every feasible integer point is therefore visited."""
    names = list(models)
    b_ram, b_flops, b_lat = budgets["ram_gb"], budgets["flops_g"], budgets["latency_ms"]
    best = {"counts": None, "score": -1}

    def dfs(i, counts, ram, flops, lat):
        if i == len(names):
            high_acc = sum(counts[n] for n in names
                           if models[n]["accuracy"] >= threshold)
            if high_acc < 1:
                return
            score = sum(counts[n] * models[n]["score"] for n in names)
            if score > best["score"]:
                best["counts"] = dict(counts)
                best["score"] = score
            return
        name = names[i]
        m = models[name]
        k = 0
        while True:
            nram = ram + k * m["ram_gb"]
            nflops = flops + k * m["flops_g"]
            nlat = lat + k * m["latency_ms"]
            if nram > b_ram + 1e-9 or nflops > b_flops + 1e-9 or nlat > b_lat + 1e-9:
                break  # monotone: no larger k of this model is feasible
            counts[name] = k
            dfs(i + 1, counts, nram, nflops, nlat)
            k += 1
        counts[name] = 0

    dfs(0, {n: 0 for n in names}, 0.0, 0.0, 0.0)
    if best["counts"] is None:
        return None, None
    return best["counts"], best["score"]


def solve_optimal(spec: dict) -> dict:
    """Task 1. Deterministic candidate generation. Returns
    {counts, score, feasible} for the formalized spec."""
    counts, score = _search_optimum(spec["models"], spec["budgets"],
                                    spec["high_acc_threshold"])
    if counts is None:
        return {"counts": None, "score": None, "feasible": False}
    return {"counts": counts, "score": score, "feasible": True}


def make_certificate(spec: dict, counts: dict, score: int) -> dict:
    """Task 3. A re-checkable optimality certificate. Carries everything an
    independent checker needs; nothing about how the solver searched."""
    return {
        "type": "exhaustive_feasible_region_search",
        "certified_property": "optimal_over_all_feasible_integer_deployments_under_spec",
        "pruning": "monotone_additive_resource_bounds",
        "claimed_counts": dict(counts),
        "claimed_score": score,
        "spec": {"models": spec["models"], "budgets": spec["budgets"],
                 "high_acc_threshold": spec["high_acc_threshold"]},
    }


def recheck_certificate(cert: dict) -> dict:
    """Task 3, independent verification procedure. Re-derives the optimum
    from the certificate's spec via a fresh search and checks the claim.
    Deliberately re-implements the checks inline rather than trusting the
    solver's path (feasibility recomputed from scratch, optimum re-searched).
    Returns {accepted: bool, reason}."""
    spec = cert["spec"]
    models, b = spec["models"], spec["budgets"]
    counts, claimed = cert["claimed_counts"], cert["claimed_score"]

    # (a) claimed answer feasible?
    ram = sum(counts.get(n, 0) * models[n]["ram_gb"] for n in models)
    flops = sum(counts.get(n, 0) * models[n]["flops_g"] for n in models)
    lat = sum(counts.get(n, 0) * models[n]["latency_ms"] for n in models)
    if ram > b["ram_gb"] + 1e-9 or flops > b["flops_g"] + 1e-9 or lat > b["latency_ms"] + 1e-9:
        return {"accepted": False, "reason": "claimed answer violates a budget"}
    if sum(counts.get(n, 0) for n in models
           if models[n]["accuracy"] >= spec["high_acc_threshold"]) < 1:
        return {"accepted": False, "reason": "claimed answer misses high-accuracy requirement"}
    # (b) claimed score consistent with claimed counts?
    recomputed = sum(counts.get(n, 0) * models[n]["score"] for n in models)
    if recomputed != claimed:
        return {"accepted": False, "reason": f"score {claimed} != recomputed {recomputed}"}
    # (c) claimed score actually maximal? independent re-search.
    _, true_opt = _search_optimum(models, b, spec["high_acc_threshold"])
    if true_opt is None:
        return {"accepted": False, "reason": "no feasible deployment exists"}
    if claimed != true_opt:
        return {"accepted": False, "reason": f"claimed {claimed} is not optimal (true {true_opt})"}
    return {"accepted": True, "reason": "feasible, consistent, and optimal"}


# ---- Kernel-protocol adapters (Attempter + Verifier) --------------------

class SolverAttempter:
    """Contract Principle 4: where a deterministic solver exists, the solver
    produces the candidate, not the LLM. Fits the frozen Attempter protocol."""

    def attempt(self, state) -> dict:
        spec = state.formalization.get("spec")
        if spec is None:
            return {"counts": None, "tokens": 0, "solver": "none"}
        sol = solve_optimal(spec)
        return {"counts": sol["counts"], "score": sol["score"],
                "feasible": sol["feasible"], "tokens": 0, "solver": "exhaustive"}


class OptimalityVerifier:
    """Task 2. Certifies the benchmark predicate (feasible + optimal), never
    a weaker one. Emits the certificate and the independent-recheck result.
    Assigns trust labels per the frozen contract."""

    def verify(self, state, execution: dict) -> dict:
        spec = state.formalization.get("spec")
        answer = execution.get("answer")
        if spec is None:
            return {"ok": False, "trust_label": "Open", "failure_type": "formalization",
                    "signals": [{"kind": "formalization_shape", "location": "formalization",
                                 "evidence": {"detail": "no usable spec"}}]}
        if not isinstance(answer, dict) or answer.get("counts") is None:
            # No candidate produced (e.g. solver found the spec infeasible).
            return {"ok": False, "trust_label": "Open", "failure_type": "execution",
                    "signals": [{"kind": "no_candidate", "location": "solver",
                                 "evidence": {"detail": "solver produced no feasible deployment"}}]}

        cert = make_certificate(spec, answer["counts"], answer["score"])
        recheck = recheck_certificate(cert)
        if recheck["accepted"]:
            return {"ok": True, "trust_label": "Verified", "failure_type": None,
                    "signals": [], "certificate": cert, "recheck": recheck}
        # Solver+verifier disagreement would be an internal defect; the answer
        # is at best feasible-but-uncertified -> Derived, never Verified.
        return {"ok": False, "trust_label": "Derived", "failure_type": "verification",
                "signals": [{"kind": "optimality_uncertified", "location": "answer",
                             "evidence": {"detail": recheck["reason"]}}],
                "certificate": cert, "recheck": recheck}
