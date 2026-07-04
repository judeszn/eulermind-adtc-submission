# VENDORED verbatim from the EulerMind research repo (github.com/judeszn/EulerMind)
# at commit 8521038 - only import paths adapted. Canonical source + full
# experiment history live there. Do not edit here.
"""Intervention 1B formalizer: general structure detection + extractors.

Same Formalizer protocol, same parser-first-with-explicit-fallback shape
as 1A's ParserFirstFormalizer - only the detection/extraction layer is
generalized (kernel/edge_ai_extractors.py). 1A's class is left untouched
as the baseline the comparison is against.

Completeness rule (frozen for 1B): the deterministic path is only trusted
when it recovers the FULL catalog structure it detected AND all three
budgets AND the threshold. Partial deterministic extraction is merged over
the LLM's attempt (parser values overwrite LLM values field-by-field), so
a dropped catalog line degrades to LLM-for-that-line, never to a silently
incomplete spec.
"""

from __future__ import annotations

from .edge_ai_extractors import extract_budgets, extract_catalog, extract_threshold


class StructuredFormalizer:
    def __init__(self, fallback_formalizer=None):
        from .edge_ai import LLMFormalizer
        self.fallback = fallback_formalizer or LLMFormalizer()

    def formalize(self, state) -> dict:
        text = state.problem_text
        models, structure_type = extract_catalog(text)
        budgets = extract_budgets(text)
        threshold = extract_threshold(text)

        det_complete = bool(models) and budgets is not None and threshold is not None

        if det_complete:
            return {"kind": "knapsack",
                    "spec": {"models": models, "budgets": budgets,
                             "high_acc_threshold": threshold},
                    "formalizer_tokens": 0, "source": "parser",
                    "structure_type": structure_type,
                    "det_models_found": len(models)}

        # Explicit fallback with field-level splice: whatever the
        # deterministic layer DID resolve overwrites the LLM's guess for
        # that field; everything else is the LLM's.
        result = self.fallback.formalize(state)
        result["source"] = "llm_fallback"
        result["structure_type"] = structure_type
        result["det_models_found"] = len(models)
        spec = result.get("spec")
        if isinstance(spec, dict):
            if models:
                spec["models"] = {**spec.get("models", {}), **models}
            if budgets is not None:
                spec["budgets"] = budgets
            if threshold is not None:
                spec["high_acc_threshold"] = threshold
        elif models and budgets is not None and threshold is not None:
            # LLM produced nothing usable but the deterministic layer
            # actually has everything - promote it rather than discard.
            result["spec"] = {"models": models, "budgets": budgets,
                              "high_acc_threshold": threshold}
            result["source"] = "parser_recovered"
        return result
