# VENDORED verbatim from the EulerMind research repo (github.com/judeszn/EulerMind)
# at commit 8521038 - only import paths adapted. Canonical source + full
# experiment history live there. Do not edit here.
"""Gamma+2 — a genuinely independent certificate checker for
constraint_csp certificates.

Independence, concretely: this module imports NOTHING from
kernel.csp_solver (not solve, not recheck_certificate, not _check, not
_enumerate_solutions, not _minimal_conflict). The production
recheck_certificate calls `_check()` / `_enumerate_solutions()` — the same
functions `solve()` depends on — so a bug there would fool solver and
checker identically. This checker differs on BOTH axes:

  - **search algorithm**: solver enumerates via generate-all-permutations-
    then-filter (itertools.permutations + full-assignment test); this
    checker uses backtracking DFS with incremental per-step pruning
    (assign one engineer at a time, reject a branch the moment a
    constraint is violated on the partial assignment). Different
    algorithm, same guarantee of completeness over the same search space
    (all injective engineer->project maps).
  - **constraint evaluator**: separately written (`_full_satisfies`, a
    positive "all(satisfies(c))" formulation) rather than the solver's
    negative "return False on first violation" loop.

Completeness of the backtracking search: at every leaf (all engineers
assigned) every constraint is fully re-checked, so no partial-assignment
pruning can admit an invalid complete assignment; and because every
project is tried at every step (skipping only already-used ones), no
branch of the injective-map space is skipped, so no valid complete
assignment is missed either.
"""

from __future__ import annotations


def _full_satisfies(constraints: list[dict], tags: dict, assignment: dict) -> bool:
    """Independently-written full-assignment evaluator (positive
    "all constraints hold" formulation, not a shared function)."""
    def satisfies(con: dict) -> bool:
        kind = con["kind"]
        if kind == "forbidden":
            return assignment.get(con["engineer"]) != con["project"]
        if kind == "exact_tag":
            n = sum(1 for p in assignment.values() if tags.get(p) == con["tag"])
            return n == con["count"]
        if kind == "not_both_tag":
            return not (tags.get(assignment.get(con["e1"])) == con["tag"]
                       and tags.get(assignment.get(con["e2"])) == con["tag"])
        if kind == "implies":
            return not (assignment.get(con["e1"]) == con["p1"]
                       and assignment.get(con["e2"]) != con["p2"])
        return False  # unknown kind: fail closed
    return all(satisfies(c) for c in constraints)


def _partial_ok(constraints: list[dict], tags: dict, assignment: dict, n_total: int) -> bool:
    """Incremental pruning check on a PARTIAL assignment: reject only when
    a constraint is definitively already broken, or definitively cannot be
    satisfied by any completion (exact_tag count bound)."""
    filled = len(assignment)
    for con in constraints:
        kind = con["kind"]
        if kind == "forbidden":
            if assignment.get(con["engineer"]) == con["project"]:
                return False
        elif kind == "not_both_tag":
            if (con["e1"] in assignment and con["e2"] in assignment
                    and tags.get(assignment[con["e1"]]) == con["tag"]
                    and tags.get(assignment[con["e2"]]) == con["tag"]):
                return False
        elif kind == "implies":
            if (assignment.get(con["e1"]) == con["p1"] and con["e2"] in assignment
                    and assignment.get(con["e2"]) != con["p2"]):
                return False
        elif kind == "exact_tag":
            have = sum(1 for p in assignment.values() if tags.get(p) == con["tag"])
            remaining = n_total - filled
            if have > con["count"] or have + remaining < con["count"]:
                return False
        else:
            return False  # unknown kind: fail closed
    return True


def backtracking_search(engineers, projects, tags, constraints, limit=None):
    """Independent search: DFS backtracking with incremental pruning,
    assigning engineers one at a time — a different algorithm from the
    solver's generate-then-filter. Returns up to `limit` solutions (all,
    if limit is None)."""
    n = len(engineers)
    solutions: list[dict] = []
    assignment: dict = {}
    used: set = set()

    def recurse(idx: int) -> bool:
        """Returns True if the caller should stop (limit reached)."""
        if idx == n:
            if _full_satisfies(constraints, tags, assignment):
                solutions.append(dict(assignment))
                if limit is not None and len(solutions) >= limit:
                    return True
            return False
        eng = engineers[idx]
        for proj in projects:
            if proj in used:
                continue
            assignment[eng] = proj
            used.add(proj)
            if _partial_ok(constraints, tags, assignment, n):
                if recurse(idx + 1):
                    del assignment[eng]
                    used.remove(proj)
                    return True
            del assignment[eng]
            used.remove(proj)
        return False

    recurse(0)
    return solutions


def independent_recheck(cert: dict) -> dict:
    """Accept iff independently re-derived facts confirm the certificate's
    claim. Shares no search code or evaluator code with the production
    checker."""
    spec = cert["spec"]
    engineers, projects, tags = spec["engineers"], spec["projects"], spec["project_tags"]
    constraints = spec["constraints"]

    if cert["type"] == "satisfying_assignment_over_exhaustive_search":
        assignment = cert["claimed_assignment"]
        if set(assignment) != set(engineers):
            return {"accepted": False, "reason": "assignment covers wrong engineer set (independent)"}
        if len(set(assignment.values())) != len(assignment):
            return {"accepted": False, "reason": "assignment reuses a project (independent)"}
        if not set(assignment.values()) <= set(projects):
            return {"accepted": False, "reason": "assignment uses an unknown project (independent)"}
        if not _full_satisfies(constraints, tags, assignment):
            return {"accepted": False, "reason": "assignment violates a constraint (independent)"}
        return {"accepted": True,
                "reason": "assignment satisfies every constraint (independent backtracking evaluator)"}

    if cert["type"] == "minimal_conflict_with_search_exhaustion":
        conflict = cert["claimed_conflict"]
        if backtracking_search(engineers, projects, tags, conflict, limit=1):
            return {"accepted": False,
                    "reason": "claimed conflict set is actually satisfiable (independent backtracking search)"}
        for i in range(len(conflict)):
            trial = conflict[:i] + conflict[i + 1:]
            if not backtracking_search(engineers, projects, tags, trial, limit=1):
                return {"accepted": False,
                        "reason": f"conflict set not minimal - dropping constraint {i} still unsatisfiable (independent)"}
        return {"accepted": True,
                "reason": "conflict set is unsatisfiable and irreducible (independent backtracking search)"}

    return {"accepted": False, "reason": f"unknown certificate type {cert['type']}"}
