# VENDORED verbatim from the EulerMind research repo (github.com/judeszn/EulerMind)
# at commit 8521038 - only import paths adapted. Canonical source + full
# experiment history live there. Do not edit here.
"""Intervention 1B: general structure detection + matching extractors.

The 1A parser (kernel/edge_ai_parser.py) matched ONE literal bullet
phrasing and scored 0% on any paraphrase. 1B replaces the detection +
extraction layer with:

  Component A - detect_structure(): classify each candidate catalog line
    by its STRUCTURE (delimiter/shape), not its exact wording.
  Component B - per-structure extractors: markdown-table, delimited-bullet
    (any of : ; | , separators), and key-value, each pulling the four
    numeric fields by VALUE SEMANTICS - a number immediately tied to a
    unit label (GB/GFLOPS/ms) or a field alias - rather than by fixed
    token order.

Determinism boundary (frozen): field-name matching uses a CLOSED alias
vocabulary (FIELD_ALIASES) - not open-ended synonym learning, no model,
no embeddings. A line is only extracted deterministically when all four
fields resolve unambiguously; otherwise that line is left for the LLM
fallback. Digits + units are never guessed.

Scope honesty: extractors cover the structure TYPES named in the 1B spec
(tables, delimited bullets, key-value). They are written against value
semantics, not against research/I1_validation's specific templates - but
that validation set is still template-generated, so gains on it are a
lower bound on, not proof of, real-world-phrasing robustness. Called out
in RESULTS, not hidden.
"""

from __future__ import annotations

import re

# Closed, deterministic alias vocabulary. Not learned, not extensible at
# runtime - every accepted spelling of each field is listed here.
FIELD_ALIASES = {
    "ram_gb": ("ram", "memory", "mem"),
    "flops_g": ("flops", "gflops", "compute", "throughput"),
    "accuracy": ("accuracy", "acc"),
    "latency_ms": ("latency", "lat"),
}

# Unit tokens that disambiguate a bare number -> which field it belongs to,
# and how to normalize it. Order matters: match longer units first.
UNIT_PATTERNS = [
    ("ram_gb", re.compile(r'([\d.]+)\s*GB\b', re.IGNORECASE), 1.0),
    ("ram_gb", re.compile(r'([\d.]+)\s*MB\b', re.IGNORECASE), 1 / 1024),
    ("flops_g", re.compile(r'([\d.]+)\s*GFLOPS\b', re.IGNORECASE), 1.0),
    ("latency_ms", re.compile(r'([\d.]+)\s*ms\b', re.IGNORECASE), 1.0),
]

MODEL_NAME_RE = re.compile(r'\b([A-Z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)*)\b')
KNOWN_MODEL_HINTS = {"cnn", "transformer-lite", "xgboost", "knn", "mobilenet",
                     "tinybert", "decisiontree", "svm-linear"}


def _score(acc: float, latency_ms: float) -> int:
    return round(1000 * (0.7 * acc + 0.3 * (1.0 / latency_ms)))


def _normalize_units(segment: str) -> dict:
    """Pull unit-bearing numbers (RAM/FLOPS/latency) from a text segment
    by value semantics. Returns {field: normalized_value} for whatever it
    finds unambiguously (exactly one match per field)."""
    found = {}
    for field, pat, factor in UNIT_PATTERNS:
        matches = pat.findall(segment)
        if len(matches) == 1 and field not in found:
            found[field] = round(float(matches[0]) * factor, 6)
        elif len(matches) == 1 and field == "ram_gb":
            pass  # GB already took precedence over MB via ordering
    return found


