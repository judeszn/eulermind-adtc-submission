# VENDORED verbatim from the EulerMind research repo (github.com/judeszn/EulerMind)
# at commit 8521038 - only import paths adapted. Canonical source + full
# experiment history live there. Do not edit here.
"""Gamma Task 1 — CSP Formalizer for constraint_csp.

Parser-first, deterministic wherever the source is explicit; LLM performs
semantic association only, and only when deterministic extraction cannot
apply, per the frozen contract. The four constraint kinds are rendered by
benchmark/generator/csp.py from FIXED deterministic templates (not
paraphrased prose, unlike edge_ai_deployment) - so a template-matching
parser, not a value-semantic one, is the right tool here: the templates
are the "explicit structure" this domain presents.

Output spec shape (identical to what the solver consumes):
{engineers: [...], projects: [...], project_tags: {proj: tag},
 constraints: [{"kind": ..., ...fields}]}

Independent of benchmark/ - the four render templates are duplicated here
by necessity (parsing is the inverse of benchmark/generator/csp.py's
_render(), not an import of it).
"""

from __future__ import annotations

import json
import re
import urllib.request

OLLAMA_URL = "http://localhost:11434/api/generate"

FORBIDDEN_RE = re.compile(r'^-?\s*(\w+) cannot be assigned (Project \w+)\.$')
EXACT_TAG_RE = re.compile(r'^-?\s*Exactly (\d+) engineers? must be assigned (\w+) projects\.$')
NOT_BOTH_TAG_RE = re.compile(r'^-?\s*(\w+) and (\w+) cannot both be assigned (\w+) projects\.$')
IMPLIES_RE = re.compile(
    r'^-?\s*If (\w+) is assigned (Project \w+), then (\w+) must be assigned (Project \w+)\.$')

PROJECT_LINE_RE = re.compile(r'^-\s*(Project \w+)\s*\((\w+)\)\s*$')
INTRO_RE = re.compile(
    r'([A-Z][a-z]+(?:,\s*[A-Z][a-z]+)*(?:\s+and\s+[A-Z][a-z]+)?)'
    r'[—\-]must each be assigned exactly one project', re.IGNORECASE)
# The intro sentence uses an em-dash on both sides: "Five engineers—A, B and C—must..."
INTRO_NAMES_RE = re.compile(r'engineers[—\-]([^—\-]+)[—\-]must each be assigned')


def parse_engineers(text: str) -> list[str] | None:
    m = INTRO_NAMES_RE.search(text)
    if not m:
        return None
    raw = m.group(1)
    raw = raw.replace(" and ", ", ")
    names = [n.strip() for n in raw.split(",") if n.strip()]
    return names or None


def parse_projects(text: str) -> dict | None:
    tags = {}
    for line in text.splitlines():
        m = PROJECT_LINE_RE.match(line.strip())
        if m:
            tags[m.group(1)] = m.group(2)
    return tags or None


def parse_constraints(text: str) -> tuple[list[dict], list[str]]:
    """Returns (parsed_constraints, unparsed_lines). Unparsed lines are the
    explicit fallback signal - each becomes a candidate for the LLM."""
    parsed, unparsed = [], []
    in_section = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("Constraints:"):
            in_section = True
            continue
        if not in_section or not line.startswith("-"):
            continue
        body = line[1:].strip()
        m = FORBIDDEN_RE.match("- " + body)
        if m:
            parsed.append({"kind": "forbidden", "engineer": m.group(1), "project": m.group(2)})
            continue
        m = EXACT_TAG_RE.match("- " + body)
        if m:
            parsed.append({"kind": "exact_tag", "count": int(m.group(1)), "tag": m.group(2)})
            continue
        m = NOT_BOTH_TAG_RE.match("- " + body)
        if m:
            parsed.append({"kind": "not_both_tag", "e1": m.group(1), "e2": m.group(2),
                           "tag": m.group(3)})
            continue
        m = IMPLIES_RE.match("- " + body)
        if m:
            parsed.append({"kind": "implies", "e1": m.group(1), "p1": m.group(2),
                           "e2": m.group(3), "p2": m.group(4)})
            continue
        unparsed.append(body)
    return parsed, unparsed


# ---- Second template family: natural assignment prose (added 2026-07-04,
# submission-compliance fix D5). "assign four volunteers - A, B, C, and D -
# to four clinics: W, X, Y, and Z" with sentence-form constraints. Closed
# patterns, fail-closed: a constraint sentence matching none of the shapes
# below is simply not captured (the standing Trust Boundary applies -
# Verified is relative to the formalized spec; fidelity is separate).

_PROSE_INTRO_RE = re.compile(
    r'assign\s+(?:\w+\s+)?\w+?s?\s*[-—–]\s*(.+?)\s*[-—–]\s*to\s+(?:\w+\s+)?\w+?s?:\s*'
    r'(.+?)(?:,\s*with\b[^.]*)?\.', re.IGNORECASE)
_PROSE_FORBIDDEN_RE = re.compile(r'\b([A-Z]\w+) cannot be assigned to ([A-Z]\w+)')
_PROSE_EITHER_RE = re.compile(
    r'\b([A-Z]\w+) must be assigned to either ([A-Z]\w+) or ([A-Z]\w+)')
_PROSE_IMPLIES_RE = re.compile(
    r'\bIf ([A-Z]\w+) is assigned to ([A-Z]\w+),? then ([A-Z]\w+) must be assigned to ([A-Z]\w+)')


