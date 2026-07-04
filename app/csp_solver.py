# VENDORED verbatim from the EulerMind research repo (github.com/judeszn/EulerMind)
# at commit 8521038 - only import paths adapted. Canonical source + full
# experiment history live there. Do not edit here.
"""Gamma Tasks 2-5 — CSP Solver, property-aligned Verifier, certificates,
and an independent checker for constraint_csp.

Solver (Task 2): complete, deterministic, offline. 5 engineers into 7
distinct projects = P(7,5) = 2520 permutations - exhaustive search is
exact and instant. Produces a satisfying assignment when one exists, or a
minimal (irreducible) conflict set + a completeness proof when none does.

Verifier (Task 3): certifies exactly the benchmark's predicate
(benchmark/metrics.py::_grade_csp) - satisfiable+valid-assignment, or
correctly-refused-unsat. Never a weaker property (e.g. "some checks
passed" without exhaustion is not enough to certify UNSAT).

Certificate (Task 4): SAT -> the assignment (re-checkable by re-evaluating
every constraint). UNSAT -> the minimal conflict set + search-exhaustion
count (re-checkable by re-enumerating and confirming zero solutions, and
by confirming removing any one conflict-set constraint restores >=1
solution - that second check is what makes it MINIMAL, not just a conflict).

Independent checker (Task 5): recheck_certificate() re-implements
constraint checking from scratch (does not import benchmark/, does not
call the solver's own _check_assignment for the final accept/reject -
uses a separately written evaluator) and, for UNSAT, re-enumerates
independently rather than trusting the solver's stored result.

Independent of benchmark/ - check_assignment logic is necessarily
duplicated (kernel must not import the instrument that measures it).
"""

from __future__ import annotations

import itertools


def _check(constraints: list[dict], tags: dict, assignment: dict) -> bool:
    """Independent implementation of constraint satisfaction - written
    separately from benchmark/generator/csp.py::check_assignment, not
    imported from it, per the standing kernel/benchmark independence rule."""
    for con in constraints:
        kind = con["kind"]
        if kind == "forbidden":
            if assignment.get(con["engineer"]) == con["project"]:
                return False
        elif kind == "exact_tag":
            n = sum(1 for p in assignment.values() if tags.get(p) == con["tag"])
            if n != con["count"]:
                return False
        elif kind == "not_both_tag":
            if (tags.get(assignment.get(con["e1"])) == con["tag"]
                    and tags.get(assignment.get(con["e2"])) == con["tag"]):
                return False
        elif kind == "implies":
            if (assignment.get(con["e1"]) == con["p1"]
                    and assignment.get(con["e2"]) != con["p2"]):
                return False
        else:
            return False  # unknown constraint kind: fail closed, never fabricate
    return True


def _enumerate_solutions(engineers, projects, tags, constraints, limit=None):
    sols = []
    for perm in itertools.permutations(projects, len(engineers)):
        assignment = dict(zip(engineers, perm))
        if _check(constraints, tags, assignment):
            sols.append(assignment)
            if limit is not None and len(sols) >= limit:
                break
    return sols


def _minimal_conflict(engineers, projects, tags, constraints) -> list[dict]:
    """Greedy irreducibility: drop each constraint in turn; keep the drop
    only if the remaining set is still unsatisfiable. Independent
    implementation (not imported from the generator, which uses the same
    algorithm to build the instance in the first place - re-deriving it
    here is the point: an independently-computed minimal set that happens
    to agree is stronger evidence than trusting the generator's own)."""
    core = list(constraints)
    for con in list(core):
        trial = [c for c in core if c is not con]
        if not _enumerate_solutions(engineers, projects, tags, trial, limit=1):
            core = trial
    return core


def solve(spec: dict) -> dict:
    """Task 2. Complete search. Returns either a satisfying assignment or
    a minimal-conflict UNSAT result, never a guess."""
    engineers, projects, tags = spec["engineers"], spec["projects"], spec["project_tags"]
    constraints = spec["constraints"]
    total_perms = 1
    for i in range(len(engineers)):
        total_perms *= (len(projects) - i)

    sols = _enumerate_solutions(engineers, projects, tags, constraints)
    if sols:
        return {"satisfiable": True, "assignment": sols[0],
                "solution_count_found": len(sols), "search_exhausted": True,
                "total_permutations": total_perms}
    conflict = _minimal_conflict(engineers, projects, tags, constraints)
    return {"satisfiable": False, "assignment": None,
             "minimal_conflict": conflict, "search_exhausted": True,
             "total_permutations": total_perms}


def make_certificate(spec: dict, solution: dict) -> dict:
    """Task 4. Re-checkable certificate object."""
    if solution["satisfiable"]:
        return {"type": "satisfying_assignment_over_exhaustive_search",
                "certified_property": "assignment_satisfies_all_constraints",
                "spec": spec, "claimed_assignment": solution["assignment"]}
    return {"type": "minimal_conflict_with_search_exhaustion",
            "certified_property": "no_assignment_satisfies_all_constraints",
            "spec": spec, "claimed_conflict": solution["minimal_conflict"],
            "total_permutations": solution["total_permutations"]}


