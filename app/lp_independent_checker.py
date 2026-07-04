# VENDORED verbatim from the EulerMind research repo (github.com/judeszn/EulerMind)
# at commit 8521038 - only import paths adapted. Canonical source + full
# experiment history live there. Do not edit here.
"""Delta D2 Task 5 — a genuinely independent certificate checker for
optimization_lp, built on the LP DUALITY THEOREM instead of vertex
enumeration.

kernel/lp_solver.py's solver and its production recheck_certificate both
rest on the Fundamental Theorem of LP (optimum occurs at a feasible-region
vertex) and share the same vertex-enumeration search. This checker shares
no optimization logic with either: it performs NO search at all. Given a
claimed optimal (x, y, profit), it:

  1. Checks primal feasibility directly (arithmetic only).
  2. Determines the active set - which of {x=0, y=0, constraint1 tight,
     constraint2 tight} hold at the claimed point (arithmetic only).
  3. Constructs dual variables (u1, u2) implied by Complementary Slackness
     applied to that active set (solving AT MOST a 2x2 linear system -
     never a search over candidate points).
  4. Verifies dual feasibility (u >= 0, both dual constraints hold) and
     Strong Duality (dual objective == claimed primal objective).

If (3)-(4) succeed, the LP Duality Theorem certifies (x, y) is optimal -
independently of any vertex re-derivation. If no valid dual witness
exists, or dual/primal objectives disagree, the certificate is rejected.

This is the Fundamental Theorem of LP (solver) vs the LP Duality Theorem
(checker) - two different theorems, not two implementations of the same
argument.

Primal: max p1*x + p2*y  s.t.  a1*x + b1*y <= c1,  a2*x + b2*y <= c2,  x,y >= 0
Dual:   min c1*u1 + c2*u2  s.t.  a1*u1 + a2*u2 >= p1,  b1*u1 + b2*u2 >= p2,  u1,u2 >= 0

Complementary Slackness:
  x > 0  => a1*u1 + a2*u2 = p1        (dual constraint for x binds)
  y > 0  => b1*u1 + b2*u2 = p2        (dual constraint for y binds)
  constraint1 slack (> 0)  => u1 = 0
  constraint2 slack (> 0)  => u2 = 0
"""

from __future__ import annotations

TOL = 1e-6


def _construct_dual(spec: dict, x: float, y: float) -> tuple[float, float] | None:
    """Solve for (u1, u2) from the Complementary Slackness system implied
    by which of {x, y, slack1, slack2} are strictly positive at (x, y).
    Returns None if the system can't be solved (degenerate vertex, or a
    coefficient needed for a 1-unknown solve is zero)."""
    a1, b1, c1 = spec["a1"], spec["b1"], spec["c1"]
    a2, b2, c2 = spec["a2"], spec["b2"], spec["c2"]
    s1 = c1 - (a1 * x + b1 * y)
    s2 = c2 - (a2 * x + b2 * y)

    x_pos, y_pos = x > TOL, y > TOL
    s1_pos, s2_pos = s1 > TOL, s2 > TOL

    if sum([x_pos, y_pos, s1_pos, s2_pos]) != 2:
        return None  # not a non-degenerate vertex; no unique CS witness

    fixed: dict[str, float] = {}
    if s1_pos:
        fixed["u1"] = 0.0
    if s2_pos:
        fixed["u2"] = 0.0
    equations = []
    if x_pos:
        equations.append((a1, a2, spec["p1"]))  # a1*u1 + a2*u2 = p1
    if y_pos:
        equations.append((b1, b2, spec["p2"]))  # b1*u1 + b2*u2 = p2

    if len(fixed) == 2:
        return fixed["u1"], fixed["u2"]

    if len(fixed) == 1 and len(equations) == 1:
        coef1, coef2, rhs = equations[0]
        if "u1" in fixed:
            u1 = fixed["u1"]
            if abs(coef2) < 1e-12:
                return None
            u2 = (rhs - coef1 * u1) / coef2
            return u1, u2
        else:
            u2 = fixed["u2"]
            if abs(coef1) < 1e-12:
                return None
            u1 = (rhs - coef2 * u2) / coef1
            return u1, u2

    if len(equations) == 2:
        (A1, B1, R1), (A2, B2, R2) = equations
        det = A1 * B2 - A2 * B1
        if abs(det) < 1e-12:
            return None
        u1 = (R1 * B2 - R2 * B1) / det
        u2 = (A1 * R2 - A2 * R1) / det
        return u1, u2

    return None  # unreachable given sum([...])==2, kept for clarity


def independent_recheck(cert: dict) -> dict:
    """Accept iff the LP Duality Theorem certifies optimality: a
    dual-feasible witness exists whose objective matches the claimed
    primal objective (strong duality). Shares no code with
    kernel/lp_solver.py."""
    spec = cert["spec"]
    if cert["type"] != "lp_vertex_optimum":
        return {"accepted": False,
                "reason": f"independent checker only certifies optimal-status claims, got {cert['type']}"}

    x, y, claimed = cert["claimed_x"], cert["claimed_y"], cert["claimed_profit"]

    if x < -TOL or y < -TOL:
        return {"accepted": False, "reason": "claimed point violates non-negativity (independent)"}
    if spec["a1"] * x + spec["b1"] * y > spec["c1"] + TOL:
        return {"accepted": False, "reason": "claimed point violates constraint 1 (independent)"}
    if spec["a2"] * x + spec["b2"] * y > spec["c2"] + TOL:
        return {"accepted": False, "reason": "claimed point violates constraint 2 (independent)"}

    recomputed = spec["p1"] * x + spec["p2"] * y
    if abs(recomputed - claimed) > TOL * max(1.0, abs(claimed)):
        return {"accepted": False,
                "reason": f"claimed profit {claimed} != independent recompute {recomputed}"}

    dual = _construct_dual(spec, x, y)
    if dual is None:
        return {"accepted": False,
                "reason": "no unique dual witness (degenerate vertex or singular system) - "
                          "cannot certify optimality independently"}
    u1, u2 = dual
    if u1 < -TOL or u2 < -TOL:
        return {"accepted": False, "reason": f"dual witness infeasible: u1={u1}, u2={u2} < 0"}
    if spec["a1"] * u1 + spec["a2"] * u2 < spec["p1"] - TOL:
        return {"accepted": False, "reason": "dual constraint for x violated - not a valid witness"}
    if spec["b1"] * u1 + spec["b2"] * u2 < spec["p2"] - TOL:
        return {"accepted": False, "reason": "dual constraint for y violated - not a valid witness"}

    dual_obj = spec["c1"] * u1 + spec["c2"] * u2
    if abs(dual_obj - claimed) > TOL * max(1.0, abs(claimed)):
        return {"accepted": False,
                "reason": f"strong duality fails: dual objective {dual_obj} != claimed {claimed}"}

    return {"accepted": True,
           "reason": "primal feasible, dual witness feasible, strong duality holds "
                     "(LP Duality Theorem, independent of vertex re-derivation)",
           "dual": {"u1": round(u1, 6), "u2": round(u2, 6)}}
