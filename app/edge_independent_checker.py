# VENDORED verbatim from the EulerMind research repo (github.com/judeszn/EulerMind)
# at commit 8521038 - only import paths adapted. Canonical source + full
# experiment history live there. Do not edit here.
"""Gamma+1 — a genuinely independent certificate checker for
edge_ai_deployment optimality certificates.

Independence, concretely: this module imports NOTHING from
kernel.edge_ai_solver (not the solver, not its recheck, not its
_search_optimum, not its _score). The production recheck_certificate
shares `_search_optimum` (recursive DFS + monotone pruning) with the
solver — a pruning bug would fool both. This checker instead:

  - establishes the optimum by BRUTE-FORCE enumeration with NO pruning
    (itertools.product over budget-implied per-model bounds) — the most
    trustworthy optimality oracle, because there is no pruning logic that
    could be wrong;
  - recomputes the score formula from raw accuracy/latency (does not trust
    the spec's precomputed per-model "score" field);
  - recomputes feasibility from raw stats.

If a pruning bug had let the solver miss a higher-scoring feasible point,
this unpruned enumeration would find it and REJECT the certificate. That
is the property "independence" must have.

Complete-enumeration bound: for model i, no feasible deployment can use
more than floor(min_over_budgets(budget / per-unit-cost_i)) units. The
product over these bounds is a superset of the feasible region, so
enumerating it and filtering by feasibility visits every feasible point.
"""

from __future__ import annotations

import itertools

TOL = 1e-9
_ENUM_CAP = 20_000_000  # guard against pathological boxes; report if exceeded


def _indep_score(accuracy: float, latency_ms: float) -> int:
    """The objective, reimplemented independently (same formula — it is the
    problem definition, not search logic — but a separate implementation, so
    a typo in the solver's _score would be caught)."""
    return round(1000 * (0.7 * accuracy + 0.3 * (1.0 / latency_ms)))


def _per_model_bounds(models: dict, budgets: dict) -> dict:
    bounds = {}
    for n, m in models.items():
        cand = []
        if m["ram_gb"] > 0:
            cand.append(int(budgets["ram_gb"] // m["ram_gb"]))
        if m["flops_g"] > 0:
            cand.append(int(budgets["flops_g"] // m["flops_g"]))
        if m["latency_ms"] > 0:
            cand.append(int(budgets["latency_ms"] // m["latency_ms"]))
        bounds[n] = min(cand) if cand else 0
    return bounds


def _feasible(models, budgets, threshold, counts) -> bool:
    ram = sum(counts.get(n, 0) * models[n]["ram_gb"] for n in models)
    flops = sum(counts.get(n, 0) * models[n]["flops_g"] for n in models)
    lat = sum(counts.get(n, 0) * models[n]["latency_ms"] for n in models)
    if ram > budgets["ram_gb"] + TOL or flops > budgets["flops_g"] + TOL \
            or lat > budgets["latency_ms"] + TOL:
        return False
    high = sum(counts.get(n, 0) for n in models
               if models[n]["accuracy"] >= threshold)
    return high >= 1


def independent_optimum(spec: dict):
    """Brute-force, no pruning. Returns (best_score, enum_size) or
    (None, enum_size) if no feasible deployment, or ('CAPPED', size)."""
    models, budgets, thr = spec["models"], spec["budgets"], spec["high_acc_threshold"]
    names = list(models)
    bounds = _per_model_bounds(models, budgets)
    size = 1
    for n in names:
        size *= (bounds[n] + 1)
    if size > _ENUM_CAP:
        return "CAPPED", size

    ram_c = [models[n]["ram_gb"] for n in names]
    flp_c = [models[n]["flops_g"] for n in names]
    lat_c = [models[n]["latency_ms"] for n in names]
    scr_c = [_indep_score(models[n]["accuracy"], models[n]["latency_ms"]) for n in names]
    hi_c = [1 if models[n]["accuracy"] >= thr else 0 for n in names]
    B_ram, B_flp, B_lat = budgets["ram_gb"], budgets["flops_g"], budgets["latency_ms"]

    best = None
    for combo in itertools.product(*(range(bounds[n] + 1) for n in names)):
        ram = flp = lat = 0.0
        score = 0
        high = 0
        for c, rc, fc, lc, sc, hc in zip(combo, ram_c, flp_c, lat_c, scr_c, hi_c):
            if c:
                ram += c * rc; flp += c * fc; lat += c * lc
                score += c * sc; high += c * hc
        if ram <= B_ram + TOL and flp <= B_flp + TOL and lat <= B_lat + TOL and high >= 1:
            if best is None or score > best:
                best = score
    return best, size


def independent_recheck(cert: dict) -> dict:
    """Accept iff the claimed answer is (a) feasible, (b) its score matches an
    independent recomputation from raw stats, and (c) equals the brute-force
    optimum. Shares no search code with the production checker."""
    spec = cert["spec"]
    models = spec["models"]
    counts = cert["claimed_counts"]
    claimed = cert["claimed_score"]

    if not _feasible(models, spec["budgets"], spec["high_acc_threshold"], counts):
        return {"accepted": False, "reason": "claimed answer infeasible (independent check)"}

    recomputed = sum(counts.get(n, 0) * _indep_score(models[n]["accuracy"],
                                                     models[n]["latency_ms"])
                     for n in models)
    if recomputed != claimed:
        return {"accepted": False,
                "reason": f"claimed score {claimed} != independent recompute {recomputed}"}

    opt, size = independent_optimum(spec)
    if opt == "CAPPED":
        return {"accepted": False, "reason": f"enumeration box too large ({size}); cannot certify"}
    if opt is None:
        return {"accepted": False, "reason": "no feasible deployment exists (independent)"}
    if claimed != opt:
        return {"accepted": False,
                "reason": f"claimed {claimed} is not optimal (independent brute-force found {opt})"}
    return {"accepted": True, "reason": "feasible, score-consistent, and optimal (independent)",
            "independent_optimum": opt, "enum_size": size}
