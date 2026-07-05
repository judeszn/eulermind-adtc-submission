# VENDORED verbatim from the EulerMind research repo (github.com/judeszn/EulerMind)
# at commit d44a160 - only import paths adapted. Canonical source + full
# experiment history live there. Do not edit here.
"""Sprint Σ3 Phase 1 — Reality Check (run on YOUR hardware, real model).

This is the instrument for the one thing the sprint hinges on: hearing the
*actual* offline Qwen2.5-Math model explain WAEC/SSCE questions. It does NOT
improve anything (Phase 1 rule: understand reality first). It runs a fixed,
representative question set through the real local model + the deterministic
checker, and writes an auditable transcript for the Phase 2 explanation audit.

Prerequisite — start the model first (the ADTC runtime), e.g.:
    llama-server -m model/qwen2.5-math-1.5b-instruct-q4_k_m.gguf --port 8080

Then:
    python3 -m app.reality_check
    -> writes competition/reality_check_transcript.md

Stdlib only. No assumptions, no synthetic answers — every explanation below
comes from the real model or the run fails loudly.
"""

from __future__ import annotations

import time
from pathlib import Path

from .answer_checker import check_answer, trust_rationale
from .tutor import discover_server, stream_tutor_answer

OUT = Path("competition/reality_check_transcript.md")

# Representative SS1-SS3 / WAEC set. Deliberately mixed: some land in the
# checkable families (expect Derived) and some do NOT (expect an honest
# Heuristic) — so the audit sees both the teaching AND the trust behaviour on
# real output. Themed for the West-African context where natural.
QUESTIONS = [
    "Solve 2x^2 + 7x + 3 = 0. Show your working.",
    "Solve the simultaneous equations 3x + 2y = 16 and x - y = 3.",
    "Solve 5x - 7 = 2x + 8.",
    "Expand (2x - 3)(x + 5).",
    "Factorise x^2 - 5x + 6.",
    "Simplify 3(2x - 1) + 4(x + 2).",
    "Differentiate y = x^3 - 4x^2 + 2x with respect to x.",
    "Evaluate 15% of 240.",
    "Make x the subject of the formula v = u + a*x.",
    "A trader buys an item for 4500 naira and sells it for 5400 naira. "
    "Find the percentage profit.",
    "Find the gradient of the line joining the points (1, 2) and (4, 11).",
    "Prove that the sum of the angles in a triangle is 180 degrees.",
]


def _run_one(q: str, base: str, model: str) -> dict:
    t0 = time.perf_counter()
    status: dict = {}
    text = "".join(stream_tutor_answer(q, base, model, status))
    dt = time.perf_counter() - t0
    truncated = status.get("finish_reason") == "length"
    if truncated:
        # a clipped answer is NEVER verified — label it honestly instead
        check = {"label": "Heuristic", "checked": False, "passed": None,
                 "note": "incomplete generation (token limit) — nothing checked"}
    else:
        check = check_answer(q, text)
    return {"question": q, "explanation": text, "seconds": dt,
            "truncated": truncated,
            "label": check["label"], "checked": check["checked"],
            "passed": check["passed"], "note": check["note"],
            "rationale": trust_rationale(check)}


def _render(rows: list[dict], model: str) -> str:
    n = len(rows)
    derived = sum(r["label"] == "Derived" for r in rows)
    heuristic = sum(r["label"] == "Heuristic" for r in rows)
    truncated = sum(r.get("truncated", False) for r in rows)
    mean_s = sum(r["seconds"] for r in rows) / n
    false_ver = sum(r["label"] == "Derived" and r["passed"] is False for r in rows)
    lines = [
        "# Σ3 Phase 1 — Reality Check transcript",
        "",
        f"Model: `{model}` · questions: {n} · "
        f"Derived: {derived} · Heuristic: {heuristic} · "
        f"Truncated: {truncated} · mean {mean_s:.1f}s/question · "
        f"**False verifications: {false_ver}** (must be 0)",
        "",
        "> Phase 2 audit question for every explanation below: *Could a "
        "struggling SS2/SS3 student genuinely understand this?* If not, note "
        "exactly why (skipped reasoning / too symbolic / assumes prior "
        "knowledge / poor ordering / too verbose / too short).",
        "",
    ]
    for i, r in enumerate(rows, 1):
        lines += [
            f"## Q{i}. {r['question']}",
            f"*label:* **{r['label']}** · *{r['seconds']:.1f}s* · "
            f"*check:* {r['note']}",
            "",
            "```",
            r["explanation"].strip() or "(empty response)",
            "```",
            "",
            "Audit — understandable to a struggling SS3 student? __________  "
            "why / why not: __________",
            "",
            "---",
            "",
        ]
    return "\n".join(lines)


def main() -> None:
    """Default: the fixed 12-question dev set. With a file argument
    (`python3 -m app.reality_check holdout/waec_past_papers.txt`, one
    question per line, '#' comments allowed): a HOLDOUT run — questions
    must come from real past papers, not authored by anyone who wrote the
    checkers, and the file is run ONCE (holdout discipline, WIN.md)."""
    import sys
    global QUESTIONS, OUT
    if len(sys.argv) > 1:
        src = Path(sys.argv[1])
        QUESTIONS = [ln.strip() for ln in src.read_text(encoding="utf-8").splitlines()
                     if ln.strip() and not ln.lstrip().startswith("#")]
        OUT = Path(f"competition/holdout_{src.stem}_transcript.md")
        if not QUESTIONS:
            raise SystemExit(f"no questions found in {src}")
    server = discover_server()
    if server is None:
        print("No local model server found on 127.0.0.1:8080 or :11434.\n"
              "Start the real model first, e.g.:\n"
              "  llama-server -m model/qwen2.5-math-1.5b-instruct-q4_k_m.gguf "
              "--port 8080\n"
              "Phase 1 needs the REAL model — this script will not invent "
              "explanations.")
        raise SystemExit(1)
    base, model = server
    print(f"Reality check against {model} at {base} — {len(QUESTIONS)} "
          "questions, fully offline. This streams real model output…\n")
    rows = []
    for i, q in enumerate(QUESTIONS, 1):
        print(f"  [{i}/{len(QUESTIONS)}] {q[:60]}…")
        rows.append(_run_one(q, base, model))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(_render(rows, model), encoding="utf-8")
    false_ver = sum(r["label"] == "Derived" and r["passed"] is False for r in rows)
    print(f"\nWrote {OUT}.  False verifications: {false_ver} (must be 0).")
    print("Next (Phase 2): read each explanation and answer the audit line.")


if __name__ == "__main__":
    main()
