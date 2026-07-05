# VENDORED verbatim from the EulerMind research repo (github.com/judeszn/EulerMind)
# at commit d44a160 - only import paths adapted. Canonical source + full
# experiment history live there. Do not edit here.
"""Sigma-1 Tutor Lane — local model client (stdlib only).

Speaks the OpenAI-compatible /v1/chat/completions streaming protocol,
which BOTH llama.cpp's llama-server (the ADTC-required runtime) and
Ollama (developer convenience) expose. Probes llama-server first.

The model is prompted for step-by-step tutoring and a machine-parseable
FINAL ANSWER line. It is NEVER asked to assess or label its own
correctness - labels come from app/answer_checker.py exclusively
(competition/PROMPT_STRATEGY.md: model self-verification is the banned
fabricated-certainty pattern).
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

CANDIDATE_SERVERS = ("http://127.0.0.1:8080", "http://127.0.0.1:11434")

MULTI_QUESTION_MESSAGE = (
    "I detected multiple independent questions. EulerMind verifies one "
    "question at a time so each answer can be independently checked. "
    "Please submit one question.")

_TASK_VERB = re.compile(
    r'\b(solve|factori[sz]e|differentiate|integrate|expand|simplify|'
    r'evaluate|compute|calculate|prove|find)\b', re.IGNORECASE)


def _is_command_position(text: str, i: int) -> bool:
    """A task verb counts as a NEW command only at the start of the text, of
    a sentence, of a line, or right after a joiner (and/also/then). 'to solve
    this' in mid-prose does not count."""
    head = text[:i]
    stripped = head.rstrip()
    if not stripped:
        return True
    if '\n' in head[len(stripped):]:
        return True                     # verb begins a new line
    if stripped[-1] in '.?!;':
        return True                     # verb begins a new sentence
    last_word = stripped.split()[-1].lower().strip('*_')
    return last_word in ('and', 'also', 'then', 'plus')


def detect_multiple_questions(text: str) -> bool:
    """Deterministic gate: True when the text contains two or more separate
    maths tasks. Two command verbs count as ONE task only when nothing but
    joiner words sits between them ('expand and simplify (x+1)(x+2)');
    any real content between them ('Solve 3x = 12. Then factorise…') means
    two independent questions."""
    matches = [m for m in _TASK_VERB.finditer(text)
               if _is_command_position(text, m.start())]
    clusters = 0
    prev_end = None
    for m in matches:
        between = text[prev_end:m.start()] if prev_end is not None else None
        joined = between is not None and re.fullmatch(
            r'[\s,]*(?:and|or|also|then)?[\s,]*', between, re.IGNORECASE)
        if not joined:
            clusters += 1
        prev_end = m.end()
    return clusters >= 2

SYSTEM_PROMPT = (
    "You are a patient mathematics teacher for West African secondary school "
    "students preparing for WAEC/SSCE exams. A tired student must understand "
    "your solution after reading it once.\n"
    "\n"
    "Reply using EXACTLY six tags in this order: <UNDERSTANDING> (1-2 "
    "sentences: what the question asks), <METHOD> (3-5 short lines: the plan "
    "and why it works), <CALCULATION> (only the algebra needed, one step per "
    "line, saying WHY each step happens — 'subtract 3 from both sides so the "
    "equation stays balanced', never 'move 3 across'), <ANSWER> (ONLY the "
    "mathematical result — values like x = 5 or x = -1/2 or x = -3, or an "
    "expression like (x - 2)(x - 3); NEVER a sentence, NEVER 'see "
    "explanation', NEVER working — all explanation belongs in METHOD or "
    "CALCULATION; for a proof, state the key result, e.g. sum of angles = "
    "180 degrees), <MISTAKE> (one "
    "sentence: the usual student mistake here), <TAKEAWAY> (one sentence: "
    "the lesson to remember). Nothing outside the tags.\n"
    "\n"
    "Example — for the question 'Solve x + 2 = 5' you would reply exactly:\n"
    "<UNDERSTANDING>We need the value of x that makes both sides "
    "equal.</UNDERSTANDING>\n"
    "<METHOD>Isolate x by removing the +2 from the left side.</METHOD>\n"
    "<CALCULATION>Subtract 2 from both sides so the equation stays balanced: "
    "x = 5 - 2 = 3</CALCULATION>\n"
    "<ANSWER>x = 3</ANSWER>\n"
    "<MISTAKE>Students sometimes add 2 instead of subtracting it.</MISTAKE>\n"
    "<TAKEAWAY>Whatever you do to one side, do to the other.</TAKEAWAY>\n"
    "\n"
    "Write ALL mathematics in plain text: no LaTeX, no backslashes, no "
    "\\frac, no \\boxed, no dollar signs. Fractions as a/b, powers as x^2, "
    "roots as sqrt(...), plus-or-minus as ±.\n"
    "Solve it once, correctly, and stop: one line of reasoning, never "
    "restart, never apologise, never show a second method.\n"
    "Never label your own answer as verified or correct — a separate program "
    "checks it."
)


def discover_server(timeout: float = 0.8) -> tuple[str, str] | None:
    """Returns (base_url, model_id) of the first live server, else None."""
    for base in CANDIDATE_SERVERS:
        try:
            with urllib.request.urlopen(f"{base}/v1/models", timeout=timeout) as r:
                data = json.loads(r.read())
            models = [m.get("id", "") for m in data.get("data", [])]
            if models:
                preferred = next(
                    (m for pref in ("math", "qwen") for m in models
                     if pref in m.lower()), models[0])
                return base, preferred
        except (urllib.error.URLError, OSError, json.JSONDecodeError):
            continue
    return None


def stream_tutor_answer(question: str, base: str, model: str,
                        status: dict | None = None):
    """Yields text chunks from the local model. Raises on connection loss.
    Pass a dict as `status` to receive the generation's finish_reason
    ('stop' = completed; 'length' = truncated at the token cap — the caller
    must NOT attempt verification on a truncated answer)."""
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                     {"role": "user", "content": question}],
        "stream": True,
        "temperature": 0.1,  # format stability: the tag contract matters more than variety
        "max_tokens": 1600,  # qwen-math CoT is verbose; 900 clipped real answers
    }).encode()
    req = urllib.request.Request(
        f"{base}/v1/chat/completions", data=payload,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        for raw in resp:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line.startswith("data:"):
                continue
            body = line[5:].strip()
            if body == "[DONE]":
                return
            try:
                choice = json.loads(body)["choices"][0]
            except (json.JSONDecodeError, KeyError, IndexError):
                continue
            reason = choice.get("finish_reason")
            if reason and status is not None:
                status["finish_reason"] = reason
            chunk = choice.get("delta", {}).get("content")
            if chunk:
                yield chunk