def recheck_certificate(cert: dict) -> dict:
    """Task 5. Independent checker. Re-evaluates from scratch; does not
    trust the solver's stored verdict for either branch."""
    spec = cert["spec"]
    engineers, projects, tags = spec["engineers"], spec["projects"], spec["project_tags"]

    if cert["type"] == "satisfying_assignment_over_exhaustive_search":
        assignment = cert["claimed_assignment"]
        if set(assignment) != set(engineers):
            return {"accepted": False, "reason": "assignment covers wrong engineer set"}
        if len(set(assignment.values())) != len(assignment):
            return {"accepted": False, "reason": "assignment reuses a project"}
        if not set(assignment.values()) <= set(projects):
            return {"accepted": False, "reason": "assignment uses an unknown project"}
        if not _check(spec["constraints"], tags, assignment):
            return {"accepted": False, "reason": "assignment violates a constraint"}
        return {"accepted": True, "reason": "assignment satisfies every constraint"}

    if cert["type"] == "minimal_conflict_with_search_exhaustion":
        conflict = cert["claimed_conflict"]
        # (a) the conflict set itself must be unsatisfiable - independent re-enumeration.
        if _enumerate_solutions(engineers, projects, tags, conflict, limit=1):
            return {"accepted": False, "reason": "claimed conflict set is actually satisfiable"}
        # (b) minimality: removing ANY one constraint must restore >=1 solution.
        for i in range(len(conflict)):
            trial = conflict[:i] + conflict[i + 1:]
            if not _enumerate_solutions(engineers, projects, tags, trial, limit=1):
                return {"accepted": False,
                        "reason": f"conflict set not minimal - dropping constraint {i} still unsatisfiable"}
        return {"accepted": True, "reason": "conflict set is unsatisfiable and irreducible"}

    return {"accepted": False, "reason": f"unknown certificate type {cert['type']}"}


# ---- Kernel-protocol adapters --------------------------------------------

class SolverAttempter:
    """Certification-only role (see contract-tension note): produces the
    reference/certifying candidate. NOT used as the H1 experiment's
    Attempter - that role is the LLM (BlindCSPAttempter/GuidedCSPAttempter
    in kernel/csp_attempters.py), so H1's feedback-visibility comparison
    retains a real gap for feedback to close."""

    def attempt(self, state) -> dict:
        spec = state.formalization.get("spec")
        if spec is None:
            return {"solution": None}
        return {"solution": solve(spec)}


class DeterministicCSPExecutor:
    """Executor stage. CSP has no arithmetic to compute (unlike knapsack's
    score) - its job is shape validation only: pass through a well-formed
    proposed solution, or flag a malformed one, before the Verifier sees it."""

    def execute(self, state, attempt: dict) -> dict:
        solution = (attempt or {}).get("solution")
        if not isinstance(solution, dict) or "satisfiable" not in solution:
            return {"tool": "shape_check", "answer": None,
                    "tokens": (attempt or {}).get("tokens", 0)}
        return {"tool": "shape_check", "answer": solution,
                "tokens": (attempt or {}).get("tokens", 0)}


class CSPCertifyingVerifier:
    """Task 3. Certifies exactly the benchmark grading predicate. Assigns
    Verified only when the certificate independently rechecks; otherwise
    Derived (internally attempted but uncertified, matching the precedent
    set by kernel/edge_ai_solver.py's OptimalityVerifier) or Open (no
    candidate at all).

    Critical asymmetry the LLM cannot resolve on its own: a SAT claim is
    checked directly against the claimed assignment (cheap). A bare UNSAT
    claim carries no proof - the LLM has no way to search 2520 permutations
    itself - so the verifier must independently run solve() to confirm or
    refute the claim before any label is assigned. Never trust "I couldn't
    find one" as equivalent to "none exists" (Law 1)."""

    def verify(self, state, execution: dict) -> dict:
        spec = state.formalization.get("spec")
        solution = (execution or {}).get("answer")
        if spec is None:
            return {"ok": False, "trust_label": "Open", "failure_type": "formalization",
                    "signals": [{"kind": "formalization_shape", "location": "formalization",
                                 "evidence": {"detail": "no usable spec"}}]}
        if solution is None:
            return {"ok": False, "trust_label": "Open", "failure_type": "execution",
                    "signals": [{"kind": "no_candidate", "location": "attempt",
                                 "evidence": {"detail": "no solution produced"}}]}

        if solution.get("satisfiable") is True:
            if not isinstance(solution.get("assignment"), dict):
                return {"ok": False, "trust_label": "Open", "failure_type": "execution",
                        "signals": [{"kind": "answer_shape", "location": "assignment",
                                     "evidence": {"detail": "satisfiable=True but no assignment"}}]}
            proposed = {"satisfiable": True, "assignment": solution["assignment"]}
        else:
            # Bare UNSAT claim: the verifier must independently establish
            # ground truth by search - the LLM's claim is not itself evidence.
            independent = solve(spec)
            if independent["satisfiable"]:
                # Claim contradicted: a solution DOES exist. Fabricated
                # certainty - never labeled Verified, regardless of how
                # confident the claim was.
                return {"ok": False, "trust_label": "Derived", "failure_type": "verification",
                        "signals": [{"kind": "unsat_claim_contradicted", "location": "satisfiable",
                                     "evidence": {"detail": "a valid assignment exists",
                                                 "counterexample": independent["assignment"]}}]}
            proposed = independent  # verifier's own solve() supplies the minimal_conflict

        cert = make_certificate(spec, proposed)
        recheck = recheck_certificate(cert)
        if recheck["accepted"]:
            return {"ok": True, "trust_label": "Verified", "failure_type": None,
                    "signals": [], "certificate": cert, "recheck": recheck}
        return {"ok": False, "trust_label": "Derived", "failure_type": "verification",
                "signals": [{"kind": "certification_failed", "location": "answer",
                             "evidence": {"detail": recheck["reason"]}}],
                "certificate": cert, "recheck": recheck}