def _split_name_list(raw: str) -> list[str]:
    raw = raw.replace(" and ", ", ")
    return [n.strip() for n in raw.split(",") if n.strip()]


def parse_assignment_prose(text: str) -> dict | None:
    """Deterministic parse of the natural-prose assignment family. Returns
    the same spec shape the solver consumes, or None (fail closed)."""
    m = _PROSE_INTRO_RE.search(text)
    if not m:
        return None
    people = _split_name_list(m.group(1))
    places = _split_name_list(m.group(2))
    if len(people) < 2 or len(places) < len(people):
        return None
    people_set, places_set = set(people), set(places)

    constraints: list[dict] = []
    for who, where in _PROSE_FORBIDDEN_RE.findall(text):
        if who in people_set and where in places_set:
            constraints.append({"kind": "forbidden", "engineer": who, "project": where})
    for who, opt1, opt2 in _PROSE_EITHER_RE.findall(text):
        if who in people_set and opt1 in places_set and opt2 in places_set:
            # "must be either A or B" == forbidden everywhere else (exact,
            # not a heuristic - the complement over a finite domain).
            for other in places:
                if other not in (opt1, opt2):
                    constraints.append({"kind": "forbidden", "engineer": who,
                                        "project": other})
    for e1, p1, e2, p2 in _PROSE_IMPLIES_RE.findall(text):
        if e1 in people_set and p1 in places_set and e2 in people_set and p2 in places_set:
            constraints.append({"kind": "implies", "e1": e1, "p1": p1,
                                "e2": e2, "p2": p2})
    if not constraints:
        return None
    return {"engineers": people, "projects": places,
            "project_tags": {p: "" for p in places}, "constraints": constraints}


_LLM_CONSTRAINT_PROMPT = (
    'Classify this single constraint sentence into exactly one JSON object. '
    'The engineer/project names are proper nouns (e.g. "Alice", "Project X") - '
    'copy them exactly as written, never invent or alter them.\n'
    'Shapes (pick the one that matches):\n'
    '{"kind":"forbidden","engineer":"<name>","project":"<name>"}\n'
    '{"kind":"exact_tag","count":<int>,"tag":"<tag>"}\n'
    '{"kind":"not_both_tag","e1":"<name>","e2":"<name>","tag":"<tag>"}\n'
    '{"kind":"implies","e1":"<name>","p1":"<name>","e2":"<name>","p2":"<name>"}\n\n'
    'Sentence: {line}\nRespond with ONLY the JSON object.'
)


def _llm_parse_constraint(line: str, model: str = "llama3.2:1b") -> dict | None:
    """Minimal LLM fallback: semantic classification of ONE constraint
    sentence into a known shape. Never invents entity names (the model is
    told to copy them, not compute anything) - this is association, not
    deterministic reasoning, per the frozen contract."""
    try:
        payload = json.dumps({
            "model": model, "prompt": _LLM_CONSTRAINT_PROMPT.format(line=line),
            "stream": False, "format": "json",
            "options": {"temperature": 0.0, "num_predict": 150},
        }).encode()
        req = urllib.request.Request(OLLAMA_URL, data=payload,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            out = json.loads(resp.read())
        parsed = json.loads(out.get("response", "") or "{}")
        if isinstance(parsed, dict) and parsed.get("kind") in (
                "forbidden", "exact_tag", "not_both_tag", "implies"):
            return parsed
    except Exception:
        pass
    return None


class CSPFormalizer:
    """Formalizer protocol. Parser-first; explicit LLM fallback ONLY for
    individual constraint lines the deterministic templates don't match -
    never for engineers/projects, which are pure entity listing with no
    "association" role for the LLM to play. Engineers is a fixed 5-name
    list and projects always render as `- Project X (tag)`; if those are
    missing it is a genuine formalization failure to report, not a
    semantic-interpretation task to hand to the LLM."""

    def __init__(self, model: str = "llama3.2:1b"):
        self.model = model

    def formalize(self, state) -> dict:
        text = state.problem_text
        engineers = parse_engineers(text)
        tags = parse_projects(text)
        constraints, unparsed = parse_constraints(text)

        # Second template family (natural assignment prose) - tried only
        # when the benchmark family's intro is absent, so benchmark-format
        # parsing is byte-identical to the pre-D5 behavior.
        if engineers is None and tags is None:
            prose_spec = parse_assignment_prose(text)
            if prose_spec is not None:
                return {"kind": "csp", "spec": prose_spec,
                        "formalizer_tokens": 0, "source": "parser_prose",
                        "unparsed_constraint_lines": 0}

        llm_calls = 0
        recovered = []
        if unparsed and engineers and tags:
            for line in unparsed:
                c = _llm_parse_constraint(line, model=self.model)
                llm_calls += 1
                if c is not None:
                    recovered.append(c)
        constraints = constraints + recovered
        still_unparsed = len(unparsed) - len(recovered)

        complete = bool(engineers) and bool(tags) and bool(constraints) and still_unparsed == 0
        source = "parser" if not unparsed else ("llm_fallback" if not still_unparsed else "unparsed")
        if complete:
            return {"kind": "csp",
                    "spec": {"engineers": engineers, "projects": list(tags),
                             "project_tags": tags, "constraints": constraints},
                    "formalizer_tokens": llm_calls * 30, "source": source,
                    "unparsed_constraint_lines": 0}

        return {"kind": "csp", "spec": None, "formalizer_tokens": llm_calls * 30,
                "source": "unparsed", "unparsed_constraint_lines": still_unparsed,
                "missing_engineers": engineers is None, "missing_projects": tags is None}
