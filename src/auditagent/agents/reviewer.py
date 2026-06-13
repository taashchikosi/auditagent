"""Reviewer agent — THE CITATION GATE (the core differentiator).

Rule, applied to every finding:
    A finding is ACCEPTED only if it carries a citation whose offsets
    re-slice the raw contract to EXACTLY the quoted text. Otherwise:
      1. ONE retry — ask the reviewer provider to re-extract a verbatim quote
         from the source text (this is the ~2% Claude-Sonnet call in prod).
      2. Re-anchor the re-extracted quote against raw text.
      3. Still no exact anchor → REJECT (uncited / bad citation).

This is what turns "the model said so" into "here's the exact clause, proven".
A hallucinated clause that isn't in the document survives neither the anchor
check nor re-extraction — so it is rejected, by construction.
"""

from __future__ import annotations

from ..anchor import fuzzy_anchor_quote
from ..clauses import V1_CLAUSES
from ..llm.base import LLMProvider
from ..models import (
    Finding,
    ReviewedFinding,
    ReviewStatus,
)


def _spec_for(clause_type: str):
    for spec in V1_CLAUSES:
        if spec.name == clause_type or spec.key == clause_type:
            return spec
    return None


def _reextract(
    finding: Finding, raw_text: str, reviewer: LLMProvider
) -> Finding | None:
    """Second-chance: have the reviewer re-extract a verbatim quote."""
    spec = _spec_for(finding.clause_type)
    if spec is None:
        return None
    hits = reviewer.classify(raw_text, (spec,))
    for hit in hits:
        cit = fuzzy_anchor_quote(raw_text, hit.quote)
        if cit is not None:
            return finding.model_copy(update={"citation": cit})
    return None


def review_findings(
    findings: list[Finding],
    raw_text: str,
    reviewer: LLMProvider,
    *,
    max_retries: int = 1,
) -> list[ReviewedFinding]:
    """Gate every finding; accept only citation-verified ones."""
    reviewed: list[ReviewedFinding] = []
    for f in findings:
        if f.citation is not None and f.citation.verify_against(raw_text):
            reviewed.append(ReviewedFinding(finding=f, status=ReviewStatus.ACCEPTED))
            continue

        fixed = _reextract(f, raw_text, reviewer) if max_retries else None
        if fixed is not None and fixed.citation.verify_against(raw_text):
            reviewed.append(
                ReviewedFinding(
                    finding=fixed,
                    status=ReviewStatus.ACCEPTED,
                    reason="citation re-extracted and verified on retry",
                    retries=1,
                )
            )
            continue

        status = (
            ReviewStatus.REJECTED_UNCITED
            if f.citation is None
            else ReviewStatus.REJECTED_BAD_CITATION
        )
        reviewed.append(
            ReviewedFinding(
                finding=f,
                status=status,
                reason="no exact-span evidence after retry — rejected to prevent "
                "an uncited (possibly hallucinated) finding",
                retries=1 if max_retries else 0,
            )
        )
    return reviewed