def _extract_accuracy(segment: str) -> float | None:
    """Accuracy has no unit - find it via alias, in EITHER word order
    ('accuracy 0.93' or '0.93 accuracy'). Falls back to a lone decimal
    only after excluding decimals already claimed by a unit (e.g. 0.66GB),
    so a RAM value isn't misread as accuracy."""
    for alias in FIELD_ALIASES["accuracy"]:
        m = re.search(rf'{alias}\s*[=:]?\s*(0?\.\d+)', segment, re.IGNORECASE)  # word first
        if m:
            return float(m.group(1))
        m = re.search(rf'(0?\.\d+)\s*{alias}', segment, re.IGNORECASE)  # number first
        if m:
            return float(m.group(1))
    # Fallback: a lone 0.xx that is NOT immediately followed by a unit
    # (GB/MB/GFLOPS/ms) - those decimals belong to other fields.
    free_decimals = re.findall(r'\b(0?\.\d+)\b(?!\s*(?:GB|MB|GFLOPS|ms)\b)', segment, re.IGNORECASE)
    if len(free_decimals) == 1:
        return float(free_decimals[0])
    return None


def _extract_model_name(segment: str) -> str | None:
    """The entity name: prefer a known model hint, else the first
    capitalized token that isn't a unit/field word."""
    candidates = MODEL_NAME_RE.findall(segment)
    for c in candidates:
        if c.lower() in KNOWN_MODEL_HINTS:
            return c
    stop = {"RAM", "GB", "MB", "GFLOPS", "FLOPS", "Compute", "Accuracy",
            "Acc", "Latency", "Lat", "Model", "Memory", "Throughput"}
    for c in candidates:
        if c not in stop and not c.replace(".", "").isdigit():
            return c
    return None


def _try_extract_line(segment: str) -> tuple[str, dict] | None:
    """Extract one (name, {4 fields+score}) from a text segment, or None if
    any field can't be resolved unambiguously. Digits never guessed."""
    name = _extract_model_name(segment)
    if not name:
        return None
    units = _normalize_units(segment)
    acc = _extract_accuracy(segment)
    if not all(f in units for f in ("ram_gb", "flops_g", "latency_ms")) or acc is None:
        return None
    return name, {"ram_gb": units["ram_gb"], "flops_g": units["flops_g"],
                  "accuracy": acc, "latency_ms": units["latency_ms"],
                  "score": _score(acc, units["latency_ms"])}


# ---------------------------------------------------------------- detection

