"""Clause Classifier agent — detect the v1 clauses, anchor quotes to offsets.

It TRUSTS the provider's quote only as far as it can verify it: a quote earns
a citation only if it's an exact substring of the raw contract. A paraphrased
or invented quote yields `citation=None` — deliberately leaving the Reviewer
something to reject. (This is how the B1 lazy baseline ends up with uncited,
unanchorable findings.)
"""

from __future__ import annotations

from ..anchor import fuzzy_anchor_quote
from ..clauses import CLAUSE_NAME_BY_KEY, V1_CLAUSES, ClauseSpec
from ..llm.base import LLMProvider
from ..models import Citation, Finding


def anchor_quote(raw_text: str, quote: str) -> Citation | None:
    """Return a Citation iff `quote` is an EXACT substring of raw_text.

    Kept as the strict byte-exact primitive (re-exported, used by tests and as
    the fast path). For real LLM quotes — which differ by whitespace / smart-
    quotes / dashes — use `fuzzy_anchor_quote`, which tries this first then
    normalizes to LOCATE the region while still returning a real raw slice.
    """
    idx = raw_text.find(quote)
    if idx == -1:
        return None
    return Citation(quote=quote, start_char=idx, end_char=idx + len(quote))


def classify_clauses(
    raw_text: str,
    provider: LLMProvider,
    *,
    clause_specs: tuple[ClauseSpec, ...] = V1_CLAUSES,
) -> list[Finding]:
    """Run the provider, then anchor each hit to exact source offsets."""
    findings: list[Finding] = []
    seen: set[str] = set()
    for hit in provider.classify(raw_text, clause_specs):
        if hit.clause_key in seen:
            continue
        seen.add(hit.clause_key)
        findings.append(
            Finding(
                clause_type=CLAUSE_NAME_BY_KEY.get(hit.clause_key, hit.clause_key),
                rationale=hit.rationale,
                citation=fuzzy_anchor_quote(raw_text, hit.quote),
                raw_quote=hit.quote,  # keep the model's original for eval re-anchoring
                confidence=hit.confidence,
            )
        )
    return findings
