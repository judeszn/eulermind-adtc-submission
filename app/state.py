# VENDORED verbatim from the EulerMind research repo (github.com/judeszn/EulerMind)
# at commit 8521038 - only import paths adapted. Canonical source + full
# experiment history live there. Do not edit here.
"""Execution State — the internal data model frozen in docs/VISION.md.

One object flows through the Reasoning Kernel loop. It is the only thing the
stages pass between each other and the only thing the trace log serializes
(Guardrail 6: everything is logged).

Phase 0 ships only this schema and the trace logger; the loop that mutates it
arrives in Phase 1.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field

STATE_SCHEMA_VERSION = 2  # bump on any serialized-field change; never break replay logs
# v2: FailureSignal shape changed from {"check": ...} to {"kind","location","evidence"};
# history "attempt_done" records now include "failure_kinds". See docs/LOGGING.md.

TRUST_LABELS = ("Verified", "Derived", "Heuristic", "Open")

# Escalation ladder (frozen): each rung is tried before the next.
NEXT_ACTIONS = ("formalize", "attempt", "patch", "rederive", "reformalize", "stop")

# Failure taxonomy (frozen): every failed attempt is classified as exactly one.
FAILURE_TYPES = ("formalization", "planning", "execution", "verification",
                 "timeout", "memory", "unknown")


@dataclass
class ExecutionState:
    problem_id: str
    problem_text: str
    schema_version: int = STATE_SCHEMA_VERSION
    formalization: dict | None = None      # variables/constraints/objective/unknowns/units
    formalization_checks: dict | None = None  # back-translation agreement etc. (derived, never self-reported)
    attempt: int = 0
    execution_result: dict | None = None
    verifier_result: dict | None = None    # must carry failure signals, never a bare pass/fail
    trust_label: str = "Open"
    next_action: str = "formalize"
    history: list[dict] = field(default_factory=list)

    def record(self, event: str, **payload) -> None:
        """Append an event to the in-state history (kept small; full detail
        goes to the TraceLogger)."""
        self.history.append({"t": time.time(), "event": event, "attempt": self.attempt, **payload})

    def to_dict(self) -> dict:
        return asdict(self)


class TraceLogger:
    """Append-only JSONL trace. Guardrail 6: every retry, every execution,
    every verifier output."""

    def __init__(self, path: str):
        self.path = path
        self._fh = open(path, "a", encoding="utf-8")

    def log(self, record: dict) -> None:
        self._fh.write(json.dumps(record, default=str) + "\n")
        self._fh.flush()

    def close(self) -> None:
        self._fh.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
