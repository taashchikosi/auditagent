"""Deterministic, offline provider — default so M2 runs with no API keys.

Two strategies, which is what makes the side-by-side demo (#16) real:

  * THOROUGH (the agent's classifier): scans the full text, and returns the
    EXACT sentence containing a cue as the quote — so it anchors cleanly and
    the citation gate accepts it.

  * LAZY (the B1 single-shot baseline): reads only a truncated context window
    and returns a whitespace-normalised paraphrase as its "quote". This
    reproduces the ContractEval finding — single-shot LLMs miss clauses
    buried later in long contracts (false negatives) and sometimes cite text
    that doesn't exactly exist. The agent then visibly beats it.

This is a STAND-IN for the LLM's clause-detection step, not a claim of
accuracy. Real accuracy is measured against CUAD labels at M3 with a real
model. The pipeline, gate, checklist and audit log around it are the real,
permanent engineering.
"""

from __future__ import annotations

import re

from ..clauses import ClauseSpec
from .base import ClauseHit

# A naive sentence splitter is fine here: we only need a plausible quote
# window; the classifier re-anchors it to exact offsets against raw text.
_SENT = re.compile(r"[^.!?]*[.!?]")


class DeterministicProvider:
    """Keyword/cue-based clause detector with thorough vs lazy strategies."""

    def __init__(self, *, lazy: bool = False, context_limit: int = 1600) -> None:
        self.lazy = lazy
        self.context_limit = context_limit
        self.name = "deterministic-lazy(B1)" if lazy else "deterministic-thorough"

    def classify(
        self, text: str, clause_specs: tuple[ClauseSpec, ...]
    ) -> list[ClauseHit]:
        scope = text[: self.context_limit] if self.lazy else text
        hits: list[ClauseHit] = []
        seen: set[str] = set()
        for spec in clause_specs:
            sentence = self._first_sentence_with_cue(scope, spec)
            if sentence is None:
                continue  # lazy mode misses clauses outside the truncated scope
            if spec.key in seen:
                continue
            seen.add(spec.key)
            quote = sentence
            if self.lazy:
                # Single-shot models paraphrase / re-whitespace their quotes;
                # collapsing whitespace makes the quote fail exact anchoring,
                # so the gate will reject it -> a visible B1 failure mode.
                quote = " ".join(sentence.split())
            hits.append(
                ClauseHit(
                    clause_key=spec.key,
                    quote=quote.strip(),
                    rationale=spec.why,
                    confidence=0.55 if self.lazy else 0.9,
                )
            )
        return hits

    @staticmethod
    def _first_sentence_with_cue(text: str, spec: ClauseSpec) -> str | None:
        low = text.lower()
        for cue in spec.cues:
            idx = low.find(cue.lower())
            if idx == -1:
                continue
            # Expand to the surrounding sentence for a meaningful quote.
            start = text.rfind(".", 0, idx) + 1
            end = text.find(".", idx)
            end = end + 1 if end != -1 else len(text)
            candidate = text[start:end].strip()
            if candidate:
                return candidate
        return None