def detect_structure(text: str) -> dict:
    """Component A. Classify catalog presentation. Returns a structure type
    and the candidate line segments, without extracting - routing only."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    # Markdown table: rows starting/containing pipes with a separator row.
    pipe_rows = [ln for ln in lines if ln.count("|") >= 3]
    has_separator = any(re.match(r'^\|?[\s:-]+\|[\s:|-]+$', ln) for ln in lines)
    if len(pipe_rows) >= 3 and has_separator:
        data_rows = [ln for ln in pipe_rows
                     if not re.match(r'^\|?[\s:-]+\|[\s:|-]+$', ln)
                     and not re.search(r'\bModel\b.*\bRAM\b', ln, re.IGNORECASE)]
        return {"type": "markdown_table", "segments": data_rows}

    # Delimited bullets: lines beginning with -, *, or a bare model line
    # carrying at least two unit tokens.
    bullet_segments = [ln for ln in lines
                       if (ln.startswith(("-", "*", "•"))
                           or _looks_like_catalog_line(ln))
                       and _unit_token_count(ln) >= 2]
    if len(bullet_segments) >= 2:
        return {"type": "delimited_bullets", "segments": bullet_segments}

    # Sentence-embedded: split on sentence-final punctuation only (NOT ';',
    # which separates clauses of the same model's spec - splitting there
    # severs a model from half its fields). A catalog sentence may run
    # "Running CNN requires X; it reaches Y" and must stay whole.
    sentences = re.split(r'(?<=[.])\s+(?=[A-Z])', text)
    sentence_segments = [s for s in sentences if _unit_token_count(s) >= 2
                        and _extract_model_name(s)]
    if len(sentence_segments) >= 2:
        return {"type": "sentence_embedded", "segments": sentence_segments}

    return {"type": "none", "segments": []}


def _unit_token_count(segment: str) -> int:
    n = 0
    for _, pat, _ in UNIT_PATTERNS:
        if pat.search(segment):
            n += 1
    return n


def _is_budget_or_requirement_text(segment: str) -> bool:
    """True for text belonging to the budget or threshold regions — the
    regions extract_budgets() and extract_threshold() own. Catalog
    extraction must never consume these: a budget sentence carries the
    same unit-bearing shape as a model line ("...under 3.7GB..., 92
    GFLOPS..., 123ms") plus a leading capitalized word ("Constraints:",
    "Total budget:"), so without this exclusion it fabricates a
    pseudo-model out of the budget values (D1 root cause, reproduced
    30/30 on paraphrase L3)."""
    if _BUDGET_CUE.search(segment):
        return True
    return any(re.search(p, segment, re.IGNORECASE) for p in _THRESHOLD_PATTERNS)


def _looks_like_catalog_line(ln: str) -> bool:
    if _is_budget_or_requirement_text(ln):
        return False
    return bool(_extract_model_name(ln)) and _unit_token_count(ln) >= 2


# ---------------------------------------------------------------- budgets

_BUDGET_CUE = re.compile(
    r'\b(budget|caps?|ceilings?|limits?|permits?|allows?|'
    r'under|up to|combined|cumulative|cannot exceed|at most|total|resource)\b',
    re.IGNORECASE)


def extract_budgets(text: str) -> dict | None:
    """Budgets by value semantics, restricted to the budget region ONLY -
    sentences carrying a budget cue word. This deliberately excludes the
    catalog region (per-model specs), so a model's RAM value can't be
    misread as the RAM budget. Requires exactly one unambiguous value per
    field in that region. Handles MB->GB deterministically."""
    budget_sentences = [s for s in re.split(r'(?<=[.\n])\s+', text)
                        if _BUDGET_CUE.search(s) and _unit_token_count(s) >= 1]
    if not budget_sentences:
        return None
    blob = " ".join(budget_sentences)

    ram = flops = latency = None
    gb = re.findall(r'([\d.]+)\s*GB\b', blob, re.IGNORECASE)
    mb = re.findall(r'([\d.]+)\s*MB\b', blob, re.IGNORECASE)
    fl = re.findall(r'([\d.]+)\s*GFLOPS\b', blob, re.IGNORECASE)
    lat = re.findall(r'([\d.]+)\s*ms\b', blob, re.IGNORECASE)
    if len(gb) == 1:
        ram = round(float(gb[0]), 6)
    elif len(mb) == 1:
        ram = round(float(mb[0]) / 1024, 6)
    if len(fl) == 1:
        flops = float(fl[0])
    if len(lat) == 1:
        latency = float(lat[0])
    if ram is not None and flops is not None and latency is not None:
        return {"ram_gb": ram, "flops_g": flops, "latency_ms": latency}
    return None


# Threshold must be anchored to the REQUIREMENT phrasing (>=, "at least",
# "clear", "reaches", "or higher"), never a bare accuracy value - otherwise
# a model's accuracy (e.g. 0.93) gets misread as the threshold.
_THRESHOLD_PATTERNS = (
    r'accuracy\s*(?:>=|≥|of at least|at least|reaches?|clears?|exceeds?|above)\s*(0?\.\d+)',
    r'(?:>=|≥)\s*(0?\.\d+)\s*accuracy',
    r'(0?\.\d+)\s*(?:accuracy\s*)?or higher',
    r'clear\s*(0?\.\d+)\s*accuracy',
)


def extract_threshold(text: str) -> float | None:
    for pat in _THRESHOLD_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return float(m.group(1))
    return None


# ---------------------------------------------------------------- top level

def _extract_markdown_table(text: str) -> dict:
    """Table cells are bare numbers; units live in the header. Map columns
    by header field-alias, then read each data row positionally."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    rows = [ln for ln in lines if ln.count("|") >= 3]
    # Find the header row (contains field alias words, not a separator).
    header_idx = None
    for i, ln in enumerate(rows):
        if re.match(r'^\|?[\s:-]+\|[\s:|-]+$', ln):
            continue
        low = ln.lower()
        if any(a in low for aliases in FIELD_ALIASES.values() for a in aliases):
            header_idx = i
            break
    if header_idx is None:
        return {}
    header_cells = [c.strip() for c in rows[header_idx].strip("|").split("|")]

    # Map each column index -> (field, unit_factor). The name column is the
    # one with no field alias.
    col_field = {}
    name_col = None
    for j, cell in enumerate(header_cells):
        low = cell.lower()
        matched = None
        for field, aliases in FIELD_ALIASES.items():
            if any(a in low for a in aliases):
                matched = field
                break
        if matched:
            factor = 1 / 1024 if ("mb" in low and matched == "ram_gb") else 1.0
            col_field[j] = (matched, factor)
        elif "model" in low or name_col is None:
            name_col = j
    if name_col is None or len(col_field) < 4:
        return {}

    models = {}
    for ln in rows[header_idx + 1:]:
        if re.match(r'^\|?[\s:-]+\|[\s:|-]+$', ln):
            continue
        cells = [c.strip() for c in ln.strip("|").split("|")]
        if len(cells) <= max(name_col, max(col_field)):
            continue
        name = cells[name_col]
        if not name or name.lower() in ("model",):
            continue
        fields = {}
        ok = True
        for j, (field, factor) in col_field.items():
            m = re.search(r'([\d.]+)', cells[j])
            if not m:
                ok = False
                break
            fields[field] = round(float(m.group(1)) * factor, 6)
        if ok and len(fields) == 4:
            fields["score"] = _score(fields["accuracy"], fields["latency_ms"])
            models[name] = fields
    return models


def extract_catalog(text: str) -> tuple[dict, str]:
    """Extract from EVERY structure present and union the results, not just
    the first-matched type. Level-3-style inputs carry a table AND prose
    asides in one problem; trusting only the table silently drops the
    aside models (measured: 90 missing on L3 before this). Union-of-all
    is the honest completeness rule - a name found by any extractor counts,
    and value conflicts can't arise because each name appears in exactly
    one structure. Returns ({name: fields}, structure_label)."""
    models = {}
    labels = []

    # 1. Markdown table (column-mapped).
    table_models = _extract_markdown_table(text)
    if table_models:
        models.update(table_models)
        labels.append("markdown_table")

    # 2. Line/sentence-embedded segments (bullets, sentences, prose asides).
    #    Scanned independently of which primary type detect_structure picks,
    #    so a table's prose asides are still swept up.
    for segment_source in ("delimited_bullets", "sentence_embedded"):
        for segment in _all_catalog_segments(text):
            result = _try_extract_line(segment)
            if result is not None:
                name, fields = result
                models.setdefault(name, fields)
        break  # _all_catalog_segments already covers both; single pass

    if not labels:
        labels.append(detect_structure(text)["type"])
    return models, "+".join(labels) if labels else "none"


def _all_catalog_segments(text: str) -> list[str]:
    """Every line, sentence, or ';'-clause that looks like a single model's
    spec (a name plus >=2 unit tokens), regardless of the primary structure
    type. Used to sweep up prose-embedded catalog entries a table extractor
    misses.

    All three paths gate through _looks_like_catalog_line (D1: two of them
    previously duplicated the check inline WITHOUT the budget/requirement
    exclusion, letting the budget paragraph through as a segment). The
    ';'-clause split is scoped per line, not across the whole document —
    a clause boundary cannot span a line break, so an aside clause can no
    longer swallow an adjacent table or budget paragraph and poison its
    own field resolution with their values (D1: that contamination is what
    made aside models unresolvable and dropped them)."""
    segments = []
    for ln in text.splitlines():
        ln = ln.strip()
        if _looks_like_catalog_line(ln):
            segments.append(ln)
        # ';'-joined asides within one line ("...; also, note: X needs...").
        for clause in re.split(r';\s*(?:also,?\s*)?', ln):
            if _looks_like_catalog_line(clause):
                segments.append(clause)
    for sentence in re.split(r'(?<=[.])\s+(?=[A-Z])', text):
        if _looks_like_catalog_line(sentence):
            segments.append(sentence)
    return segments
